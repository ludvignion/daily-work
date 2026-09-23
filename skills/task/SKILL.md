---
name: task
description: >-
  /daily-work:task <areas/<area>/briefs/<slug>.md>. Turn a brief into a task folder
  areas/<area>/tasks/<date>-<slug>/ with task.md, inputs/ and outputs/, and write anything
  settled in this conversation into its Spec. Normally a grilling session does this itself
  (see CLAUDE.md); this is the fallback.
disable-model-invocation: true
argument-hint: "<areas/<area>/briefs/<slug>.md>"
---

# Task

The user typed: `$ARGUMENTS`

1. If that is empty, list the files in `areas/*/briefs/`, print them, and stop.
2. Run this one Bash command from the repo root:

   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/task.sh" <brief path>
   ```
   A refusal is one line starting "refused:"; print it and stop.
3. If this conversation settled anything about the task (a grilling session, answers to
   questions), write it into the new task.md under `## Spec`: Purpose, Done lines, Decided as
   stated or assumed, Out of scope. Change nothing else in task.md. If nothing was settled,
   leave the Spec as it is.
4. Print the script's output, then the Spec if you wrote one, and end with:
   `Next: tell Claude to work on <task folder>, then /daily-work:record <task folder>`

Do not start the task. Do not create CONTEXT.md. Never open or print .env.
