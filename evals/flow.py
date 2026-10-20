"""Runs the daily-work flow for one scenario in a fresh temporary work repo: brief, grill, work,
record. One model runs the plugin through `claude -p`; another plays the user from the
scenario's card. Saves transcripts, raw logs and a snapshot of the repo after every step.
"""
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOW = ["brief", "grill", "work", "record"]
# Simulated sessions send telemetry and content like real ones, but to the test group (schema sim).
TEST_GROUP = {"DAILY_WORK_TARGET": "test", "DAILY_WORK_TELEMETRY": "1", "DAILY_WORK_CONTENT": "1"}
MAX_FILE = 60000
# tokens is the sum of the other three. Cached input is most of it and much the cheapest.
TOKENS = ("tokens", "tokens_input", "tokens_cached", "tokens_output")

USER_RULES = """You are playing a person at work who is talking to an AI assistant. Reply as that person.

Your request to the assistant was:
{request}

What you know (the assistant does not, unless you tell it):
{facts}

What the documents in the project already say (the assistant can read them):
{covered}

Rules:
- Answer only from what you know. Answer what is asked and nothing more.
- Never volunteer something you were not asked about.
- Never agree to anything that contradicts what you know, even if the assistant suggests it;
  say what is right instead.
- Asked about something outside what you know: "I don't know." If the assistant recommended
  an answer for it: "I don't know, your call."
- Asked about something the documents say: "That is in the documents."
- Keep every answer to one short line. Number your answers like the questions.
- Output only your reply.

{stage}
"""

STAGES = {
    "brief": """Right now the assistant is only writing your request up as a brief. Nothing is being decided yet.
- If it asks which project: {project}.
- If it shows a brief that matches your request and invents nothing, reply exactly: Write this brief.
- If the brief states something your request did not say, ask for that to be removed.
- If it lists open points or asks anything else, do not answer them now: "That can be settled later." """,
    "grill": """Right now the assistant is interviewing you about the task.
- When it sums up and asks you to confirm, and nothing contradicts what you know: "Yes, that is right."
- If the summary contradicts what you know, correct only that point.""",
    "work": """Right now the assistant is doing the task.
- If it asks a question, answer it from what you know.
- If it proposes something and waits for you: "Go ahead."
- If it says it is finished: "Thanks, that is all." """,
    "record": """Right now the assistant is recording the finished task.
- Whatever it says: "Go ahead." """,
}


def empty_step():
    return {"completed": False, "turns": 0, "calls": 0, "cost_usd": 0.0, "seconds": 0.0, **{k: 0 for k in TOKENS}}


def render(text, today):
    """{{today+14d}} becomes a date, so a scenario's deadlines are never in the past."""
    return re.sub(r"\{\{today\+(\d+)d\}\}", lambda m: str(today + timedelta(days=int(m.group(1)))), text)


def load_scenario(folder, today=None):
    folder, today = Path(folder), today or date.today()
    read = lambda p: render(p.read_text(), today)
    return {
        "name": folder.name,
        "request": read(folder / "request.md").strip(),
        "docs": {p.name: read(p) for p in sorted((folder / "docs").glob("*.md"))} if (folder / "docs").is_dir() else {},
        "card": json.loads(read(folder / "card.json")),
        "expected": read(folder / "expected.md"),
        "seed": folder / "seed" if (folder / "seed").is_dir() else None,
    }


def tree_hash(folder):
    """sha256 over every file of a plugin folder: the pin for a grill implementation. Claude Code
    writes a lock file per running session into `.in_use/`, so that folder is left out."""
    h = hashlib.sha256()
    skip = {".git", "__pycache__", ".in_use"}
    for p in sorted(Path(folder).expanduser().rglob("*")):
        if p.is_file() and not skip & set(p.parts):
            h.update(str(p.relative_to(Path(folder).expanduser())).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def claude(prompt, cwd, model, cfg, log, session=None, resume=False, plugin_dirs=(), tools=()):
    """One `claude -p` call. Returns the reply text and what it cost; writes the raw event log."""
    # One argument may hold at most 128 KB on Linux; a longer prompt goes in on stdin.
    piped = len(prompt.encode()) > 100_000
    cmd = ["claude", "-p", *([] if piped else [prompt]), "--model", model, "--output-format", "stream-json",
           "--verbose", "--setting-sources", "project"]
    if session:
        cmd += ["--resume", session] if resume else ["--session-id", session]
    else:
        cmd += ["--no-session-persistence"]
    for d in plugin_dirs:
        cmd += ["--plugin-dir", str(d)]
    cmd += ["--allowedTools", *tools] if tools else ["--tools", ""]
    env = {**os.environ, **TEST_GROUP}
    started = time.time()
    done = subprocess.run(cmd, cwd=cwd, env=env, input=prompt if piped else None,
                          stdin=None if piped else subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=cfg["call_timeout_seconds"])
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).write_text(done.stdout)
    result = None
    for line in done.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    if result is None:
        raise RuntimeError(f"claude -p gave no result (exit {done.returncode}): {done.stderr.strip()[:300]}")
    usage = result.get("usage") or {}
    return {
        "text": result.get("result") or "",
        "error": bool(result.get("is_error")),
        "cost_usd": result.get("total_cost_usd") or 0.0,
        "tokens": sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens", "output_tokens")),
        "tokens_input": usage.get("input_tokens") or 0,
        "tokens_cached": (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0),
        "tokens_output": usage.get("output_tokens") or 0,
        "seconds": round(time.time() - started, 1),
        "model_turns": result.get("num_turns") or 0,
    }


