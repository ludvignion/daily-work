#!/usr/bin/env python3
"""Judge real sessions afterwards, in a batch: every brief, grill and record run in the Supabase
table content that has no score yet is scored by the judge model on the rubric for its skill
(config.json, session_rubrics), and the runs judged in the last days are grouped into topics and
confusion. Scores go to session_scores, the analysis to session_analysis.

python3 evals/sessions.py [--target real|test] [--limit 50] [--days 7] [--dry-run]

--target test judges the test group (schema sim: the eval's simulated sessions and your own
tries with DAILY_WORK_TARGET=test) instead of real use (schema public, the default).

Reads and writes with the secret key from the environment variable SUPABASE_SERVICE_KEY, so run
it in your own terminal or as a scheduled job; never put the key in a file. Run it at least
every 30 days: content deletes its rows after that.

The judge sees only what content holds: the person's prompts, the assistant's replies and the
names of the files written, not their contents. So it scores the conversation, not the output.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import analyse
import flow
import scoring

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CUT = 2500

JUDGE = """You judge one run of the {skill} step of daily-work, a plugin that turns a person's
request into a brief, grills them into a task file and records the result. You see only the
conversation and the names of the files the run wrote, not the files themselves: judge what
the conversation shows, and do not guess at what it does not.

Score each criterion from 1 to 5 by its description, with one sentence of reason. Describe the
assistant's behaviour; do not quote or repeat what the person wrote.

{criteria}

Reply with only this JSON:
{shape}

Files written: {files}

Conversation:
{conversation}"""

ANALYSE = """You are analysing real sessions of daily-work, a plugin that turns a person's request
into a brief, grills them into a task file and records the result. Below are {n} skill runs: for
each, the step, the judge's scores (1 to 5) with reasons, and the conversation.

Write two parts.

topics: the kinds of things the sessions dealt with, at most {groups} kinds, and how the
plugin handled each. confusion: the moments where the plugin and the person did not understand
each other, or the plugin did not follow its own steps, at most {groups} kinds.

Every kind has exactly {bullets} bullets. Each bullet is one short plain sentence of at most
{words} words about the plugin's behaviour, specific enough to act on. Never quote or repeat
what a person wrote, and name no person, client, project or figure from the sessions: describe
behaviour only. Each kind names the runs it comes from by their id below (for example
"grill/123"), only ids that appear. Order kinds by how many runs they cover, most first.

Reply with only this JSON:
{shape}

