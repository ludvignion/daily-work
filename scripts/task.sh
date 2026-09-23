#!/usr/bin/env bash
# Create a task folder. Reads the raw arguments on stdin: "[area] <slug> [ask...]".
# One word is a slug in _inbox; two or more are area, slug, then the Ask.
# To give an Ask to an _inbox task, name the area: "_inbox <slug> <ask>".
set -euo pipefail
source "$(dirname "$0")/lib.sh"

ltrim() { local s=$1; printf '%s' "${s#"${s%%[![:space:]]*}"}"; }
s=$(ltrim "$(cat)")
w1=${s%%[[:space:]]*}
r=$(ltrim "${s#"$w1"}")
w2=${r%%[[:space:]]*}
ASK=$(ltrim "${r#"$w2"}"); ASK=${ASK%"${ASK##*[![:space:]]}"}
if [ -z "$w2" ]; then AREA=_inbox SLUG=$w1; else AREA=$w1 SLUG=$w2; fi

[ -n "$SLUG" ] || refuse "usage: /daily-work:task [area] <slug> [ask]"
[[ $SLUG =~ $SLUG_RE ]] || refuse "slug '$SLUG' has characters outside [a-z0-9-]; nothing created"
[[ $AREA == _inbox || $AREA =~ $SLUG_RE ]] || refuse "area '$AREA' has characters outside [a-z0-9-]; nothing created"
[ -d areas ] || refuse "no areas/ here; run /daily-work:init first"

DATE=${DAILY_WORK_DATE:-$(date +%F)}
A=areas/$AREA
T=$A/tasks/$DATE-$SLUG
[ -e "$T" ] && refuse "$T already exists; nothing created"
export AREA SLUG DATE ASK

for f in README.md sources.md; do
  [ -e "$A/$f" ] || { fill "$TEMPLATES/area/$f" "$A/$f"; echo "$A/$f: created"; }
done
[ -e "$A/reference/.gitkeep" ] || { mkdir -p "$A/reference"; : > "$A/reference/.gitkeep"; echo "$A/reference/.gitkeep: created"; }

mkdir -p "$T/inputs" "$T/outputs"
: > "$T/inputs/.gitkeep"; : > "$T/outputs/.gitkeep"
fill "$TEMPLATES/task/task.md" "$T/task.md"
echo "$T/: created with task.md, inputs/, outputs/"

add_under "$A/README.md" "## Tasks" "- $DATE $SLUG: open"
echo "$A/README.md: added \"- $DATE $SLUG: open\""
if ! grep -qE "^- $AREA(:|\$)" README.md 2>/dev/null; then
  add_under README.md "## Areas" "- $AREA"
  echo "README.md: added \"- $AREA\""
fi

echo "Next: write the Ask in $T/task.md, then follow ## Before answering in CLAUDE.md"
