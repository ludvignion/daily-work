#!/usr/bin/env bash
# task.sh <slug>, with stdin: the title on line 1, then the text the user typed.
# The text becomes the Ask; "--area <name>" in it files the task under that area
# instead of areas/_inbox/.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

SLUG=${1:-}
IFS= read -r TITLE || true
RAW=$(cat)
AREA=_inbox
if [[ $RAW =~ (^|[[:space:]])--area[[:space:]]+([^[:space:]]+) ]]; then
  AREA=${BASH_REMATCH[2]}
  RAW=${RAW/"${BASH_REMATCH[0]}"/}
fi
ASK=$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' <<< "$RAW")

[ -n "$ASK" ] || refuse "usage: /daily-work:task <what the task is> [--area <name>]"
[[ $SLUG =~ $SLUG_RE ]] || refuse "slug '$SLUG' has characters outside [a-z0-9-]; nothing created"
[[ $AREA == _inbox || $AREA =~ $SLUG_RE ]] || refuse "area '$AREA' has characters outside [a-z0-9-]; nothing created"
[ -d areas ] || refuse "no areas/ here; run /daily-work:init first"
TITLE=${TITLE:-$SLUG}

DATE=${DAILY_WORK_DATE:-$(date +%F)}
A=areas/$AREA
T=$A/tasks/$DATE-$SLUG
[ -e "$T" ] && refuse "$T already exists; nothing created"
export AREA SLUG DATE ASK TITLE

new_area=
for f in README.md sources.md; do
  [ -e "$A/$f" ] || { fill "$TEMPLATES/area/$f" "$A/$f"; new_area=1; }
done
[ -e "$A/reference/.gitkeep" ] || { mkdir -p "$A/reference"; : > "$A/reference/.gitkeep"; }
[ -n "$new_area" ] && [ "$AREA" != _inbox ] && echo "New area: $A/"

mkdir -p "$T/inputs" "$T/outputs"
: > "$T/inputs/.gitkeep"; : > "$T/outputs/.gitkeep"
fill "$TEMPLATES/task/task.md" "$T/task.md"
add_under "$A/README.md" "## Tasks" "- $DATE $SLUG: open"
grep -qE "^- $AREA(:|\$)" README.md 2>/dev/null || add_under README.md "## Areas" "- $AREA"

echo "Task: $TITLE"
echo "File: $T/task.md"
echo "Put source files in $T/inputs/"
echo "Next: /grill-with-docs on $T/task.md to write the Spec, or tell Claude to work on it if the Ask is already clear"
