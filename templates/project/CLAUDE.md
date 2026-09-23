# <repo name>

## Purpose
<One paragraph, written by the owner: what this repo is for, who works in it, what kinds of
tasks land here.>

## Reading order
Before any task: CONTEXT.md if it exists, then the area's README.md, sources.md and CONTEXT.md
if it has one, then the task's task.md.

## Where things go
Work belongs to an area: areas/<area>/, a client, a system or a recurring responsibility.
A brief is a person's description of a task, in areas/<area>/briefs/<slug>.md. A task is a
brief made clear enough to work on, in areas/<area>/tasks/<date>-<slug>/ with task.md,
inputs/ and outputs/. Client files go in inputs/ or the area's reference/ and are never
committed. What the task produces, code included, goes in outputs/ and is committed. A method
used twice becomes a skill in .claude/skills/. A script used once stays in the task's
outputs/; used twice, it moves to tools/.

## Before answering
State in one line: which sources you will use, what each term in the ask means (CONTEXT.md or
"undefined"), the scope, and the form of the output. An undefined term or a missing source is
the question to ask; nothing else is.

## When to grill
Run /grill-with-docs when the clarify line shows an undefined term or a missing source, or
when the ask is larger than one sitting. Otherwise the clarify line is enough.

## After a grilling session on a brief
Before ending, turn the brief into a task:
1. Create areas/<area>/tasks/<today>-<slug>/ with task.md, inputs/.gitkeep and
   outputs/.gitkeep. Use the same slug as the brief.
2. In task.md, keep the layout of the other task.md files: the brief's heading as the title,
   the brief's text unchanged under ## Ask, and what was settled under ## Spec: Done lines,
   Decided as stated or assumed, Out of scope. Leave ## Result and ## Caveats as they are.
3. Add "- <today> <slug>: open" under ## Tasks in the area's README.md.
4. Move the brief into the task folder as brief.md.
5. Show the path of task.md.
If the session ends before this, /daily-work:task on the brief does steps 1, 3 and 4.

## After a grilling session on a task
Write what was settled into that task's task.md under Spec: Done lines, Decided as stated or
assumed, Out of scope. Nothing settled in the session stays only in the session.

## Done
A Done line is something a person can confirm in under a minute. A number reconciles to a
named figure. A memo answers the questions in the Ask. A review points at the slide or line
for every finding.

## Finishing
Run /daily-work:record on the task folder. It writes Result and Caveats, updates the area
index, and names the Done lines left for a person to check.
