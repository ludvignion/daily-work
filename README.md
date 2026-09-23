# daily-work

A Claude Code plugin that gives a repo a structure for ad-hoc white-collar work: reading decks,
evaluating documents, pulling and checking numbers, writing memos. Work is grouped in areas (a
client, a system, a recurring responsibility). A person describes a task in a brief; grilling
turns the brief into a task Claude can work on; the plugin records what was done. Nothing here builds software.

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

1. **Brief.** Describe the task in your own words:
   `/daily-work:brief techseed I want to help my colleague visualise different options of a UNS structure …`
   Claude picks a heading and a file name (and asks for the area if you did not name an
   existing one), and the plugin writes `areas/techseed/briefs/uns-mockup.md` and shows it.
2. **Grill.** `/grill-with-docs areas/techseed/briefs/uns-mockup.md`. The grilling settles
   what the task is. When it ends, the generated CLAUDE.md has Claude turn the brief into
   `areas/techseed/tasks/<today>-uns-mockup/task.md`: your text as the Ask, what was settled
   as the Spec. If that did not happen, run `/daily-work:task` on the brief.
   A brief that is already clear can skip grilling and go straight to `/daily-work:task`.
3. **Work.** Tell Claude to work on the task folder. Client files go in `inputs/`; what the
   task produces, code included, goes in `outputs/`.
4. **Record.** `/daily-work:record areas/techseed/tasks/<date>-uns-mockup` writes Result and
   Caveats, marks the task done in the area README, commits, and lists the Done lines a
   person still has to check.

A repo set up by this plugin:

```
CLAUDE.md                     how Claude works here
README.md                     ## Areas: one line per area
areas/
  techseed/
    README.md                 ## Tasks: one line per task, open or done
    sources.md                where facts come from, and which source wins
    reference/                client files for the area (not committed)
    briefs/
      uns-mockup.md           a description waiting to be grilled
    tasks/
      2026-09-23-uns-mockup/
        task.md               heading, Ask, Spec, Result, Caveats
        brief.md              the brief it came from
        inputs/               client files (not committed)
        outputs/              what was produced, code included (committed)
tools/                        code used by two or more tasks
```

## Skills

All four are user-invoked only.

- **`/daily-work:init [dir]`** — creates `CLAUDE.md`, `README.md`, `.gitignore`,
  `.env.example`, `pyproject.toml`, `areas/` and `tools/`, and runs `git init` if the
  directory is not in a repo. Prints `copied` or `skipped` per file. Never overwrites: an
  existing `CLAUDE.md` gets only the template's missing `##` sections, an existing
  `.gitignore` only its missing lines. Safe to re-run.
- **`/daily-work:brief [area] <describe the task>`** — writes the description to
  `areas/<area>/briefs/<slug>.md`, creating the area (`README.md`, `sources.md`,
  `reference/`) and its line under `## Areas` if new, and prints the brief.
- **`/daily-work:task <brief>`** — turns a brief into a task folder with `task.md`, `inputs/`
  and `outputs/`, moves the brief in as `brief.md`, adds `- <date> <slug>: open` under
  `## Tasks` in the area README, and writes anything settled in the conversation into the
  Spec. A grilling session normally does this itself; this is the fallback.
- **`/daily-work:record [task folder]`** — fills `## Result` and `## Caveats` from `outputs/`
  and the conversation, adds any missing source to the area's `sources.md`, changes the README
  line to `- <date> <slug>: done, <one line>`, commits `daily-work: record <slug>`, and prints
  the Done lines left to check. It refuses to commit if `## Ask` or `## Spec` changed. With no
  argument it lists open tasks.

`inputs/` and `reference/` are gitignored so client files never enter git history; only
their `.gitkeep` files are tracked. `pyproject.toml` lists pandas, openpyxl, python-pptx,
python-docx, pypdf and python-dotenv for `uv`; edit it to suit.

## Using it with grill-with-docs

daily-work is meant to sit next to Matt Pocock's `grill-with-docs` skill, which needs the
`grilling` and `domain-modeling` skills installed. daily-work never calls them and works
without them: the generated `CLAUDE.md` tells a grilling session to turn the brief into a task,
and `/daily-work:task` does the same by hand.

Pin the versions of `grilling`, `domain-modeling` and `grill-with-docs` you install. An open
change renames `CONTEXT.md` to `GLOSSARY.md`, and the generated `CLAUDE.md` reads
`CONTEXT.md`; an unpinned update would leave the glossary where Claude no longer looks.

This plugin never creates or edits `CONTEXT.md`, `CONTEXT-MAP.md` or `docs/adr/`.
