#!/usr/bin/env bash
# brief.sh <area> <slug>, with stdin: the title on line 1, then the description.
# Creates the area if new, then the task folder areas/<area>/tasks/<slug>/ with brief.md,
# inputs/ and outputs/, and indexes it in the area README.
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
T=$A/tasks/$SLUG
F=$T/brief.md
[ -e "$T" ] && refuse "$T already exists; nothing created"
export AREA SLUG DATE ASK TITLE

if [ ! -e "$A/README.md" ]; then
  fill "$TEMPLATES/area/README.md" "$A/README.md"
  [ -e "$A/sources.md" ] || fill "$TEMPLATES/area/sources.md" "$A/sources.md"
  echo "New area: $A/"
fi
grep -qE "^- $AREA(:|\$)" README.md 2>/dev/null || add_under README.md "## Areas" "- $AREA"

mkdir -p "$T/inputs" "$T/outputs"
: > "$T/inputs/.gitkeep"; : > "$T/outputs/.gitkeep"
fill "$TEMPLATES/brief/brief.md" "$F"
add_under "$A/README.md" "## Tasks" "- $DATE $SLUG: open"
echo "Created $F"
echo "Next: /grill-with-docs $F"
