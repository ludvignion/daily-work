"""Markdown reports for an eval run, the side-by-side of two grill implementations, and the
summary rows for the Supabase table eval_runs.
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

import scoring

ROOT = Path(__file__).resolve().parent.parent


def num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def cell(r):
    """Mean, with the spread over the runs when there is one."""
    return f"{num(r['mean'])} ({num(r['min'])} to {num(r['max'])})" if r["min"] != r["max"] else num(r["mean"])


def table(rows, comparison):
    """One line per step and metric, with the baseline beside it when there is one."""
    compared = {(c["scenario"], c["step"], c["metric"]): c for c in comparison}
    lines = ["| Step | Metric | Mean (spread) | Baseline | Change | |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        c = compared.get((r["scenario"], r["step"], r["metric"]))
        flag = "" if not c or r["metric"] in scoring.INFORMATIONAL else "REGRESSION" if c["regression"] else "look" if c["beyond"] else ""
        base = num(c["baseline"]) if c else ""
        # delta is signed so that negative is worse, whichever way the metric runs.
        change = ("better " if c["delta"] > 0 else "worse " if c["delta"] < 0 else "same ") + num(abs(c["delta"])) if c else ""
        lines.append(f"| {r['step']} | {r['metric']} | {cell(r)} | {base} | {change} | {flag} |")
    return lines


def write(summary, baseline, noise=None):
    """The report for one grill implementation. `baseline` is a saved summary, or None; `noise`
    a saved calibration (run.py calibrate), or None."""
    meta, rows = summary["meta"], summary["rows"]
    calibration = noise["metrics"] if noise else None
    comparison = scoring.compare(rows, baseline["rows"], meta["config"]["thresholds"], calibration) if baseline else []
    lines = [f"# daily-work eval {meta['run_id']}", ""]
    lines += [f"- Date: {meta['date']}", f"- Plugin version: {meta['plugin_version']} (commit {meta['commit']})",
              f"- Grill implementation: {meta['grill']} (sha256 {meta['grill_sha256'][:12]})",
              f"- Models: plugin {meta['config']['models']['plugin']}, user {meta['config']['models']['user']}, "
              f"judge {meta['config']['models']['judge']}",
              f"- Steps run: {', '.join(meta['steps'])}",
              f"- Scenarios: {len(meta['scenarios'])}, runs per scenario: {meta['runs_per_scenario']}",
              f"- Tokens: {summary['totals']['tokens']} = input {summary['totals']['tokens_input']} + cached input "
              f"{summary['totals']['tokens_cached']} + output {summary['totals']['tokens_output']} "
              f"(of which judge {summary['totals']['judge_tokens']})",
              f"- Runtime: {summary['totals']['seconds'] / 60:.1f} minutes of model time, "
              f"{summary['totals']['wall_seconds'] / 60:.1f} minutes on the clock",
              f"- Cost at API prices: {summary['totals']['cost_usd']:.2f} USD (of which judge "
              f"{summary['totals']['judge_cost_usd']:.2f}). On a subscription login this is usage, not a charge.", ""]
    if baseline:
        lines += [f"Baseline: run {baseline['meta']['run_id']}, plugin {baseline['meta']['plugin_version']}, "
                  f"{baseline['meta']['date']}.", ""]
        lines += [f"Noise calibrated from runs {' and '.join(noise['runs'])}." if noise else
                  "Noise not calibrated (run.py calibrate); the config thresholds alone decide.", ""]
        found = scoring.regressions(comparison)
        if found:
            lines += [f"**{len(found)} regression{'s' if len(found) > 1 else ''} overall. First step with a drop: {scoring.first_drop(comparison)}.**", ""]
            for c in found:
                where = [l["scenario"] for l in scoring.looks(comparison, step=c["step"], metric=c["metric"])]
                lines.append(f"- {c['step']}, {c['metric']}: {num(c['baseline'])} to {num(c['now'])}"
                             + (f"; past its limit in {', '.join(where)}" if where else ""))
            lines.append("")
        else:
            lines += ["**No regressions against the baseline.**", ""]
        lines += ["A scenario row marked \"look\" dropped past its own limit. It is not a regression on its own: "
                  "three runs of one scenario vary too much.", ""]
    else:
        lines += ["No baseline saved for this grill implementation; nothing to compare against.", ""]
    failed = [r for r in summary["runs"] if r["error"]]
    if failed:
        lines += ["Runs that stopped on an error:"] + [f"- {r['scenario']} run {r['run']}: {r['error']}" for r in failed] + [""]
    lines += ["## Overall", ""] + table([r for r in rows if r["scenario"] == "ALL"], comparison) + [""]
    for name in meta["scenarios"]:
        lines += [f"## {name}", ""]
        lines += table([r for r in rows if r["scenario"] == name], comparison) + [""]
    lines += ["## Config", "", "```json", json.dumps(meta["config"], indent=2), "```", ""]
    return "\n".join(lines)


def side_by_side(a, b):
    """Two grill implementations on the same scenarios: every grill and end-to-end metric, both columns."""
    na, nb = a["meta"]["grill"], b["meta"]["grill"]
    rows_b = {(r["scenario"], r["step"], r["metric"]): r for r in b["rows"]}
    lines = [f"# Grill comparison {a['meta']['run_id']}: {na} and {nb}", "",
             f"Plugin {a['meta']['plugin_version']}, {a['meta']['date']}, {a['meta']['runs_per_scenario']} runs per scenario. "
             "Better is marked for the metric's own direction; a difference inside the spread is not a finding.", ""]
    scenario = None
    for r in sorted(a["rows"], key=lambda r: (r["scenario"] != "ALL", r["scenario"])):
        other = rows_b.get((r["scenario"], r["step"], r["metric"]))
        if r["step"] not in ("grill", "work", "end_to_end") or other is None:
            continue
        if r["scenario"] != scenario:
            scenario = r["scenario"]
            lines += ["", f"## {'Overall' if scenario == 'ALL' else scenario}", "",
                      f"| Step | Metric | {na} | {nb} | Better |", "| --- | --- | --- | --- | --- |"]
        diff = r["mean"] - other["mean"]
        if r["metric"] in scoring.LOWER_IS_BETTER:
            diff = -diff
        lines.append(f"| {r['step']} | {r['metric']} | {cell(r)} | {cell(other)} | {na if diff > 0 else nb if diff < 0 else 'same'} |")
    return "\n".join(lines) + "\n"


def supabase_rows(summary):
    """One row per scenario and step, with that step's metrics as one JSON object."""
    meta, grouped = summary["meta"], {}
    for r in summary["rows"]:
        grouped.setdefault((r["scenario"], r["step"]), {})[r["metric"]] = {k: r[k] for k in ("mean", "min", "max", "sd", "n")}
    return [{"run_id": meta["run_id"], "run_date": meta["date"], "plugin_version": meta["plugin_version"],
             "grill": meta["grill"], "model": meta["config"]["models"]["plugin"], "scenario": scenario, "step": step,
             "metrics": metrics} for (scenario, step), metrics in grouped.items()]