{materials}"""


def refuse(why):
    print(f"refused: {why}")
    sys.exit(1)


def cut(text, n=CUT):
    return text if len(text) <= n else text[:n] + " [cut]"


def conversation(turns):
    return "\n".join(f"{t.get('role')}: {cut(t.get('text') or '', 1500)}" for t in turns) or "(none)"


def judge_prompt(row, rubric):
    shape = {"scores": {c: {"score": 3, "reason": "one sentence"} for c in rubric}}
    return JUDGE.format(skill=row["skill"], criteria="\n".join(f"- {c}: {text}" for c, text in rubric.items()),
                        shape=json.dumps(shape, indent=2), files=", ".join(row.get("files") or []) or "none",
                        conversation=conversation(row.get("turns") or []))


def score_row(row, parsed, rubric, model):
    """The session_scores row for one judged content row."""
    scores = scoring.judge_scores(parsed, rubric)
    reasons = {c: (parsed["scores"][c].get("reason", "") if isinstance(parsed["scores"][c], dict) else "") for c in rubric}
    return {"content_row": row["id"], "content_id": row["content_id"], "skill": row["skill"], "run_ts": row["ts"],
            "plugin_version": row["plugin_version"], "judge_model": model, "scores": scores, "reasons": reasons}


def run_id(row):
    return f"{row['skill']}/{row['id']}"


def material(row, score):
    lines = [f"=== {run_id(row)}"]
    lines += [f"  {c} {score['scores'].get(c)}: {r}" for c, r in (score.get("reasons") or {}).items()]
    lines.append("conversation:\n" + conversation(row.get("turns") or []))
    return "\n".join(lines)


# --- Supabase, with the secret key ---

SCHEMAS = {"real": "public", "test": "sim"}


class Supabase:
    def __init__(self, target="real"):
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not key:
            refuse("SUPABASE_SERVICE_KEY is not set; this batch reads content, which only the secret key can")
        self.url = json.loads((ROOT / "telemetry.json").read_text())["url"].rstrip("/")
        # The profile headers pick the schema: the same tables exist in public and in sim.
        self.schema = SCHEMAS[target]
        self.headers = {"apikey": key, "Content-Type": "application/json",
                        "Accept-Profile": self.schema, "Content-Profile": self.schema}

    def get(self, table, query, page=500):
        rows = []
        while True:
            url = f"{self.url}/rest/v1/{table}?{query}&limit={page}&offset={len(rows)}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self.headers), timeout=60) as r:
                    batch = json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:300]
                if e.code == 404:
                    refuse(f"table {self.schema}.{table} not found (HTTP 404 {body}); run the migration in supabase/migrations/ "
                           "that creates it in the Supabase SQL editor")
                raise RuntimeError(f"{table} refused the read: HTTP {e.code} {body}") from e
            rows += batch
            if len(batch) < page:
                return rows

    def runs(self, ids):
        """Content runs with their turns, for these ids only: turns can be large."""
        out, ids = [], sorted(ids)
        for i in range(0, len(ids), 50):
            chunk = ",".join(str(x) for x in ids[i:i + 50])
            out += self.get("content", f"select=id,ts,plugin_version,content_id,skill,turns,files&id=in.({chunk})", page=50)
        return out

    def insert(self, table, rows):
        request = urllib.request.Request(f"{self.url}/rest/v1/{table}", data=json.dumps(rows).encode(), method="POST",
                                         headers={**self.headers, "Prefer": "return=minimal"})
        try:
            with urllib.request.urlopen(request, timeout=60):
                pass
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{table} refused the rows: HTTP {e.code} {e.read().decode(errors='replace')[:300]}") from e


def ask(prompt, cfg, log):
    """One judge call; the parsed JSON reply, or None after two tries."""
    with tempfile.TemporaryDirectory(prefix="daily-work-sessions-") as empty:
        for attempt in (1, 2):
            try:
                return scoring.parse_judge(flow.claude(prompt, empty, cfg["models"]["judge"], cfg, f"{log}-{attempt}.jsonl")["text"])
            except (ValueError, RuntimeError, subprocess.TimeoutExpired):
                continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Judge real sessions from the content table.")
    parser.add_argument("--target", choices=sorted(SCHEMAS), default="real",
                        help="real: schema public, real use (default); test: schema sim, test sessions")
    parser.add_argument("--limit", type=int, default=50, help="most runs to judge in one batch (default 50)")
    parser.add_argument("--days", type=int, default=7, help="analyse the runs judged in this many days (default 7)")
    parser.add_argument("--dry-run", action="store_true", help="say how many runs wait, judge nothing")
    args = parser.parse_args()
    cfg = json.loads((HERE / "config.json").read_text())
    db = Supabase(args.target)
    logs = Path(tempfile.mkdtemp(prefix="daily-work-sessions-logs-"))

    judged = {r["content_row"] for r in db.get("session_scores", "select=content_row")}
    runs = db.get("content", "select=id&kind=eq.run&order=id")
    waiting = [r["id"] for r in runs if r["id"] not in judged]
    print(f"{len(waiting)} runs wait to be judged, of {len(runs)} in {db.schema}.content")
    if args.dry_run:
        return
    new = []
    for row in db.runs(waiting[:args.limit]):
        rubric = cfg["session_rubrics"][row["skill"]]
        parsed = ask(judge_prompt(row, rubric), cfg, logs / f"judge-{row['id']}")
        try:
            new.append(score_row(row, parsed or {}, rubric, cfg["models"]["judge"]))
        except ValueError as e:
            print(f"  {run_id(row)}: not judged ({e})")
    if new:
        db.insert("session_scores", new)
    print(f"judged {len(new)} runs")

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    scores = db.get("session_scores", f"select=content_row,scores,reasons&judged_at=gte.{urllib.parse.quote(since.isoformat())}")
    by_row = {s["content_row"]: s for s in scores}
    picked = db.runs([r["id"] for r in runs if r["id"] in by_row])
    if not picked:
        print("no judged runs in the period; no analysis")
        return
    parts = [material(r, by_row[r["id"]]) for r in picked]
    prompt = ANALYSE.format(n=len(parts), groups=analyse.MAX_GROUPS, bullets=analyse.BULLETS, words=analyse.MAX_WORDS,
                            shape=json.dumps(analyse.SHAPE, indent=2), materials="\n\n".join(parts))
    for attempt in (1, 2, 3):
        try:
            result = analyse.check(ask(prompt, cfg, logs / f"analyse-{attempt}") or {}, {run_id(r) for r in picked})
            break
        except ValueError as e:
            error = e
            prompt = analyse.retry(prompt, e)
    else:
        refuse(f"no usable analysis: {error}")
    db.insert("session_analysis", [{"period_start": since.isoformat(), "period_end": datetime.now(timezone.utc).isoformat(),
                                    "runs": len(picked), "judge_model": cfg["models"]["judge"], **result}])
    print(f"analysis of {len(picked)} runs: {len(result['topics'])} topics, {len(result['confusion'])} kinds of confusion")


if __name__ == "__main__":
    main()