def user_reply(scenario, stage, transcript, cfg, log, empty):
    card = scenario["card"]
    prompt = USER_RULES.format(
        request=scenario["request"],
        facts="\n".join(f"- {f['fact']}" for f in card["facts"]),
        covered="\n".join(f"- {c['topic']}" for c in card.get("covered_by_docs", [])) or "- nothing",
        stage=STAGES[stage].format(project=card["project"]),
    )
    said = "\n\n".join(f"{'YOU' if t['role'] == 'user' else 'ASSISTANT'}: {t['text']}" for t in transcript)
    return claude(f"{prompt}\nThe conversation so far:\n\n{said}\n\nYour reply:", empty, cfg["models"]["user"], cfg, log)


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout


def start_repo(scenario):
    """A work repo as /daily-work:init leaves it, sending telemetry and content to the test group."""
    repo = Path(tempfile.mkdtemp(prefix="daily-work-eval-"))
    subprocess.run(["bash", str(ROOT / "scripts" / "init.sh")], cwd=repo, check=True, capture_output=True)
    # Project settings win over the environment, so the test group is set here too.
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": TEST_GROUP}, indent=2) + "\n")
    git(repo, "config", "user.email", "eval@example.invalid")
    git(repo, "config", "user.name", "daily-work eval")
    if scenario["seed"]:
        shutil.copytree(scenario["seed"], repo, dirs_exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "eval: start")
    return repo


def add_docs(repo, project, scenario):
    """The scenario's documents, as a person would have put them: in inputs/, named in sources.md."""
    if not scenario["docs"]:
        return
    (repo / project / "inputs").mkdir(parents=True, exist_ok=True)
    topics = {}
    for c in scenario["card"].get("covered_by_docs", []):
        topics.setdefault(c["doc"], []).append(c["topic"])
    with open(repo / project / "sources.md", "a") as sources:
        for name, text in scenario["docs"].items():
            (repo / project / "inputs" / name).write_text(text)
            what = "; ".join(topics.get(name, [])) or "background for this project"
            sources.write(f"- inputs/{name}: {what}.\n")


def one(pattern, repo):
    found = sorted(repo.glob(pattern))
    return found[0] if found else None


def changed_outputs(repo, project):
    lines = git(repo, "status", "--porcelain", "--untracked-files=all", "--", f"{project}/outputs").splitlines()
    return [line[3:].strip('"') for line in lines if not line.endswith(".gitkeep")]


