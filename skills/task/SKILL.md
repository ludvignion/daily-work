---
name: task
description: >-
  /daily-work:task [area] <slug> [ask]. Create a task folder areas/<area>/tasks/<today>-<slug>/
  with task.md, inputs/ and outputs/, creating the area if new and indexing both. One word is a
  slug in areas/_inbox/. Text after the slug becomes the Ask. The session runs one script and
  edits nothing.
disable-model-invocation: true
argument-hint: "[area] <slug> [ask]"
---

# Task

Run this one Bash command from the repo root. Put the arguments between the heredoc lines
exactly as given, unquoted and unchanged:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/task.sh" <<'DAILY_WORK_ARGS'
$ARGUMENTS
DAILY_WORK_ARGS
```

Print its output exactly as printed and end the turn on its last line. A refusal is one line
starting "refused:"; print it and stop. Edit nothing yourself, and do not start the task.
Do not create CONTEXT.md. Never open or print .env.
