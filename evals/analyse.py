"""The analysis of a complete run: one model call over every scenario run's conversations and
the judge's reasons, grouped into topics and confusion, three short bullets each. Written to
analysis.json next to the run's summary, for the dashboard's Eval tab.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import flow
import scoring

PARTS = ("topics", "confusion")
MAX_GROUPS, BULLETS, MAX_WORDS, CUT = 6, 3, 25, 2500

PROMPT = """You are analysing an offline eval of daily-work, a plugin that turns a person's request into a
brief, grills them into a task file, does the work and records the result. A simulated user
answered from a fixed card. Below are {n} runs: for each, the request, the grill conversation,
the work conversation, and the judge's scores (1 to 5) with reasons for every step.

Write two parts.

topics: the kinds of things the conversations dealt with: what the grill asked about and what
the work had to produce, grouped into at most {groups} kinds across all runs (for example
"audience and purpose", "deadlines and dates", "figures from the documents"). For each kind,
exactly {bullets} bullets on how the plugin handled it: what worked, what fell short, what to
keep or change.

confusion: the moments where the plugin, the simulated user or one step and the next did not
understand each other: a wrong assumption written as fact, an answer misread, an instruction
not followed, a step doing another step's job, a question the documents already answered. At
most {groups} kinds, exactly {bullets} bullets each.

Each bullet is one short plain sentence of at most {words} words about the plugin's behaviour,
specific enough to act on. No examples or figures in the bullet; the runs list carries them. Each
kind names the runs it comes from as "scenario/run" (for example "02-travel-cost-check/1"),
only runs that appear below. Order kinds by how many runs they cover, most first. Say nothing
that the material below does not show.

Reply with only this JSON:
{shape}

{materials}"""

SHAPE = {part: [{"name": "short name of the kind", "runs": ["scenario/run"], "bullets": ["one sentence"]}] for part in PARTS}


def cut(text, n=CUT):
    return text if len(text) <= n else text[:n] + " [cut]"


def conversation(turns):
    return "\n".join(f"{t['role']}: {cut(t['text'], 1200)}" for t in turns) or "(none)"


def material(name, run, record, scores, request):
    """One run's part of the prompt."""
    lines = [f"=== {name}/{run}", f"request: {cut(request, 800)}"]
    lines += [f"grill conversation:\n{conversation(record['transcripts'].get('grill', []))}",
              f"work conversation:\n{conversation(record['transcripts'].get('work', []))}"]
    for step in scoring.STEPS:
        metrics, reasons = scores["metrics"].get(step, {}), scores["reasons"].get(step, {})
        done = "completed" if metrics.get("completed") else "NOT COMPLETED"
        judged = [f"  {c} {metrics.get(c)}: {r}" for c, r in reasons.items() if isinstance(r, str)]
        lines.append(f"{step} ({done}):\n" + ("\n".join(judged) or "  (no judge reasons)"))
    return "\n".join(lines)


def check(parsed, known_runs, parts=PARTS):
    """The analysis as the dashboard reads it: every part, at most MAX_GROUPS kinds of exactly
    BULLETS bullets of at most MAX_WORDS words, and only runs that exist. Refuses a reply that
    breaks any of it, so the call is made again."""
    out = {}
    for part in parts:
        groups = parsed.get(part)
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"analysis has no list '{part}'")
        out[part] = []
        for g in groups[:MAX_GROUPS]:
            bullets = [b.strip() for b in g.get("bullets", []) if isinstance(b, str) and b.strip()]
            if not str(g.get("name", "")).strip():
                raise ValueError(f"a kind in '{part}' has no name")
            if len(bullets) != BULLETS:
                raise ValueError(f"'{g['name']}' has {len(bullets)} bullets, not {BULLETS}")
            long = [b for b in bullets if len(b.split()) > MAX_WORDS]
            if long:
                raise ValueError(f"'{g['name']}' has a bullet over {MAX_WORDS} words: {long[0][:80]}")
            runs = [r for r in g.get("runs", []) if r in known_runs]
            out[part].append({"name": g["name"].strip(), "runs": runs, "bullets": bullets})
    return out


def retry(prompt, error):
    """The prompt again, with what was wrong with the last reply, so the next call can fix it."""
    first = prompt.split("\n\nYour last reply was refused: ")[0]
    return (f"{first}\n\nYour last reply was refused: {error}. Reply again with the whole JSON; keep every "
            f"bullet at {MAX_WORDS} words or fewer and give every kind exactly {BULLETS} bullets.")


def analyse(summary, folder, request_for, cfg):
    """Analyse the run in `folder` (evals/runs/<id>/<grill>) and write folder/analysis.json."""
    folder, parts, known = Path(folder), [], set()
    for r in summary["runs"]:
        run_dir = folder / r["scenario"] / f"run-{r['run']}"
        record = json.loads((run_dir / "run.json").read_text())
        scores = json.loads((run_dir / "scores.json").read_text())
        parts.append(material(r["scenario"], r["run"], record, scores, request_for(r["scenario"])))
        known.add(f"{r['scenario']}/{r['run']}")
    prompt = PROMPT.format(n=len(parts), groups=MAX_GROUPS, bullets=BULLETS, words=MAX_WORDS,
                           shape=json.dumps(SHAPE, indent=2), materials="\n\n".join(parts))
    with tempfile.TemporaryDirectory(prefix="daily-work-eval-analyse-") as empty:
        for attempt in (1, 2, 3):
            try:
                call = flow.claude(prompt, empty, cfg["models"]["judge"], cfg, folder / "logs" / f"analyse-{attempt}.jsonl")
                result = check(scoring.parse_judge(call["text"]), known)
                break
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
                error = e
                if isinstance(e, ValueError):
                    prompt = retry(prompt, e)
        else:
            raise RuntimeError(f"no usable analysis after three attempts: {error}")
    result = {"run_id": summary["meta"]["run_id"], "grill": summary["meta"]["grill"], "model": cfg["models"]["judge"],
              "runs": len(parts), **result}
    (folder / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result
