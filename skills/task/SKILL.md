---
name: task
description: >-
  /daily-work:task <what the task is> [--area <name>]. Create a task folder with task.md (a
  heading, the Ask in the user's words, an empty Spec), inputs/ and outputs/. Without --area
  it goes to areas/_inbox/. The session picks a heading and a folder name, runs one script,
  and edits nothing.
disable-model-invocation: true
argument-hint: "<what the task is> [--area <name>]"
---

# Task

The user typed: `$ARGUMENTS`

1. From that text, write:
   - a **title**: a short heading for the task, 3 to 8 words, sentence case, one line.
   - a **slug**: 2 to 4 lowercase words joined by hyphens, only `a-z`, `0-9`, `-`
     (e.g. `uns-mockup`, `q3-revenue-check`).
   If the text is empty, print `usage: /daily-work:task <what the task is> [--area <name>]`
   and stop.
2. Run this one Bash command from the repo root. Put the title on the first heredoc line and
   the user's text, exactly as typed and unchanged, on the lines after it:

   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/task.sh" <slug> <<'DAILY_WORK_ARGS'
   <title>
   $ARGUMENTS
   DAILY_WORK_ARGS
   ```
3. Print its output exactly as printed and end the turn on its last line. A refusal is one
   line starting "refused:"; print it and stop.

Edit nothing yourself and do not start the task. Do not create CONTEXT.md. Never open or
print .env.
