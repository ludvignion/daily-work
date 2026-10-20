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

This creates `AGENTS.md`, `README.md`, `.gitignore`, `tools/` and a few more files,
and makes the folder a git repo. If it asks to install uv and a Python, answer "yes": the
plugin needs them to send what it records, and installs them itself in about a minute. Your
tasks do not need Python. `.claude/settings.json` holds the two switches for what the
plugin sends its author; change a `"1"` to `"0"` there to turn one off. Then ask Claude:
"Help me write the Purpose section in AGENTS.md", and answer its questions.

## 7. Your first task

All inside Claude Code, in your work repo:

1. **Describe it.**
   `/daily-work:brief <project> <what you want, in your own words>`
   The project is an engagement, a system or a responsibility, e.g. `acme`. Claude rewrites
   your text into a brief, picks a short task name for its file (e.g. `q3-review`), and
   shows both. Answer "yes" or say what to change.
2. **Grill it.**
   Paste the `Next:` line step 1 printed, or type
   `/mattpocock-skills:grill-with-docs <task-name>`.
   Answer the questions. At the end, Claude writes `<project>/tasks/<task-name>.md` with
   what was settled.
3. **Add files.** Put the client's files (decks, spreadsheets, PDFs) in the project's
   `inputs/` folder. Open it from your file manager, or ask Claude where it is.
4. **Do the work.** "Work on <task-name>". Results land in the project's `outputs/`.
5. **Close it.**
   `/daily-work:record <task-name>`, or just `/daily-work:record` if it is your only open task.
   Claude shows what was done and what to watch out for and asks "Record this?". Answer
   yes; it writes it down, commits, and lists the checks left for you.

With several tasks open, `/daily-work:record` with no argument lists them.

To change something a project already produced, start again at step 1 and say what to
change ("update the prices in the Q3 review"). The new task edits the file already in
`outputs/`; it does not make a second one.

## Everyday use

```
cd work
claude
```

To read a file without an editor, ask Claude ("show me the task file for acme/q3-review"), or
open the folder in your file manager.

## If something is off

- **A `/daily-work:` command is missing:** run `/plugin`, check that daily-work is installed
  and enabled, then restart Claude Code.
- **record says "git commit failed":** git does not know who you are; redo step 2's
  `git config` lines.
- **Update daily-work now instead of waiting:** `/plugin marketplace update daily-work`, then
  restart Claude Code.
