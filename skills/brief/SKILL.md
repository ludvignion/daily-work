---
name: brief
description: >-
  /daily-work:brief [project] <describe the task>. Rewrite a person's description of a task into
  a clear brief, find what is still open, show both for the person to verify, then write the
  brief to <project>/briefs/<task-name>.md for /mattpocock-skills:grill-with-docs, or, with
  nothing open, the task file straight away. Creates the project if new.
  Only when the person asks for it by name; never on your own.
argument-hint: "[project] <describe the task>"
---

# Brief

The user typed: `$ARGUMENTS`
If that line does not show the person's text, use what they wrote after the skill name.

`<plugin>` in the commands below is the daily-work plugin folder, the one that holds `scripts/`
and `skills/`; this file is `<plugin>/skills/brief/SKILL.md`. Write it as an absolute path.
Run this skill only when the person's own message asks for it by name. Never start it yourself,
not even when the work looks finished; ask the person instead.

1. **Project.** The projects are the folders at the repo root that hold a `tasks/` folder;
   list them. If the first word of the text is one of them, that is the project and the rest
   is the description. Otherwise ask the user which project, listing the existing ones and,
   when the first word is a valid name (`a-z`, `0-9`, `-`), offering it as a new project.
   Wait for the answer. Projects are lowercase, `a-z`, `0-9` and `-` only. If the description
   is empty, print `usage: /daily-work:brief [project] <describe the task>` and stop.
2. **Rewrite.** Turn the description into a brief that someone else could read cold:
   - one short paragraph: what is wanted, for whom, and why;
   - then, only for what the description says: `Input:`, `Output:`, `Constraints:` lines;
   - fix spelling and grammar, remove repetition, keep the person's terms (e.g. "UNS");
   - add nothing the description does not say, and do not settle anything it leaves open.
     Open points stay open; grilling settles them.
   If the description is about changing something the project already produced, list the
   project's `outputs/` and write the line `Output: update outputs/<file>` naming the
   existing file. If more than one file could be meant, write `Output: update an existing
   output (which one is open)` and list the candidates. Such a brief is a new task on an
   existing output; it never asks for a copy or a new file. The task it **builds on** is the
   one in the project's `tasks/` whose `## Result` names that file; if several do, that is an
   open point (step 3).
   Also write a **title** (a short heading, 3 to 8 words, sentence case) and a **task name** (2 to
   4 lowercase words joined by hyphens, only `a-z`, `0-9`, `-`, e.g. `uns-mockup`) that no
   file in the project's `briefs/` or `tasks/` already has.
3. **Find what is open.** The aim: a grill that asks only what is not yet settled, or no grill
   when nothing is. Check the brief against the glossary (CONTEXT.md or GLOSSARY.md), the
   project's sources.md and inputs/, the task it builds on (its Spec, Result and Caveats) and
   the output it changes. An open point is something the work cannot go ahead without:
   - a term none of them defines;
   - a fact no source in sources.md or inputs/ holds;
   - a choice the brief leaves open that changes the output (which file, what scope, which
     version wins);
   - for a task with nothing to build on, what Done looks like.
   A point settled in the earlier task's Spec and not changed by the brief is not open, and
   neither is a fact you can look up yourself. Write each open point as one numbered line
   saying what is open and why.
   With no open points, draft the Spec instead, in the layout AGENTS.md gives under "After a
   grilling session on a brief": the earlier task's Spec with this change in it, or, with
   nothing to build on, what the brief settles. Every Done line checks this task's change.
4. **Verify.** Show the project, the title, the task name, the task it builds on (if any), the
   rewritten brief, and then either:
   - the open points, and ask: "Write this brief for grilling, or what should change?"
   - or the drafted Spec, and ask: "Nothing is open. Skip the grill and write the task, grill
     anyway, or what should change?"
   Wait for the answer. Revise and show it again until the person approves. Write nothing
   before that. The open points are a suggestion; grilling anyway is the person's call.
5. On approval, run one command from the repo root. Put the title on the first heredoc line
   and the approved brief, unchanged, on the lines after it. Add `<builds-on>`, the earlier
   task's name, only when there is one.
   - To grill (open points, or the person chose grill anyway), end the heredoc with the open
     points, or "None found.", under `## Open points`:

     ```
     bash "<plugin>/scripts/brief.sh" <project> <task-name> [<builds-on>] <<'DAILY_WORK_ARGS'
     <title>
     <approved brief>

     ## Open points
     <the numbered open points, or None found.>
     DAILY_WORK_ARGS
     ```
   - To skip the grill, end it with the approved Spec under `## Spec`:

     ```
     bash "<plugin>/scripts/brief.sh" --no-grill <project> <task-name> [<builds-on>] <<'DAILY_WORK_ARGS'
     <title>
     <approved brief>

     ## Spec
     <the approved Spec>
     DAILY_WORK_ARGS
     ```
6. Print its output exactly as printed and end the turn on its last line. A refusal is one
   line starting "refused:"; print it and stop.

Edit nothing yourself and do not start the task. Do not create CONTEXT.md or GLOSSARY.md. Never open or
print .env.
