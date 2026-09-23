# <repo name>

## Purpose
<One paragraph, written by the owner: what this repo is for, who works in it, what kinds of
tasks land here.>

## Reading order
Before any task: CONTEXT.md if it exists, then the area's README.md, sources.md and CONTEXT.md
if it has one, then the task's task.md.

## Where things go
Work belongs to an area: areas/<area>/, a client, a system or a recurring responsibility.
Each task is a folder areas/<area>/tasks/<slug>/ with inputs/ and outputs/. It starts as
brief.md, a person's description of the task; grilling turns it into task.md. Client files
go in inputs/ and are never committed. What the task produces, code included, goes in
outputs/ and is committed. A method used twice becomes a skill in .claude/skills/. A script
used once stays in the task's outputs/; used twice, it moves to tools/.

## Before answering
State in one line: which sources you will use, what each term in the ask means (CONTEXT.md or
"undefined"), the scope, and the form of the output. An undefined term or a missing source is
the question to ask; nothing else is.

## When to grill
Run /grill-with-docs when the clarify line shows an undefined term or a missing source, or
when the ask is larger than one sitting. Otherwise the clarify line is enough.

## After a grilling session on a brief
Before ending, turn the brief into a task, in the same folder:
1. Write task.md next to brief.md, in exactly this layout:

   # <the brief's heading>

   Area: <area>
   Created: <today>

   ## Ask
   <the brief's text, unchanged, without its heading, Area and Written lines>

   ## Spec
   Purpose: <one line: who this is for and what they do with it>
   Done looks like:
   - <a check a person can confirm in under a minute>
   Decided:
   - stated: <what the asker said>
   - assumed: <what Claude chose, and why>
   Out of scope:
   - <what this task does not do>

   ## Result
   <written by /daily-work:record>

   ## Caveats
   <written by /daily-work:record>

2. Fill ## Spec with what was settled. Leave ## Result and ## Caveats as shown.
3. Delete brief.md.
4. Show the path of task.md.

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
