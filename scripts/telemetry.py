#!/usr/bin/env python3
"""Usage telemetry for daily-work. Metadata only; README "Telemetry" lists every field.

telemetry.py event <brief|record> <task file>   called by brief.sh and record.sh
telemetry.py event grill <task file> skipped     brief.sh --no-grill: a task made without grilling
telemetry.py hook            PostToolUse hook on Write: a grilling turned a brief into a task file
telemetry.py post <table>    the detached child: POST stdin to that Supabase table, silently

Nothing here may break or slow a command: every failure is swallowed, and the POST runs in
a detached child with a short timeout and no retry.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".config" / "daily-work"
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

NOTICE = """\
daily-work telemetry (shown once)
From the next run on, daily-work sends its author usage metadata, to see whether the
brief, grill, record loop gets used and where it stalls.
Sent: event name (brief, grill, record), UTC time, plugin version, a random install id, a
random task id, and the grill outcome.
Never sent: anything that identifies you or your machine, prompts, file names, paths, task
content, transcripts.
Opt out: set DAILY_WORK_TELEMETRY=0. Details: the plugin README, "Telemetry"."""


def schema():
    """The table group rows go to: sim for test sessions (DAILY_WORK_TARGET=test), public otherwise."""
    return "sim" if os.environ.get("DAILY_WORK_TARGET") == "test" else "public"


def opted_out():
    return os.environ.get("DAILY_WORK_TELEMETRY") == "0"


def config():
    """The Supabase URL and anon key from telemetry.json; None unless both are set."""
    try:
        c = json.loads((ROOT / "telemetry.json").read_text())
        return (c["url"].rstrip("/"), c["anon_key"]) if c["url"] and c["anon_key"] else None
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return None


def version():
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]


def as_uuid(text):
    try:
        return str(uuid.UUID(text.strip()))
    except ValueError:
        return None


def install_id():
    """A random UUID, made on first use and derived from nothing. Deleting the file resets it."""
    f = HOME / "install-id"
    if not (f.exists() and as_uuid(f.read_text())):
        HOME.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{uuid.uuid4()}\n")
    return as_uuid(f.read_text())


def task_id(task):
    """The random UUID on the Id: line brief.sh wrote, read from the task file or, before
    grilling, from its brief; None for a task without one."""
    task = Path(task)
    for f in (task, task.parent.parent / "briefs" / task.name):
        try:
            for line in f.read_text().splitlines():
                if line.startswith("Id: "):
                    return as_uuid(line[4:])
        except OSError:
            pass
    return None


def common(task):
    out = {
        "ts": datetime.now(timezone.utc).strftime(TS_FORMAT),
        "plugin_version": version(),
        "install_id": install_id(),
    }
    if task_id(task):
        out["task_id"] = task_id(task)
    return out


def first_run_notice():
    """Print the notice once. True if it was printed now; that run sends nothing."""
    f = HOME / "notice-shown"
    if f.exists():
        return False
    HOME.mkdir(parents=True, exist_ok=True)
    print(NOTICE)
    f.write_text(datetime.now(timezone.utc).strftime(TS_FORMAT))
    return True


def ready():
    return not opted_out() and bool(config()) and (HOME / "notice-shown").exists()


def send(table, payload):
    """Hand the payload to a detached child and return at once."""
    child = subprocess.Popen(
        [sys.executable, __file__, "post", table],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child.stdin.write(json.dumps(payload).encode())
    child.stdin.close()


def request(table, body):
    """An insert into a Supabase table through its REST API, asking for nothing back. The
    Content-Profile header picks the schema: the same tables exist in public and in sim."""
    url, key = config()
    return urllib.request.Request(f"{url}/rest/v1/{table}", data=body, method="POST", headers={
        "apikey": key,
        "Content-Type": "application/json",
        "Content-Profile": schema(),
        "Prefer": "return=minimal",
    })


def post(table, body, timeout=3):
    with urllib.request.urlopen(request(table, body), timeout=timeout) as response:
        return response.status


def emit(event, task, extra=None):
    if opted_out() or not config() or first_run_notice():
        return
    send("events", {"event": event, **common(task), **(extra or {})})


def grilled_task(hook):
    """The task file, if this Write made tasks/<name>.md while briefs/<name>.md exists: a grilling just ended."""
    path = os.path.join(hook.get("cwd", ""), hook.get("tool_input", {}).get("file_path", "")).replace("\\", "/")
    m = re.search(r"^(.*/[a-z0-9-]+)/tasks/([a-z0-9-]+\.md)$", path)
    if m and os.path.exists(f"{m.group(1)}/briefs/{m.group(2)}"):
        return path
    return None


def copilot_grilled_task(hook):
    """The same for Copilot CLI's postToolUse: its apply_patch adds the task file and deletes the
    brief in one call, so a brief deleted by that patch counts as existing."""
    args = hook.get("toolArgs")
    if hook.get("toolName") != "apply_patch" or not isinstance(args, str):
        return None
    added = re.findall(r"^\*\*\* Add File: (.+)$", args, re.M)
    deleted = {os.path.join(hook.get("cwd", ""), p).replace("\\", "/") for p in re.findall(r"^\*\*\* Delete File: (.+)$", args, re.M)}
    for name in added:
        path = os.path.join(hook.get("cwd", ""), name).replace("\\", "/")
        m = re.search(r"^(.*/[a-z0-9-]+)/tasks/([a-z0-9-]+\.md)$", path)
        if m and (f"{m.group(1)}/briefs/{m.group(2)}" in deleted or os.path.exists(f"{m.group(1)}/briefs/{m.group(2)}")):
            return path
    return None


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "post":
        post(argv[2], sys.stdin.buffer.read())
    elif cmd == "event":
        emit(argv[2], argv[3], {"outcome": argv[4]} if len(argv) > 4 else None)
    elif cmd == "hook":
        # A hook's output is not shown to the person, so it never counts as the first-run notice.
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # UTF-8 on Windows too
        task = copilot_grilled_task(hook) if argv[2:] == ["copilot"] else grilled_task(hook)
        if task and ready():
            send("events", {"event": "grill", **common(task), "outcome": "completed"})


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        pass
