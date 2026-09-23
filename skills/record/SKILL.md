---
name: record
description: >-
  /daily-work:record [areas/<area>/tasks/<slug>]. Record a finished task: write
  ## Result and ## Caveats in its task.md from outputs/ and the conversation, add missing
  sources to the area's sources.md, mark the area README line done, commit, and list the Done
  lines a person still has to check. With no argument, list open tasks and stop.
disable-model-invocation: true
argument-hint: "[areas/<area>/tasks/<slug>]"
---

# Record

Arguments: `$ARGUMENTS`

Never open or print .env. Never create CONTEXT.md. Never edit `## Ask` or `## Spec`.

## No argument

Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/record.sh" list`, print its output, and stop.

## With a task folder

1. Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/record.sh" begin <task folder>`. On a line
   starting "refused:", print it and stop. Otherwise it names task.md, sources.md and the
   files in outputs/.
2. Read task.md, the area's sources.md, and every file listed under outputs. Use the
   conversation for what was done and why.
3. Edit task.md, replacing only the body under `## Result` and under `## Caveats`:
   - Result: what was produced and where (paths under outputs/), and the answer itself: the
     numbers, findings or recommendation, each tied to its source, slide or line.
   - Caveats: what was assumed, what could not be checked, which figures do not reconcile,
     which sources were missing or stale. Write "None." only if that is true.
   Only state what outputs/ or the conversation shows.
4. For each source the task used (a file, system, report or person) that is not already in
   sources.md, add one bullet in its format: `- <source>: <what it is, where it lives, what it
   is authoritative for>.` Change no existing bullet.
5. Run, with one line (under 80 characters) saying what the task produced:
   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/record.sh" finish <task folder> <<'DAILY_WORK_LINE'
   <one line>
   DAILY_WORK_LINE
   ```
   It refuses if `## Ask` or `## Spec` changed or a placeholder remains; fix your edit and
   rerun finish. Otherwise it marks the README line done, commits "daily-work: record
   <slug>", and prints the Done lines.
6. End on the script's output: the Done lines left for a person to check. If they still read
   `<a check a person can confirm in under a minute>`, say the Spec has no Done lines yet.
