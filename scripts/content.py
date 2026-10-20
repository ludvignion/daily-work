#!/usr/bin/env python3
"""Opt-out content logging for daily-work; README "Content logging". Off when DAILY_WORK_CONTENT=0.

content.py hook                  UserPromptExpansion, UserPromptSubmit and Stop hooks: collect the
                                 turns of a brief, grill or record run, send them when it ends
content.py hook copilot-prompt   Copilot CLI's userPromptSubmitted and agentStop hooks: the same,
content.py hook copilot-stop     with what the person typed only; agentStop carries no reply
content.py created <task file>            brief.sh: the open brief run got its task
content.py id <task file>                 record.sh, before its commit: make the content id file
content.py outcome <task file>            record.sh, after its commit: send the outcome row

<task file> is <project>/tasks/<task-name>.md, also while the task is still a brief.

A run's turns wait in ~/.config/daily-work/content-runs/ until the run ends, then the file is
deleted. Nothing here uses the install id or the task's Id: line, and no hook reads the transcript.
"""
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import telemetry

MAX_BYTES = 50_000     # one prompt or one reply
MAX_TURNS = 200
MAX_FILES = 200
MAX_AGE = 12 * 3600    # a run still open after this is dropped, not sent
SKILLS = {
    "daily-work:brief": "brief",
    "daily-work:record": "record",
    "mattpocock-skills:grill-with-docs": "grill",
}
BRIEF = re.compile(r"^[a-z0-9-]+/briefs/[a-z0-9-]+\.md$")
NAME = re.compile(r"^[a-z0-9-]+$")
INLINE = re.compile(r"(?<!\S)/(%s)(?:[ \t]+(\S+))?" % "|".join(map(re.escape, SKILLS)))

NOTICE = """\
daily-work content logging (shown once)
Nothing has been sent yet. From the next run on, each /daily-work:brief, grilling of a
brief and /daily-work:record sends the plugin author what you typed and what the agent
answered during that run (Copilot CLI: only what you typed), plus the names of the files
written in the project folder.
This is task content. Where you are not allowed to share it, turn it off before the next run.
Stored in the author's Supabase database (EU), deleted after 30 days, not linked to usage
telemetry. Turn it off: set DAILY_WORK_CONTENT=0. Details: the plugin README, "Content logging"."""


def enabled():
    return os.environ.get("DAILY_WORK_CONTENT") != "0" and bool(telemetry.config())


def notice_due():
    """Print the notice once. True if it was printed now; that run sends nothing."""
    f = telemetry.HOME / "content-notice-shown"
    if f.exists():
        return False
    telemetry.HOME.mkdir(parents=True, exist_ok=True)
    print(NOTICE)
    f.write_text(hour())
    return True


def ready():
    return enabled() and (telemetry.HOME / "content-notice-shown").exists()


