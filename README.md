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

1. **Task.** `/daily-work:task acme review-deck` creates
   `areas/acme/tasks/<today>-review-deck/` with `task.md`, `inputs/` and `outputs/`. Write the
   Ask in `task.md` (or pass it after the slug) and drop the source files in `inputs/`.
2. **Clarify line.** Before answering, Claude states in one line which sources it will use,
   what each term in the Ask means, the scope, and the form of the output (see `## Before
   answering` in the generated `CLAUDE.md`).
3. **Grill, only when needed.** If the clarify line shows an undefined term or a missing
   source, or the Ask is larger than one sitting, run `/grill-with-docs` and write what was
   settled into the task's `## Spec`. Otherwise skip it.
4. **Work.** Claude does the task; results go in `outputs/`.
5. **Record.** `/daily-work:record areas/acme/tasks/<date>-review-deck` writes Result and
   Caveats, updates the area index and sources, commits, and lists the Done lines a person
   still has to check.

## Skills

All three are user-invoked only.

- **`/daily-work:init [dir]`** — creates `CLAUDE.md`, `README.md`, `.gitignore`,
  `.env.example`, `pyproject.toml` and `areas/_inbox/.gitkeep`, and runs `git init` if the
  directory is not in a repo. Prints `copied` or `skipped` per file. Never overwrites: an
  existing `CLAUDE.md` gets only the template's missing `##` sections, an existing
  `.gitignore` only its missing lines. Safe to re-run.
- **`/daily-work:task [area] <slug> [ask]`** — creates the task folder, and the area
  (`README.md`, `sources.md`, `reference/`) if it is new. Adds `- <date> <slug>: open` under
  `## Tasks` in the area README and the area under `## Areas` in the root README. One word is
  a slug in `areas/_inbox/`; to give an inbox task an Ask, name the area:
  `/daily-work:task _inbox <slug> <ask>`. Slugs and areas use `[a-z0-9-]` only.
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
