# Getting started

From a computer with nothing installed to your first task with Claude Code and daily-work.
No editor (VS Code, Cursor) is needed: you work in a terminal, and Claude reads and writes
the files.

## 1. Open a terminal

- **macOS:** Terminal (Cmd+Space, type "Terminal").
- **Windows:** PowerShell (Start menu, type "PowerShell").
- **Linux:** your usual terminal.

## 2. Install git

daily-work records every finished task as a git commit.

- **macOS:** `xcode-select --install`
- **Windows:** install Git for Windows from https://git-scm.com/download/win (Claude Code on
  Windows also needs it).
- **Linux:** `sudo apt install git` (or your distribution's package manager).

Then tell git who you are, once:

```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 3. Install Claude Code

- **macOS / Linux:** `curl -fsSL https://claude.ai/install.sh | bash`
- **Windows (PowerShell):** `irm https://claude.ai/install.ps1 | iex`

Close and reopen the terminal, then check it works:

```
claude --version
```

## 4. Log in

```
claude
```

Follow the prompts to log in with your Claude account (Pro, Max, Team or Enterprise) or an
Anthropic Console account. Type `/exit` to leave.

## 5. Install the plugins

Start `claude` anywhere and run, inside Claude Code:

```
/plugin marketplace add ludvignion/daily-work
/plugin install daily-work@daily-work
/plugin install mattpocock-skills
```

- **daily-work** gives you `/daily-work:init`, `/daily-work:brief` and `/daily-work:record`.
- **mattpocock-skills** is Matt Pocock's skill set; daily-work uses its
  `/mattpocock-skills:grill-with-docs` to turn a brief into a clear task.

Both update automatically. Restart Claude Code (`/exit`, then `claude`) after installing.

## 6. Create your work repo

One folder holds all your daily work. In the terminal:

```
mkdir work
cd work
claude
```

Inside Claude Code:

```
/daily-work:init
```

This creates `CLAUDE.md`, `README.md`, `.gitignore`, `areas/`, `tools/` and a few more files,
and makes the folder a git repo. Then ask Claude: "Help me write the Purpose section in
CLAUDE.md", and answer its questions.

## 7. Your first task

All inside Claude Code, in your work repo:

1. **Describe it.**
   `/daily-work:brief <area> <what you want, in your own words>`
   The area is a client, a system or a responsibility, e.g. `acme`. Claude rewrites your
   text into a brief and shows it. Answer "yes" or say what to change.
2. **Grill it.**
   `/mattpocock-skills:grill-with-docs areas/<area>/tasks/<slug>/brief.md`
   Answer the questions. At the end, Claude writes `task.md` in the same folder with what
   was settled.
3. **Add files.** Put the client's files (decks, spreadsheets, PDFs) in the task's
   `inputs/` folder. Open it from your file manager, or ask Claude where it is.
4. **Do the work.** "Work on areas/<area>/tasks/<slug>". Results land in `outputs/`.
5. **Close it.**
   `/daily-work:record areas/<area>/tasks/<slug>`
   Claude writes what was done and what to watch out for, commits, and lists the checks
   left for you.

To see which tasks are still open: `/daily-work:record` with no argument.

## Everyday use

```
cd work
claude
```

To read a file without an editor, ask Claude ("show me the task.md for acme/q3-review"), or
open the folder in your file manager.

## If something is off

- **A `/daily-work:` command is missing:** run `/plugin`, check that daily-work is installed
  and enabled, then restart Claude Code.
- **record says "git commit failed":** git does not know who you are; redo step 2's
  `git config` lines.
- **Update daily-work now instead of waiting:** `/plugin marketplace update daily-work`, then
  restart Claude Code.