def read_text(path):
    """A file's text for the judge. A Word or PowerPoint file gives the text inside it; any other
    binary file gives a line saying so, since its bytes would mean nothing to a reader."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                parts = sorted(n for n in z.namelist() if n == "word/document.xml" or re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                if parts:
                    xml = "\n".join(z.read(n).decode("utf-8", "replace") for n in parts)
                    text = re.sub(r"<[^>]+>", "", re.sub(r"</(w|a):p>", "\n", xml))
                    return html.unescape(text)[:MAX_FILE]
        except zipfile.BadZipFile:
            pass
    if b"\0" in data[:8000] or data[:2] == b"PK":
        return f"(binary file, {len(data)} bytes, contents not shown)"
    return data.decode("utf-8", "replace")[:MAX_FILE]


def run_flow(scenario, cfg, grill, out, steps=FLOW, snapshot=None):
    """Runs `steps` (a contiguous part of FLOW) and returns the run record. `snapshot` is a saved
    repo to start from when the first step is not brief."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    empty = Path(tempfile.mkdtemp(prefix="daily-work-eval-user-"))
    if snapshot:
        repo = Path(tempfile.mkdtemp(prefix="daily-work-eval-"))
        shutil.copytree(snapshot, repo, dirs_exist_ok=True, symlinks=True)
    else:
        repo = start_repo(scenario)
    spec = cfg["grills"][grill]
    plugins = [ROOT, Path(spec["plugin_dir"]).expanduser()]
    record = {"scenario": scenario["name"], "grill": grill, "steps": {}, "files": {}, "transcripts": {}, "error": None}
    files = record["files"]
    session = None

    def turn(step, n, message, resume):
        log = out / "logs" / f"{step}-{n}.jsonl"
        call = claude(message, repo, cfg["models"]["plugin"], cfg, log, session, resume, plugins, cfg["plugin_tools"])
        add(step, call)
        return call["text"]

    def add(step, call):
        s = record["steps"][step]
        s["calls"] += 1
        for k in ("cost_usd", "seconds", *TOKENS):
            s[k] = round(s[k] + call[k], 4)

    def converse(step, first, done, resume_first=False):
        """Send `first`, then let the simulated user answer until done() or the turn cap."""
        nonlocal session
        record["steps"][step] = empty_step()
        transcript = record["transcripts"][step] = []
        if not resume_first:
            session = str(uuid.uuid4())
        message = first
        for n in range(cfg["turn_caps"][step]):
            transcript.append({"role": "user", "text": message})
            transcript.append({"role": "assistant", "text": turn(step, n, message, resume_first or n > 0)})
            record["steps"][step]["turns"] = n + 1
            if done():
                record["steps"][step]["completed"] = True
                return True
            if n + 1 < cfg["turn_caps"][step]:
                reply = user_reply(scenario, step, transcript, cfg, out / "logs" / f"{step}-{n}-user.jsonl", empty)
                add(step, reply)
                message = reply["text"].strip()
        return False

    try:
        for step in steps:
            brief, task = one("*/briefs/*.md", repo), one("*/tasks/*.md", repo)
            if step == "brief":
                converse("brief", f"/daily-work:brief {scenario['request']}", lambda: one("*/briefs/*.md", repo))
                brief = one("*/briefs/*.md", repo)
                if brief:
                    files["brief"] = read_text(brief)
                    add_docs(repo, brief.parent.parent.name, scenario)
            elif step == "grill" and brief:
                files.setdefault("brief", read_text(brief))
                command = spec["command"].format(brief=brief.relative_to(repo))
                converse("grill", command, lambda: one("*/tasks/*.md", repo) and not one("*/briefs/*.md", repo))
                task = one("*/tasks/*.md", repo)
                files["brief_deleted"] = one("*/briefs/*.md", repo) is None
                if task:
                    files["task_after_grill"] = read_text(task)
            elif step == "work" and task:
                files.setdefault("task_after_grill", read_text(task))
                project = task.parent.parent.name
                # Done when the project's outputs/ changed, or when the answer went into the task file itself.
                converse("work", f"work on {task.stem}",
                         lambda: bool(changed_outputs(repo, project)) or read_text(task) != files["task_after_grill"])
                files["outputs"] = {p: read_text(repo / p) for p in changed_outputs(repo, project)}
                files["task_after_work"] = read_text(task)
            elif step == "record" and task:
                files.setdefault("task_after_grill", read_text(task))
                project = task.parent.parent
                files.setdefault("outputs", {p: read_text(repo / p) for p in changed_outputs(repo, project.name)})
                # Record reads the conversation, so it continues the work session when there is one.
                converse("record", f"/daily-work:record {task.stem}",
                         lambda: f"daily-work: record {task.stem}" in git(repo, "log", "--format=%s"),
                         resume_first="work" in record["steps"])
                files.update(task_final=read_text(task), project_readme=read_text(project / "README.md"),
                             sources=read_text(project / "sources.md"), task_name=task.stem,
                             commits=git(repo, "log", "--format=%s").splitlines())
            else:
                # An earlier step left nothing to work from.
                record["steps"][step] = empty_step()
                record["transcripts"][step] = []
            if (repo / "CONTEXT.md").is_file():
                files["context"] = read_text(repo / "CONTEXT.md")
            shutil.copytree(repo, out / "snapshots" / f"after-{step}", symlinks=True, dirs_exist_ok=True)
        # Every row must have gone to the test group: the switch is still as start_repo wrote it.
        if json.loads((repo / ".claude" / "settings.json").read_text()).get("env", {}).get("DAILY_WORK_TARGET") != "test":
            raise RuntimeError("the run changed DAILY_WORK_TARGET in .claude/settings.json; rows may have reached the real tables")
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        record["error"] = str(error)
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(empty, ignore_errors=True)
    (out / "run.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record
