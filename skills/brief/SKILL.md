---
name: brief
description: >-
  /daily-work:brief [area] <describe the task>. Write a person's description of a task to
  areas/<area>/briefs/<slug>.md, ready for /grill-with-docs, creating the area if new. The
  session picks the area, a heading and a file name, runs one script, and edits nothing.
disable-model-invocation: true
argument-hint: "[area] <describe the task>"
---

# Brief

The user typed: `$ARGUMENTS`

1. **Area.** List the folders in `areas/`. If the first word of the text is one of them, that
   is the area and the rest is the description. Otherwise ask the user which area, listing
   the existing ones and, when the first word is a valid name (`a-z`, `0-9`, `-`), offering
   it as a new area. Wait for the answer. Areas are lowercase, `a-z`, `0-9` and `-` only.
2. **Title and slug.** From the description, write a **title** (a short heading, 3 to 8
   words, sentence case, one line) and a **slug** (2 to 4 lowercase words joined by hyphens,
   only `a-z`, `0-9`, `-`, e.g. `uns-mockup`).
   If the description is empty, print `usage: /daily-work:brief [area] <describe the task>`
   and stop.
3. Run this one Bash command from the repo root. Put the title on the first heredoc line and
   the description, exactly as typed and unchanged, on the lines after it:

   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/brief.sh" <area> <slug> <<'DAILY_WORK_ARGS'
   <title>
   <description>
   DAILY_WORK_ARGS
   ```
4. Print its output exactly as printed, the brief included, and end the turn on its last
   line. A refusal is one line starting "refused:"; print it and stop.

Edit nothing yourself and do not start the task. Do not create CONTEXT.md. Never open or
print .env.
