#!/usr/bin/env bash
# brief.sh [--no-grill] <project> <task-name> [<builds-on>], with stdin: the title on line 1,
# then the description. <builds-on> names an earlier task in the project whose output this one
# changes.
# Creates the project if new (README.md, sources.md, tasks/, inputs/, outputs/) and indexes the
# task in the project README. Then:
#   without --no-grill: writes <project>/briefs/<task-name>.md, for grilling; its description
#                       may end in a "## Open points" section, what the grill starts from.
#   with --no-grill:    writes <project>/tasks/<task-name>.md straight away, for a brief with no
#                       open points; the description ends in a "## Spec" section.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

NO_GRILL=
[ "${1:-}" = --no-grill ] && { NO_GRILL=1; shift; }
PROJECT=${1:-} SLUG=${2:-} BUILDS_ON=${3:-}
IFS= read -r TITLE || true
TEXT=$(sed 's/[[:space:]]*$//' | sed '/./,$!d')
# With --no-grill the text splits at its "## Spec" line: the Ask above it, the Spec below.
if [ -n "$NO_GRILL" ]; then
  ASK=$(awk '/^## Spec$/ { exit } { print }' <<< "$TEXT")
  SPEC=$(awk 'on { print } /^## Spec$/ { on = 1 }' <<< "$TEXT" | sed '/./,$!d')
else
  ASK=$TEXT SPEC=
fi

[[ $PROJECT =~ $SLUG_RE ]] || refuse "project '$PROJECT' has characters outside [a-z0-9-]; nothing created"
[[ $SLUG =~ $SLUG_RE ]] || refuse "task name '$SLUG' has characters outside [a-z0-9-]; nothing created"
[ -n "$ASK" ] || refuse "usage: /daily-work:brief <project> <describe the task>"
[ -f AGENTS.md ] || refuse "no AGENTS.md here; run /daily-work:init first"
if [ -n "$NO_GRILL" ]; then
  [ -n "$SPEC" ] || refuse "--no-grill needs a ## Spec section after the description; nothing created"
  # record lists the Done lines for a person to check, so a task without them cannot be recorded.
  awk '/^Done looks like:$/ { on = 1; next } /^(Decided|Out of scope):$/ { on = 0 } on && /^- / { n++ } END { exit !n }' <<< "$SPEC" \
    || refuse "the Spec has no Done looks like: lines; grill the brief instead; nothing created"
fi

DATE=${DAILY_WORK_DATE:-$(date +%F)}
TITLE=${TITLE:-$SLUG}
P=$PROJECT
F=$P/briefs/$SLUG.md
T=$P/tasks/$SLUG.md
# A project is a folder with tasks/ in it; tools/, docs/ and the like are not.
[ -e "$P" ] && [ ! -d "$P/tasks" ] && refuse "$P/ exists and is not a project; nothing created"
[ -e "$F" ] && refuse "$F already exists; nothing created"
[ -e "$T" ] && refuse "$T already exists; nothing created"
if [ -n "$BUILDS_ON" ]; then
  [[ $BUILDS_ON =~ $SLUG_RE ]] || refuse "builds-on '$BUILDS_ON' has characters outside [a-z0-9-]; nothing created"
  [ -f "$P/tasks/$BUILDS_ON.md" ] || refuse "builds-on: $P/tasks/$BUILDS_ON.md not found; nothing created"
  BUILDS_ON=tasks/$BUILDS_ON.md
fi
# A random id for usage telemetry (README "Telemetry"); says nothing about the task.
ID=$(new_uuid)
[[ $ID =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || refuse "could not make a task id from /dev/urandom; nothing created"
export PROJECT SLUG DATE ASK SPEC TITLE ID BUILDS_ON

if [ ! -d "$P/tasks" ]; then
  fill "$TEMPLATES/project/README.md" "$P/README.md"
  fill "$TEMPLATES/project/sources.md" "$P/sources.md"
  for d in tasks inputs outputs; do mkdir -p "$P/$d"; : > "$P/$d/.gitkeep"; done
  echo "New project: $P/"
fi
grep -qE "^- $PROJECT(:|\$)" README.md 2>/dev/null || add_under README.md "## Projects" "- $PROJECT"

if [ -n "$NO_GRILL" ]; then
  fill "$TEMPLATES/task/task.md" "$T"
  add_under "$P/README.md" "## Tasks" "- $DATE $SLUG: open"
  telemetry event brief "$PWD/$T"
  telemetry event grill "$PWD/$T" skipped
  content created "$PWD/$T"
  echo "Created $T"
  python_note
  echo "Next: work on $SLUG"
  exit 0
fi

fill "$TEMPLATES/brief/brief.md" "$F"
add_under "$P/README.md" "## Tasks" "- $DATE $SLUG: open"
telemetry event brief "$PWD/$T"
content created "$PWD/$T"
echo "Created $F"
python_note
# Claude Code names the skill by its plugin; other agents run it by its own name.
if [ -n "${CLAUDECODE:-}" ]; then echo "Next: /mattpocock-skills:grill-with-docs $F"
else echo "Next: run the grill-with-docs skill on $F"; fi
