---
name: init
description: >-
  /daily-work:init [dir]. Set up a daily-work repo: CLAUDE.md, README.md, .gitignore,
  .env.example, pyproject.toml, areas/_inbox/, and git init if needed. Never overwrites; an
  existing CLAUDE.md gets only missing ## sections, an existing .gitignore only missing lines.
  The session runs one script and edits nothing.
disable-model-invocation: true
argument-hint: "[dir]"
---

# Init

Run this one Bash command from the repo root, arguments as given (usually none):

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/init.sh" $ARGUMENTS
```

Print its output exactly as printed, one line per file, and end the turn on its last line.
Edit nothing yourself. Do not create CONTEXT.md. Never open or print .env.