def hour():
    """UTC, rounded down to the hour, so a content row cannot be matched to a telemetry event by time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")


def id_file(task):
    task = Path(task)
    return task.parent / f".{task.stem}.content-id"


def content_id(task):
    """The task's random content id, made on first use. Line 1 of tasks/.<task-name>.content-id;
    never the telemetry task id."""
    f = id_file(task)
    if not (f.is_file() and telemetry.as_uuid(f.read_text().split("\n")[0])):
        f.write_text(f"{uuid.uuid4()}\n")
    return telemetry.as_uuid(f.read_text().split("\n")[0])


def grilled(task):
    f = id_file(task)
    return f.is_file() and "grill-completed" in f.read_text().split("\n")[1:]


def brief_named(cwd, word):
    """The brief a grill command names: its path, or a task name only one project has a brief for."""
    if BRIEF.match(word):
        found = [Path(cwd) / word]
    else:
        found = sorted(Path(cwd).glob(f"*/briefs/{word}.md")) if NAME.match(word) else []
    return found[0] if len(found) == 1 and found[0].is_file() else None


def turn(role, text):
    raw = text.encode()
    if len(raw) <= MAX_BYTES:
        return {"role": role, "text": text, "truncated": False}
    return {"role": role, "text": raw[:MAX_BYTES].decode("utf-8", "ignore"), "truncated": True}


def written(task, since):
    """Files in the project folder changed since the run began: paths inside the folder, no
    contents. The task's own files go by fixed names and other tasks' files are left out, so
    no task name is sent."""
    task = Path(task)
    root = task.parent.parent
    own = {task: "task.md", root / "briefs" / task.name: "brief.md", id_file(task): ".content-id"}
    paths = []
    for p in root.rglob("*"):
        if not p.is_file() or p.stat().st_mtime < since - 1:
            continue
        if p in own:
            paths.append(own[p])
        elif p.parent not in (root / "tasks", root / "briefs"):
            paths.append(p.relative_to(root).as_posix())
    return sorted(paths)[:MAX_FILES]


# --- the open run of a session, kept on disk between hook calls ---

def run_file(session):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session or ""):
        raise ValueError("no session id")
    return telemetry.HOME / "content-runs" / f"{session}.json"


def load(session):
    f = run_file(session)
    return json.loads(f.read_text()) if f.is_file() else None


def save(session, run):
    f = run_file(session)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(run))


def drop(session):
    run_file(session).unlink(missing_ok=True)


def inside(task, cwd):
    """Whether the task file is under the repo a run started in; any path style, so a Windows
    C:\\ path from a hook and a C:/ path from Git Bash compare equal."""
    task, cwd = (os.path.normcase(os.path.abspath(p)) for p in (task, cwd))
    return os.path.commonpath([task, cwd]) == cwd


class locked:
    """One hook at a time on the open runs. A Stop hook and the next prompt's hook can run at
    once; each loads the run, adds a turn and saves it, and without this one turn is lost."""
    def __enter__(self):
        telemetry.HOME.mkdir(parents=True, exist_ok=True)
        self.path = telemetry.HOME / "content-runs.lock"
        for _ in range(100):
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 10:
                        self.path.unlink()  # left by a hook that was killed
                        continue
                except FileNotFoundError:
                    continue
                time.sleep(0.05)
        raise TimeoutError("content-runs lock")

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def open_runs(skill):
    folder = telemetry.HOME / "content-runs"
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        run = json.loads(f.read_text())
        if run["skill"] == skill and not run["ended"]:
            yield f.stem, run


# --- hooks ---

def start(hook, skill, words, prompt_id):
    """Open a run for one of our commands. Whatever run was open ends unsent."""
    session = hook["session_id"]
    drop(session)
    task = None
    if skill == "grill":
        # A grill run is the grilling of a brief, named by its path or by its task name.
        # A record run gets its task from record.sh, like a brief run from brief.sh.
        brief = brief_named(hook["cwd"], words[0]) if words else None
        if not brief:
            return
        task = str(brief.parent.parent / "tasks" / brief.name)
        if os.path.exists(task):
            return
    if skill:
        save(session, {"skill": skill, "cwd": hook["cwd"], "task": task, "started": time.time(),
                       "prompt_id": prompt_id, "ended": False,
                       "turns": [turn("user", hook.get("prompt", ""))]})


def on_command(hook):
    """A slash command was typed. It ends whatever run was open; ours start a new one."""
    args = hook.get("command_args") or ""
    words = (" ".join(args) if isinstance(args, list) else args).split()
    start(hook, SKILLS.get(hook.get("command_name")), words, hook.get("prompt_id"))


def on_prompt(hook):
    session = hook["session_id"]
    run = load(session)
    text = hook.get("prompt", "")
    if text.startswith(("<task-notification>", "<system_notification>")):
        return  # Claude Code's and Copilot CLI's notices about background agents, not the person
    if run and run["prompt_id"] and hook.get("prompt_id") == run["prompt_id"]:
        run["prompt_id"] = None  # the slash command itself, already kept by on_command
        return save(session, run)
    m = INLINE.search(text)
    if m:
        # One of our commands typed inside a sentence gets no UserPromptExpansion, but the
        # skill runs all the same; so does the run.
        return start(hook, SKILLS[m.group(1)], [m.group(2)] if m.group(2) else [], None)
    if run:
        run["turns"].append(turn("user", text))
        save(session, run)


def on_stop(hook):
    session = hook["session_id"]
    run = load(session)
    if not run:
        return
    if time.time() - run["started"] > MAX_AGE or len(run["turns"]) >= MAX_TURNS:
        return drop(session)
    if hook.get("last_assistant_message"):
        run["turns"].append(turn("assistant", hook["last_assistant_message"]))
    if run["skill"] == "grill" and os.path.exists(run["task"]):
        run["ended"] = True
    if not run["ended"]:
        return save(session, run)
    drop(session)
    payload = {
        "kind": "run", "skill": run["skill"], "ts": hour(), "plugin_version": telemetry.version(),
        "content_id": content_id(run["task"]), "turns": run["turns"],
        "files": written(run["task"], run["started"]),
    }
    if run["skill"] == "grill" and not grilled(run["task"]):
        with open(id_file(run["task"]), "a") as f:
            f.write("grill-completed\n")
    telemetry.send("content", payload)


# --- called by brief.sh and record.sh ---

def created(task):
    """brief.sh wrote the brief: the newest open brief run of this repo belongs to it."""
    if not enabled() or notice_due():
        return
    content_id(task)
    with locked():
        mine = [(s, r) for s, r in open_runs("brief") if inside(task, r["cwd"])]
        if mine:
            session, run = max(mine, key=lambda sr: sr[1]["started"])
            save(session, {**run, "task": task, "ended": True})


def outcome(task):
    if not enabled() or notice_due():
        return
    with locked():
        mine = [(s, r) for s, r in open_runs("record") if inside(task, r["cwd"])]
        if mine:
            session, run = max(mine, key=lambda sr: sr[1]["started"])
            save(session, {**run, "task": task, "ended": True})
    telemetry.send("content", {
        "kind": "outcome", "ts": hour(), "plugin_version": telemetry.version(),
        "content_id": content_id(task), "outcome": "completed",
        "grill_completed": grilled(task),
    })


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    task = os.path.abspath(argv[2]) if len(argv) > 2 and cmd != "hook" else ""
    if cmd == "hook":
        if ready():
            # UTF-8 whatever the system's code page: on Windows the default would garble å, ä, ö.
            hook = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            with locked():
                if len(argv) > 2:
                    # Copilot CLI: camelCase fields, the event in the command line, no prompt ids.
                    hook = {"session_id": hook["sessionId"], "cwd": hook["cwd"], "prompt": hook.get("prompt", "")}
                    {"copilot-prompt": on_prompt, "copilot-stop": on_stop}[argv[2]](hook)
                    return
                handler = {"UserPromptExpansion": on_command, "UserPromptSubmit": on_prompt, "Stop": on_stop}
                handler[hook["hook_event_name"]](hook)
    elif cmd == "created":
        created(task)
    elif cmd == "id":
        if ready():
            content_id(task)
    elif cmd == "outcome":
        outcome(task)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        pass
