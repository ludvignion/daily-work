#!/usr/bin/env bash
# brief.sh <area> <slug>, with stdin: the title on line 1, then the description.
# Creates the area if new and writes areas/<area>/briefs/<slug>.md.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

AREA=${1:-} SLUG=${2:-}
IFS= read -r TITLE || true
ASK=$(sed 's/[[:space:]]*$//' | sed '/./,$!d')

[[ $AREA =~ $SLUG_RE ]] || refuse "area '$AREA' has characters outside [a-z0-9-]; nothing created"
[[ $SLUG =~ $SLUG_RE ]] || refuse "slug '$SLUG' has characters outside [a-z0-9-]; nothing created"
[ -n "$ASK" ] || refuse "usage: /daily-work:brief <area> <describe the task>"
[ -d areas ] || refuse "no areas/ here; run /daily-work:init first"

DATE=${DAILY_WORK_DATE:-$(date +%F)}
TITLE=${TITLE:-$SLUG}
A=areas/$AREA
F=$A/briefs/$SLUG.md
[ -e "$F" ] && refuse "$F already exists; nothing created"
[ -e "$A/tasks/$SLUG" ] && refuse "a task named $SLUG already exists in $A/tasks/; pick another name"
export AREA SLUG DATE ASK TITLE

if [ ! -e "$A/README.md" ]; then
  fill "$TEMPLATES/area/README.md" "$A/README.md"
  [ -e "$A/sources.md" ] || fill "$TEMPLATES/area/sources.md" "$A/sources.md"
  mkdir -p "$A/reference" "$A/tasks"; : > "$A/reference/.gitkeep"
  echo "New area: $A/"
fi
grep -qE "^- $AREA(:|\$)" README.md 2>/dev/null || add_under README.md "## Areas" "- $AREA"

fill "$TEMPLATES/brief/brief.md" "$F"
echo "Created $F"
echo "Next: /grill-with-docs $F"