# What went into each step and what came out of it, from the files a run saved.
STEP_IO = {
    "brief": (lambda f, request: request, lambda f: f.get("brief", "")),
    "grill": (lambda f, request: f.get("brief", ""), lambda f: f.get("task_after_grill", "")),
    "work": (lambda f, request: f.get("task_after_grill", ""), lambda f: outputs_text(f)),
    "record": (lambda f, request: f.get("task_after_work", ""), lambda f: f.get("task_final", "")),
    "end_to_end": (lambda f, request: request, lambda f: f.get("task_final", "")),
}


def outputs_text(files):
    """Every file the work step changed in outputs/, each under its path; the task file too when
    the work was written there."""
    parts = [f"=== {path}\n{text}" for path, text in sorted((files.get("outputs") or {}).items())]
    if files.get("task_after_work") and files.get("task_after_work") != files.get("task_after_grill"):
        parts.append(f"=== task file after work\n{files['task_after_work']}")
    return "\n\n".join(parts)


def step_rows(summary, folder, request_for):
    """One row per run, scenario and step for eval_steps, from each run's run.json and scores.json
    under `folder`. request_for(scenario) gives the request the run started from."""
    meta, rows = summary["meta"], []
    for r in summary["runs"]:
        run_dir = Path(folder) / r["scenario"] / f"run-{r['run']}"
        record = json.loads((run_dir / "run.json").read_text())
        scores = json.loads((run_dir / "scores.json").read_text())
        files, request = record.get("files") or {}, request_for(r["scenario"])
        for step in meta["steps"] + (["end_to_end"] if meta["steps"] == scoring.STEPS[:4] else []):
            given, made = STEP_IO[step]
            metrics = scores["metrics"].get(step, {})
            rows.append({
                "run_id": meta["run_id"], "run_date": meta["date"], "plugin_version": meta["plugin_version"],
                "grill": meta["grill"], "model": meta["config"]["models"]["plugin"], "scenario": r["scenario"],
                "run": r["run"], "step": step, "completed": bool(metrics.get("completed")),
                "input": given(files, request), "output": made(files),
                "transcript": (record.get("transcripts") or {}).get(step, []),
                "metrics": metrics, "checks": (scores.get("checks") or {}).get(step, {}),
                "reasons": (scores.get("reasons") or {}).get(step, {}),
            })
    return rows


def push(summary, steps=None):
    """Insert the summary rows into eval_runs and, when given, the step rows into eval_steps, with
    the publishable key from telemetry.json, which can insert and nothing else. Returns the rows
    written per table; 0 for a table that already holds the run, since it refuses a second copy."""
    return {"eval_runs": insert("eval_runs", supabase_rows(summary)),
            **({"eval_steps": insert("eval_steps", steps)} if steps is not None else {})}


def insert(table, rows):
    config = json.loads((ROOT / "telemetry.json").read_text())
    request = urllib.request.Request(
        f"{config['url'].rstrip('/')}/rest/v1/{table}", data=json.dumps(rows).encode(), method="POST",
        # The eval's tables live in the test group, with its simulated sessions.
        headers={"apikey": config["anon_key"], "Content-Type": "application/json", "Content-Profile": "test",
                 "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(request, timeout=60):
            pass
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return 0
        raise RuntimeError(f"{table} refused the rows: HTTP {e.code} {e.read().decode(errors='replace')[:300]}") from e
    return len(rows)
