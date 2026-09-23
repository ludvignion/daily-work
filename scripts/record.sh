#!/usr/bin/env bash
# record.sh list             tasks whose area README line says "open"
# record.sh begin <task>     check the task, snapshot Ask and Spec, list what to read
# record.sh finish <task>    one-line summary on stdin; verify Ask and Spec unchanged,
#                            mark the README line done, commit, print the Done lines
set -euo pipefail
source "$(dirname "$0")/lib.sh"

if [ "${1:-}" = list ]; then
  n=0
  for f in areas/*/README.md; do
    [ -f "$f" ] || continue
    a=$(basename "$(dirname "$f")")
    while read -r _ _ s; do
      echo "areas/$a/tasks/${s%:}"; n=$((n + 1))
    done < <(grep -E '^- [0-9]{4}-[0-9]{2}-[0-9]{2} [a-z0-9-]+: open$' "$f" || true)
  done
  [ "$n" -gt 0 ] || echo "no open tasks"
  exit 0
fi

MODE=${1:-}; T=${2:-}
[[ $MODE == begin || $MODE == finish ]] || refuse "usage: record.sh list | begin <task> | finish <task>"
T=${T%/}; T=${T#"$PWD/"}; T=${T#./}
[[ $T =~ ^areas/([^/]+)/tasks/([a-z0-9-]+)$ ]] || refuse "'$T' is not areas/<area>/tasks/<slug>"
AREA=${BASH_REMATCH[1]} SLUG=${BASH_REMATCH[2]}
A=areas/$AREA
[ -f "$T/task.md" ] || { [ -f "$T/brief.md" ] && refuse "$T has only brief.md; grill it into task.md first"; refuse "$T/task.md not found"; }
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || refuse "not a git repo"
SNAP=$GIT_DIR/daily-work/$AREA-$SLUG.spec

ask_spec() { awk '/^## Ask$/ { on = 1 } /^## (Result|Caveats)$/ { on = 0 } on' "$T/task.md"; }

if [ "$MODE" = begin ]; then
  mkdir -p "$(dirname "$SNAP")"; ask_spec > "$SNAP"
  echo "task: $T/task.md"
  echo "sources: $A/sources.md"
  out=$(find "$T/outputs" -type f ! -name .gitkeep 2>/dev/null | sort)
  if [ -n "$out" ]; then echo "outputs:"; sed 's/^/  /' <<< "$out"; else echo "outputs: none"; fi
  exit 0
fi

[ -f "$SNAP" ] || refuse "run record.sh begin $T first"
ask_spec | cmp -s - "$SNAP" || refuse "## Ask or ## Spec in $T/task.md changed since begin; restore them, nothing committed"
grep -qF '<written by /daily-work:record>' "$T/task.md" && refuse "## Result or ## Caveats still holds the placeholder"
SUM=$(tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')
[ -n "$SUM" ] || refuse "no one-line summary on stdin"

# Keep the date already on the README line; a task without one takes its Created date.
RE="^- ([0-9]{4}-[0-9]{2}-[0-9]{2}) $SLUG:"
DATE=$(grep -oE "$RE" "$A/README.md" | head -1 | cut -d' ' -f2)
[ -n "$DATE" ] || DATE=$(sed -n 's/^Created: //p' "$T/task.md" | head -1)
LINE="- $DATE $SLUG: done, $SUM"
if grep -qE "$RE" "$A/README.md"; then
  RE="$RE" LINE="$LINE" awk '$0 ~ ENVIRON["RE"] { print ENVIRON["LINE"]; next } { print }' \
    "$A/README.md" > "$A/README.md.tmp" && mv "$A/README.md.tmp" "$A/README.md"
else
  add_under "$A/README.md" "## Tasks" "$LINE"
fi

paths=("$T" "$A/README.md")
for p in "$A/sources.md" README.md tools; do [ -e "$p" ] && paths+=("$p"); done
git add -- "${paths[@]}"
git commit -q -m "daily-work: record $SLUG" -- "${paths[@]}" || refuse "git commit failed; README line updated but nothing committed"
rm -f "$SNAP"

echo "committed: $(git rev-parse --short HEAD) daily-work: record $SLUG"
echo "$A/README.md: $LINE"
echo "Left for a person to check:"
awk '/^Done looks like:$/ { on = 1; next } /^(Decided|Out of scope):$/ || /^## / { on = 0 } on && /^- / { print "  " $0 }' "$T/task.md"
