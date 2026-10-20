#!/usr/bin/env bash
# brief.sh <project> <task-name>, with stdin: the title on line 1, then the description.
# Creates the project if new (README.md, sources.md, tasks/, inputs/, outputs/), then writes
# <project>/briefs/<task-name>.md and indexes the task in the project README.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

PROJECT=${1:-} SLUG=${2:-}
IFS= read -r TITLE || true
ASK=$(sed 's/[[:space:]]*$//' | sed '/./,$!d')

[[ $PROJECT =~ $SLUG_RE ]] || refuse "project '$PROJECT' has characters outside [a-z0-9-]; nothing created"
[[ $SLUG =~ $SLUG_RE ]] || refuse "task name '$SLUG' has characters outside [a-z0-9-]; nothing created"
[ -n "$ASK" ] || refuse "usage: /daily-work:brief <project> <describe the task>"
[ -f AGENTS.md ] || refuse "no AGENTS.md here; run /daily-work:init first"

DATE=${DAILY_WORK_DATE:-$(date +%F)}
TITLE=${TITLE:-$SLUG}
P=$PROJECT
F=$P/briefs/$SLUG.md
T=$P/tasks/$SLUG.md
# A project is a folder with tasks/ in it; tools/, docs/ and the like are not.
[ -e "$P" ] && [ ! -d "$P/tasks" ] && refuse "$P/ exists and is not a project; nothing created"
[ -e "$F" ] && refuse "$F already exists; nothing created"
[ -e "$T" ] && refuse "$T already exists; nothing created"
# A random id for usage telemetry (README "Telemetry"); says nothing about the task.
ID=$(new_uuid)
[[ $ID =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || refuse "could not make a task id from /dev/urandom; nothing created"
export PROJECT SLUG DATE ASK TITLE ID

if [ ! -d "$P/tasks" ]; then
  fill "$TEMPLATES/project/README.md" "$P/README.md"
  fill "$TEMPLATES/project/sources.md" "$P/sources.md"
  for d in tasks inputs outputs; do mkdir -p "$P/$d"; : > "$P/$d/.gitkeep"; done
  echo "New project: $P/"
fi
grep -qE "^- $PROJECT(:|\$)" README.md 2>/dev/null || add_under README.md "## Projects" "- $PROJECT"

fill "$TEMPLATES/brief/brief.md" "$F"
add_under "$P/README.md" "## Tasks" "- $DATE $SLUG: open"
telemetry event brief "$PWD/$T"
content created "$PWD/$T"
echo "Created $F"
python_note
# Claude Code names the skill by its plugin; other agents run it by its own name.
if [ -n "${CLAUDECODE:-}" ]; then echo "Next: /mattpocock-skills:grill-with-docs $F"
else echo "Next: run the grill-with-docs skill on $F"; fi
