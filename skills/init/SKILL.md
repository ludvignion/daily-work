---
name: init
description: >-
  /daily-work:init [dir]. Set up a daily-work repo: AGENTS.md, README.md, .gitignore, .env.example,
  pyproject.toml, .claude/settings.json, tools/, git init if needed, and on a yes uv and a
  Python for the plugin. Never overwrites; an existing AGENTS.md gets only missing ## sections,
  an existing .gitignore only missing lines, an existing CLAUDE.md only the @AGENTS.md line.
  The session runs scripts and edits nothing.
  Only when the person asks for it by name; never on your own.
argument-hint: "[dir]"
---

# Init

`<plugin>` in the commands below is the daily-work plugin folder, the one that holds `scripts/`
and `skills/`; this file is `<plugin>/skills/init/SKILL.md`. Write it as an absolute path.
Run this skill only when the person's own message asks for it by name. Never start it yourself,
not even when the work looks finished; ask the person instead.

Run this one command from the repo root, with the arguments the person gave (usually none):

```
bash "<plugin>/scripts/init.sh" $ARGUMENTS
```

Print its output exactly as printed, one line per file.

If its `python:` line says `missing`, ask the person exactly this and wait for the answer:
"daily-work records its runs with Python, through uv. Install uv and a Python for it now? It
takes a minute and needs nothing else from you. (yes/no)". On yes, run
`bash "<plugin>/scripts/setup-python.sh"` and print its last line. On no, say that telemetry
and content logging stay off until init is run again and answered yes.

End the turn on the last line printed. Edit nothing yourself. Do not create CONTEXT.md or GLOSSARY.md. Never open or print .env.
