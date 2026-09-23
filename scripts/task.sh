#!/usr/bin/env bash
# task.sh <brief>: turn areas/<area>/briefs/<slug>.md into a task folder
# areas/<area>/tasks/<date>-<slug>/ with task.md (the brief's text as the Ask), inputs/ and
# outputs/, move the brief in as brief.md, and index the task in the area README.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

F=${1:-}; F=${F#"$PWD/"}; F=${F#./}
[[ $F =~ ^areas/([a-z0-9-]+)/briefs/([a-z0-9-]+)\.md$ ]] \
  || refuse "'$F' is not areas/<area>/briefs/<slug>.md"
AREA=${BASH_REMATCH[1]} SLUG=${BASH_REMATCH[2]}
[ -f "$F" ] || refuse "$F not found"

DATE=${DAILY_WORK_DATE:-$(date +%F)}
A=areas/$AREA
T=$A/tasks/$DATE-$SLUG
[ -e "$T" ] && refuse "$T already exists; nothing created"
TITLE=$(sed -n 's/^# //p' "$F" | head -1)
TITLE=${TITLE:-$SLUG}
# The Ask is the brief without its heading, Area and Written lines.
ASK=$(awk 'NR == 1 && /^# / { next } /^(Area|Written): / { next } { print }' "$F" \
  | sed '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}')
[ -n "$ASK" ] || refuse "$F has no description"
export AREA SLUG DATE ASK TITLE

mkdir -p "$T/inputs" "$T/outputs"
: > "$T/inputs/.gitkeep"; : > "$T/outputs/.gitkeep"
fill "$TEMPLATES/task/task.md" "$T/task.md"
if git ls-files --error-unmatch "$F" >/dev/null 2>&1; then git mv "$F" "$T/brief.md"; else mv "$F" "$T/brief.md"; fi
rmdir "$A/briefs" 2>/dev/null || true
add_under "$A/README.md" "## Tasks" "- $DATE $SLUG: open"

echo "Created $T/task.md (client files go in $T/inputs/):"
echo
cat "$T/task.md"
