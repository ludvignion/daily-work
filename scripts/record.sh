#!/usr/bin/env bash
# record.sh list             tasks whose project README line says "open"
# record.sh begin <task>     check the task, snapshot Ask and Spec, list what to read
# record.sh finish <task>    one-line summary on stdin; verify Ask and Spec unchanged, mark
#                            the README line done, commit, print the Done lines.
# <task> is the task name, or the task file <project>/tasks/<task-name>.md.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

if [ "${1:-}" = list ]; then
  n=0
  for f in */README.md; do
    p=$(dirname "$f")
    [ -d "$p/tasks" ] || continue
    while read -r _ _ s _; do
      s=${s%:}
      if [ -f "$p/briefs/$s.md" ]; then echo "$p/briefs/$s.md (not grilled yet)"; else echo "$p/tasks/$s.md"; fi
      n=$((n + 1))
    done < <(grep -E '^- [0-9]{4}-[0-9]{2}-[0-9]{2} [a-z0-9-]+: open$' "$f" || true)
  done
  [ "$n" -gt 0 ] || echo "no open tasks"
  exit 0
fi

MODE=${1:-}; T=${2:-}
[[ $MODE == begin || $MODE == finish ]] || refuse "usage: record.sh list | begin <task> | finish <task>"
T=${T#"$PWD/"}; T=${T#./}
# A bare task name stands for its task file, in whichever project holds it.
if [[ $T =~ $SLUG_RE ]]; then
  found=$(ls -d */tasks/"$T".md 2>/dev/null || true)
  case $(grep -c . <<< "$found" || true) in
    1) T=$found ;;
    0) b=$(ls -d */briefs/"$T".md 2>/dev/null | head -1 || true)
       [ -n "$b" ] && refuse "$b is still a brief; grill it first"
       refuse "no task named '$T'; run /daily-work:record with no argument to list open tasks" ;;
    *) refuse "'$T' is a task in several projects; name one of: $(tr '\n' ' ' <<< "$found")" ;;
  esac
fi
[[ $T =~ ^([a-z0-9-]+)/tasks/([a-z0-9-]+)\.md$ ]] || refuse "'$T' is not a task name or <project>/tasks/<task-name>.md"
PROJECT=${BASH_REMATCH[1]} SLUG=${BASH_REMATCH[2]}
P=$PROJECT
[ -f "$T" ] || { [ -f "$P/briefs/$SLUG.md" ] && refuse "$P/briefs/$SLUG.md is still a brief; grill it into $T first"; refuse "$T not found"; }
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || refuse "not a git repo"
SNAP=$GIT_DIR/daily-work/$PROJECT-$SLUG.spec

ask_spec() { awk '/^## Ask$/ { on = 1 } /^## (Result|Caveats)$/ { on = 0 } on' "$T"; }

# The project's outputs/ is shared by its tasks; what differs from the last commit is this task's.
changed_outputs() {
  { git -c core.quotePath=false diff --name-only HEAD -- "$P/outputs" 2>/dev/null || true
    git -c core.quotePath=false ls-files --others --exclude-standard -- "$P/outputs"
  } | grep -v '/\.gitkeep$' | sort -u || true
}

if [ "$MODE" = begin ]; then
  mkdir -p "$(dirname "$SNAP")"; ask_spec > "$SNAP"
  echo "task: $T"
  echo "sources: $P/sources.md"
  out=$(changed_outputs)
  if [ -n "$out" ]; then echo "outputs changed since the last commit:"; sed 's/^/  /' <<< "$out"
  else echo "outputs changed since the last commit: none"; fi
  exit 0
fi

[ -f "$SNAP" ] || refuse "run record.sh begin $T first"
ask_spec | cmp -s - "$SNAP" || refuse "## Ask or ## Spec in $T changed since begin; restore them, nothing committed"
grep -qF '<written by /daily-work:record>' "$T" && refuse "## Result or ## Caveats still holds the placeholder"
SUM=$(tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')
[ -n "$SUM" ] || refuse "no one-line summary on stdin"

# Keep the date already on the README line; a task without one takes its Created date.
RE="^- ([0-9]{4}-[0-9]{2}-[0-9]{2}) $SLUG:"
DATE=$(grep -oE "$RE" "$P/README.md" | head -1 | cut -d' ' -f2 || true)
[ -n "$DATE" ] || DATE=$(sed -n 's/^Created: //p' "$T" | head -1)
LINE="- $DATE $SLUG: done, $SUM"
if grep -qE "$RE" "$P/README.md"; then
  RE="$RE" LINE="$LINE" awk '$0 ~ ENVIRON["RE"] { print ENVIRON["LINE"]; next } { print }' \
    "$P/README.md" > "$P/README.md.tmp" && mv "$P/README.md.tmp" "$P/README.md"
else
  add_under "$P/README.md" "## Tasks" "$LINE"
fi

content id "$PWD/$T"
paths=("$T" "$P/README.md")
for p in "$P/tasks/.$SLUG.content-id" "$P/tasks/.gitkeep" "$P/inputs/.gitkeep" "$P/sources.md" README.md tools; do
  [ -e "$p" ] && paths+=("$p")
done
[ -n "$(ls -A "$P/outputs" 2>/dev/null)" ] && paths+=("$P/outputs")
git add -- "${paths[@]}"
git commit -q -m "daily-work: record $SLUG" -- "${paths[@]}" || refuse "git commit failed; README line updated but nothing committed"
rm -f "$SNAP"
telemetry event record "$PWD/$T"
content outcome "$PWD/$T"
python_note

echo "committed: $(git rev-parse --short HEAD) daily-work: record $SLUG"
echo "$P/README.md: $LINE"
echo "Left for a person to check:"
awk '/^Done looks like:$/ { on = 1; next } /^(Decided|Out of scope):$/ || /^## / { on = 0 } on && /^- / { print "  " $0 }' "$T"
