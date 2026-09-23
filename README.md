# daily-work

A Claude Code plugin that gives a repo a structure for ad-hoc white-collar work: reading decks,
evaluating documents, pulling and checking numbers, writing memos. Work is grouped in areas (a
client, a system, a recurring responsibility). A person describes a task in a brief; Matt Pocock's
`grill-with-docs` skill grills the brief into a task Claude can work on; the plugin records
what was done. Nothing here builds software.

Local filesystem and git only. No network calls. The plugin never opens `.env`.

## Setup

Everything below happens in your **work repo**, the repo where you do daily work, not in this
plugin's repo.

**1. Install the plugins** (once per machine, inside Claude Code):

```
/plugin marketplace add ludvignion/daily-work
/plugin install daily-work@daily-work
/plugin install mattpocock-skills
```

`mattpocock-skills` is Matt Pocock's skill set from
[mattpocock/skills](https://github.com/mattpocock/skills), in Claude Code's official
marketplace. daily-work uses its `grill-with-docs` skill (which calls his `grilling` and
`domain-modeling`) for the grilling step, as `/mattpocock-skills:grill-with-docs`. daily-work
does not ship or call it.

Both plugins update automatically. A planned change in Matt Pocock's skills renames
`CONTEXT.md` to `GLOSSARY.md`; it will arrive without warning, so the generated `CLAUDE.md`
reads whichever of the two exists.

To update daily-work by hand: `/plugin marketplace update daily-work`, then restart Claude
Code. From a terminal, the same commands start with `claude plugin` instead of `/plugin`.

**2. Create the work repo and set it up** (once per work repo):

```
mkdir ~/workspace/<work repo> && cd ~/workspace/<work repo>
claude
/daily-work:init
```

To try a local checkout of daily-work instead of installing it:
`claude --plugin-dir /path/to/daily-work`.

## The per-task loop

1. **Brief.** Describe the task in your own words:
   `/daily-work:brief techseed I want to help my colleague visualise different options of a UNS structure …`
   Claude rewrites it into a clear brief (no additions, open points left open), with a
   heading and a file name, and asks for the area if you did not name an existing one. You
   approve or correct it; only then is the task folder `areas/techseed/tasks/uns-mockup/`
   created, holding `brief.md`, `inputs/` and `outputs/`.
2. **Grill.** `/mattpocock-skills:grill-with-docs areas/techseed/tasks/uns-mockup/brief.md` (Matt Pocock's
   skill). It interviews you until the task is clear, and records terms in `CONTEXT.md` and
   decisions in `docs/adr/`. When it ends, the generated CLAUDE.md has Claude replace
   `brief.md` with `task.md` in the same folder: the brief as the Ask, what was settled as
   the Spec.
3. **Work.** Tell Claude to work on the task folder. Client files go in `inputs/`; what the
   task produces, code included, goes in `outputs/`.
4. **Record.** `/daily-work:record areas/techseed/tasks/uns-mockup` writes Result and
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
    tasks/
      uns-mockup/             not grilled yet
        brief.md              the verified description
        inputs/  outputs/
      q3-numbers/             grilled
        task.md               heading, Ask, Spec, Result, Caveats
        inputs/               client files (not committed)
        outputs/              what was produced, code included (committed)
tools/                        code used by two or more tasks
```

## Skills

All three are user-invoked only.

- **`/daily-work:init [dir]`** — creates `CLAUDE.md`, `README.md`, `.gitignore`,
  `.env.example`, `pyproject.toml`, `areas/` and `tools/`, and runs `git init` if the
  directory is not in a repo. Prints `copied` or `skipped` per file. Never overwrites: an
  existing `CLAUDE.md` gets only the template's missing `##` sections, an existing
  `.gitignore` only its missing lines. Safe to re-run.
- **`/daily-work:brief [area] <describe the task>`** — rewrites the description into a brief,
  shows it for you to verify, and on approval creates `areas/<area>/tasks/<slug>/` with
  `brief.md`, `inputs/` and `outputs/`, adds `- <date> <slug>: open` under `## Tasks` in the
  area README, and creates the area (`README.md`, `sources.md`, its line under `## Areas`) if
  new.
- **`/daily-work:record [task folder]`** — fills `## Result` and `## Caveats` from `outputs/`
  and the conversation, adds any missing source to the area's `sources.md`, changes the README
  line to `- <date> <slug>: done, <one line>`, commits `daily-work: record <slug>`, and prints
  the Done lines left to check. It refuses to commit if `## Ask` or `## Spec` changed. With no
  argument it lists open tasks.

`inputs/` is gitignored so client files never enter git history; only its `.gitkeep` is
tracked. `pyproject.toml` lists pandas, openpyxl, python-pptx,
python-docx, pypdf and python-dotenv for `uv`; edit it to suit.

## What daily-work does and does not do with grill-with-docs

- It never calls, wraps or edits Matt Pocock's skills, and its own skills work without them.
- The generated `CLAUDE.md` is what makes a grilling session end by turning `brief.md` into
  `task.md`.
- It never creates or edits `CONTEXT.md`, `GLOSSARY.md`, `CONTEXT-MAP.md` or `docs/adr/`;
  those belong to `grill-with-docs`.
