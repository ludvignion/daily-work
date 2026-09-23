# <repo name>

## Purpose
<One paragraph, written by the owner: what this repo is for, who works in it, what kinds of
tasks land here.>

## Reading order
Before any task: CONTEXT.md if it exists, then the area's README.md, sources.md and CONTEXT.md
if it has one, then the task's task.md.

## Where things go
A task is a folder under areas/<area>/tasks/. A task with no area yet goes to areas/_inbox/
and moves later with git mv. Its inputs and outputs stay inside it. A method used twice
becomes a skill in .claude/skills/. A script used once stays in the task folder; used twice,
it moves to tools/.

## Before answering
State in one line: which sources you will use, what each term in the ask means (CONTEXT.md or
"undefined"), the scope, and the form of the output. An undefined term or a missing source is
the question to ask; nothing else is.

## When to grill
Run /grill-with-docs when the clarify line shows an undefined term or a missing source, or
when the ask is larger than one sitting. Otherwise the clarify line is enough.

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
