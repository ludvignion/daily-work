---
name: brief
description: >-
  /daily-work:brief [area] <describe the task>. Rewrite a person's description of a task into
  a clear brief, show it for the person to verify, then write it to
  areas/<area>/tasks/<slug>/brief.md, ready for /grill-with-docs, creating the area if new.
disable-model-invocation: true
argument-hint: "[area] <describe the task>"
---

# Brief

The user typed: `$ARGUMENTS`

1. **Area.** List the folders in `areas/`. If the first word of the text is one of them, that
   is the area and the rest is the description. Otherwise ask the user which area, listing
   the existing ones and, when the first word is a valid name (`a-z`, `0-9`, `-`), offering
   it as a new area. Wait for the answer. Areas are lowercase, `a-z`, `0-9` and `-` only.
   If the description is empty, print `usage: /daily-work:brief [area] <describe the task>`
   and stop.
2. **Rewrite.** Turn the description into a brief that someone else could read cold:
   - one short paragraph: what is wanted, for whom, and why;
   - then, only for what the description says: `Input:`, `Output:`, `Constraints:` lines;
   - fix spelling and grammar, remove repetition, keep the person's terms (e.g. "UNS");
   - add nothing the description does not say, and do not settle anything it leaves open.
     Open points stay open; grilling settles them.
   Also write a **title** (a short heading, 3 to 8 words, sentence case) and a **slug** (2 to
   4 lowercase words joined by hyphens, only `a-z`, `0-9`, `-`, e.g. `uns-mockup`).
3. **Verify.** Show the area, the title, the slug and the rewritten brief, and ask: "Write
   this brief, or what should change?" Wait for the answer. Revise and show it again until
   the person approves. Write nothing before that.
4. On approval, run this one Bash command from the repo root. Put the title on the first
   heredoc line and the approved brief, unchanged, on the lines after it:

   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/brief.sh" <area> <slug> <<'DAILY_WORK_ARGS'
   <title>
   <approved brief>
   DAILY_WORK_ARGS
   ```
5. Print its output exactly as printed and end the turn on its last line. A refusal is one
   line starting "refused:"; print it and stop.

Edit nothing yourself and do not start the task. Do not create CONTEXT.md. Never open or
print .env.
