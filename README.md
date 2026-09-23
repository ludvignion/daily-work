# daily-work

A Claude Code plugin that gives a repo a structure for ad-hoc white-collar work: reading decks,
evaluating documents, pulling and checking numbers, writing memos. Work is grouped in areas (a
client, a system, a recurring responsibility); each task is a folder inside an area. The plugin
creates the structure, creates tasks, and records what was done. Nothing here builds software.

Local filesystem and git only. No network calls. The plugin never opens `.env`.

## Install

Load it for one session from a local checkout:

```
claude --plugin-dir /path/to/daily-work
```

Or add this repo to a plugin marketplace you use and install it with `/plugin install`.

Then, in the repo you keep for daily work:

```
/daily-work:init
```

## The per-task loop

1. **Task.** Say what the task is in plain words:
   `/daily-work:task Creating a visual mock-up for alternative UNS structures`
   Claude picks a heading and a folder name, and the plugin creates
   `areas/_inbox/tasks/<today>-uns-mockup/task.md` with the heading, your words as the Ask,
   and an empty Spec. Put source files in its `inputs/`.
2. **Grill, when the Ask is not yet clear.** Run `/grill-with-docs` on that task.md. It asks
   the questions that turn the Ask into a Spec: Done lines, what was decided, what is out of
   scope. What gets settled is written into `## Spec`. A task whose Ask is already clear
   skips this.
3. **Hand over.** Tell Claude to work on the task folder. It reads CLAUDE.md, the area and
   task.md, states a one-line clarify (sources, terms, scope, form of output), then works.
   Results go in `outputs/`.
4. **Record.** `/daily-work:record areas/_inbox/tasks/<date>-uns-mockup` writes Result and
   Caveats, marks the task done, commits, and lists the Done lines a person still has to
   check.

Areas are optional. A task without one lands in `areas/_inbox/`. Add `--area <name>` (a
client, a system, a recurring responsibility) to file it there instead, or move an inbox task
later with `git mv`.

## Skills

All three are user-invoked only.

- **`/daily-work:init [dir]`** — creates `CLAUDE.md`, `README.md`, `.gitignore`,
  `.env.example`, `pyproject.toml` and `areas/_inbox/.gitkeep`, and runs `git init` if the
  directory is not in a repo. Prints `copied` or `skipped` per file. Never overwrites: an
  existing `CLAUDE.md` gets only the template's missing `##` sections, an existing
  `.gitignore` only its missing lines. Safe to re-run.
- **`/daily-work:task <what the task is> [--area <name>]`** — Claude turns the text into a
  heading and a folder name (`[a-z0-9-]`); the script creates the task folder with `task.md`,
  `inputs/` and `outputs/`, and the area (`README.md`, `sources.md`, `reference/`) if new. It
  adds `- <date> <slug>: open` under `## Tasks` in the area README and the area under
  `## Areas` in the root README.
- **`/daily-work:record [task folder]`** — fills `## Result` and `## Caveats` from `outputs/`
  and the conversation, adds any missing source to the area's `sources.md`, changes the README
  line to `- <date> <slug>: done, <one line>`, commits `daily-work: record <slug>`, and prints
  the Done lines left to check. It refuses to commit if `## Ask` or `## Spec` changed. With no
  argument it lists open tasks.

`inputs/`, `outputs/` and `reference/` contents are gitignored; only their `.gitkeep` files
are tracked. `pyproject.toml` lists pandas, openpyxl, python-pptx, python-docx, pypdf and
python-dotenv for `uv`; edit it to suit.

## Using it with grill-with-docs

daily-work is meant to sit next to Matt Pocock's `grill-with-docs` skill, which needs the
`grilling` and `domain-modeling` skills installed. daily-work never calls them and works
without them; the generated `CLAUDE.md` only tells Claude when to suggest one.

Pin the versions of `grilling`, `domain-modeling` and `grill-with-docs` you install. An open
change renames `CONTEXT.md` to `GLOSSARY.md`, and the generated `CLAUDE.md` reads
`CONTEXT.md`; an unpinned update would leave the glossary where Claude no longer looks.

This plugin never creates or edits `CONTEXT.md`, `CONTEXT-MAP.md` or `docs/adr/`.
