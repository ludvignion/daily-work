#!/usr/bin/env python3
"""Offline eval for the daily-work plugin. See evals/README.md.

run.py run [--scenario NAME ...] [--runs N] [--grill NAME ...] [--jobs N] [--yes]
run.py step STEP --from RUN_FOLDER      one step again, from the repo saved before it
run.py baseline RUN_ID [--grill NAME]   save that run as the baseline for its grill implementation
run.py calibrate RUN_A RUN_B [--grill NAME] [--leave-out SCENARIO ...]
                                        how much two runs of the same code differ: the noise
run.py analyse RUN_ID [--grill NAME]    topics and confusion over a run's conversations
run.py push RUN_ID [--grill NAME]       summary rows to the Supabase table eval_runs
run.py pin NAME                         print the sha256 of a grill implementation's folder
"""
import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import analyse
import flow
import judge
import report
import scoring

HERE = Path(__file__).resolve().parent
RUNS, BASELINES, SCENARIOS = HERE / "runs", HERE / "baselines", HERE / "scenarios"


def refuse(why):
    print(f"refused: {why}")
    sys.exit(1)


def config():
    return json.loads((HERE / "config.json").read_text())


def check_pin(cfg, grill):
    """The grill implementation's folder must be the one the config names, byte for byte."""
    if grill not in cfg["grills"]:
        refuse(f"no grill implementation '{grill}' in config.json; there is: {', '.join(cfg['grills'])}")
    spec = cfg["grills"][grill]
    if not Path(spec["plugin_dir"]).expanduser().is_dir():
        refuse(f"{spec['plugin_dir']} is not a folder")
    actual = flow.tree_hash(spec["plugin_dir"])
    if actual != spec["sha256"]:
        refuse(f"grill implementation '{grill}' is not the pinned one: config.json says sha256 "
               f"{spec['sha256'] or '(none)'}, the folder is {actual}")
    return actual


def scenario_names(wanted):
    names = sorted(p.name for p in SCENARIOS.iterdir() if (p / "request.md").is_file())
    missing = [n for n in wanted or [] if n not in names]
    if missing:
        refuse(f"no scenario {', '.join(missing)}; there is: {', '.join(names)}")
    return wanted or names


def estimate(cfg, n):
    """Size of n runs, from the means per run of the latest full run, else the config's figures.
    Tokens and minutes hold on any login; dollars are what the tokens cost at API prices."""
    per_run, source = dict(cfg["estimate_per_run"]), "config.json"
    for summary in sorted(RUNS.glob("*/*/summary.json"), reverse=True):
        s = json.loads(summary.read_text())
        if s["meta"]["steps"] == flow.FLOW and s["runs"] and "judge_tokens" in s["totals"]:
            t, k = s["totals"], len(s["runs"])
            per_run = {"tokens": t["tokens"] / k, "minutes": t["seconds"] / 60 / k, "usd_at_api_prices": t["cost_usd"] / k}
            source = f"run {s['meta']['run_id']}"
            break
    return {key: n * v for key, v in per_run.items()}, source


def summarise(cfg, run_id, grill, sha, names, runs, steps, scored, wall):
    git = lambda *a: subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True).stdout.strip()
    step_totals = [m for s in scored for name, m in s["metrics"].items() if name != "end_to_end"]
    judge_cost = sum(s["judge_cost_usd"] for s in scored)
    judge_tokens = sum(s["judge_tokens"] for s in scored)
    return {
        "meta": {"run_id": run_id, "date": str(date.today()), "grill": grill, "grill_sha256": sha,
                 "plugin_version": json.loads((HERE.parent / "plugin.json").read_text())["version"],
                 "commit": git("rev-parse", "--short", "HEAD") + ("+changes" if git("status", "--porcelain") else ""),
                 "scenarios": names, "runs_per_scenario": runs, "steps": steps, "config": cfg},
        "rows": scoring.aggregate(scored),
        "runs": [{k: s[k] for k in ("scenario", "run", "error", "judge_cost_usd", "judge_tokens", "tokens_split", "metrics")} for s in scored],
        "totals": {"cost_usd": round(sum(m["cost_usd"] for m in step_totals) + judge_cost, 4),
                   "judge_cost_usd": round(judge_cost, 4),
                   **{k: sum(s["tokens_split"][k] for s in scored) for k in flow.TOKENS}, "judge_tokens": judge_tokens,
                   "seconds": round(sum(m["seconds"] for m in step_totals), 1), "wall_seconds": round(wall, 1)},
    }


def one_run(cfg, grill, name, n, out, steps, snapshot=None):
    scenario = flow.load_scenario(SCENARIOS / name)
    record = flow.run_flow(scenario, cfg, grill, out, steps, snapshot)
    scored = judge.score_run(record, scenario, cfg, out, steps)
    scored["run"] = n
    print(f"  {grill} {name} run {n}: " + ("stopped: " + scored["error"] if scored["error"] else
          ", ".join(f"{s} {'ok' if scored['metrics'][s]['completed'] else 'NOT COMPLETED'}" for s in steps)), flush=True)
    return scored


def finish(cfg, run_id, grill, sha, names, runs, steps, scored, wall):
    folder = RUNS / run_id / grill
    summary = summarise(cfg, run_id, grill, sha, names, runs, steps, scored, wall)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    base = BASELINES / f"{grill}.json"
    baseline = json.loads(base.read_text()) if base.is_file() and steps == flow.FLOW else None
    calibration = BASELINES / f"{grill}.noise.json"
    noise = json.loads(calibration.read_text()) if calibration.is_file() else None
    (folder / "report.md").write_text(report.write(summary, baseline, noise))
    print(f"report: {folder / 'report.md'}")
    # Only a complete run goes to the dashboard: every scenario, the configured runs each.
    # A trial on one scenario or with --runs 1 stays on disk; push it by hand if it should count.
    if steps == flow.FLOW and names == scenario_names(None) and runs == cfg["runs_per_scenario"]:
        run_analysis(summary, cfg)
        store(summary)
        # The standalone dashboard, rebuilt with this run in it.
        built = subprocess.run([sys.executable, str(HERE.parent / "dashboard" / "build.py")], capture_output=True, text=True)
        print(built.stdout.strip() or f"dashboard not rebuilt: {built.stderr.strip()[-300:]}")
    elif steps == flow.FLOW:
        print("not stored in eval_runs: not a complete run (every scenario, "
              f"{cfg['runs_per_scenario']} runs each)")
    return summary


def request_for(summary):
    run_date = date.fromisoformat(summary["meta"]["date"])
    return lambda name: flow.load_scenario(SCENARIOS / name, run_date)["request"]


def run_analysis(summary, cfg):
    """Topics and confusion over a complete run, for the dashboard. A run is kept without one if
    the analysis fails; `run.py analyse RUN_ID` makes it later."""
    meta = summary["meta"]
    try:
        result = analyse.analyse(summary, RUNS / meta["run_id"] / meta["grill"], request_for(summary), cfg)
        print(f"analysis: {len(result['topics'])} topics, {len(result['confusion'])} kinds of confusion")
    except (OSError, ValueError, KeyError, RuntimeError) as e:
        print(f"NO ANALYSIS: {e}. Later: python3 evals/run.py analyse {meta['run_id']}")


def store(summary):
    """Every complete run goes to Supabase: its summary to eval_runs, each step's input, output,
    conversation and scores to eval_steps. A run that cannot be stored is kept on disk and says
    so; `run.py push RUN_ID` stores it later."""
    meta = summary["meta"]
    try:
        steps = report.step_rows(summary, RUNS / meta["run_id"] / meta["grill"], request_for(summary))
        for table, n in report.push(summary, steps).items():
            print(f"stored in {table}: {n} rows" if n else f"{table} already holds this run; nothing written")
        # The dashboard build (dashboard/build.py) shows the runs marked stored.
        (RUNS / meta["run_id"] / meta["grill"] / "stored.json").write_text(json.dumps({"tables": ["eval_runs", "eval_steps"]}))
    except (OSError, ValueError, KeyError, RuntimeError) as e:
        print(f"NOT STORED: {e}. Later: python3 evals/run.py push {meta['run_id']}")


def cmd_run(args):
    cfg = config()
    grills = args.grill or [cfg["default_grill"]]
    pins = {g: check_pin(cfg, g) for g in grills}
    names = scenario_names(args.scenario)
    runs = args.runs or cfg["runs_per_scenario"]
    jobs_at_once = args.jobs or cfg["jobs"]
    size, source = estimate(cfg, len(names) * runs * len(grills))
    # Runs go in batches of jobs_at_once; a batch takes as long as one run.
    count = len(names) * runs
    minutes = size["minutes"] / (count * len(grills)) * -(-count // jobs_at_once) * len(grills)
    print(f"{len(names)} scenarios x {runs} runs x {len(grills)} grill implementations = {len(names) * runs * len(grills)} runs.\n"
          f"Estimated from {source}: {size['tokens'] / 1e6:.1f} million tokens, about {minutes:.0f} minutes "
          f"with {jobs_at_once} at a time, {size['usd_at_api_prices']:.2f} USD at API prices "
          "(what you pay on an API key; on a subscription login it is usage, not a charge).", flush=True)
    if not args.yes and input("Run? (yes/no) ").strip().lower() != "yes":
        refuse("not run")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    summaries = []
    for grill in grills:
        started = time.time()
        jobs = [(name, n) for name in names for n in range(1, runs + 1)]
        with ThreadPoolExecutor(max_workers=jobs_at_once) as pool:
            scored = list(pool.map(lambda j: one_run(cfg, grill, j[0], j[1], RUNS / run_id / grill / j[0] / f"run-{j[1]}",
                                                     flow.FLOW), jobs))
        summaries.append(finish(cfg, run_id, grill, pins[grill], names, runs, flow.FLOW, scored, time.time() - started))
    if len(summaries) == 2:
        path = RUNS / run_id / "compare.md"
        path.write_text(report.side_by_side(*summaries))
        print(f"side by side: {path}")


def cmd_step(args):
    """One step again from a saved run folder (evals/runs/<id>/<grill>/<scenario>/run-<n>)."""
    cfg = config()
    source = Path(args.source).resolve()
    if not (source / "run.json").is_file():
        refuse(f"{source} is not a run folder")
    grill, name = source.parent.parent.name, source.parent.name
    sha = check_pin(cfg, grill)
    before = flow.FLOW[flow.FLOW.index(args.step) - 1] if args.step != "brief" else None
    snapshot = source / "snapshots" / f"after-{before}" if before else None
    if snapshot and not snapshot.is_dir():
        refuse(f"{source} has no repo saved after {before}")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{args.step}"
    started = time.time()
    scored = [one_run(cfg, grill, name, 1, RUNS / run_id / grill / name / "run-1", [args.step], snapshot)]
    finish(cfg, run_id, grill, sha, [name], 1, [args.step], scored, time.time() - started)


def load_summary(run_id, grill):
    grill = grill or config()["default_grill"]
    path = RUNS / run_id / grill / "summary.json"
    if not path.is_file():
        refuse(f"no summary at {path}")
    return json.loads(path.read_text()), grill


def cmd_baseline(args):
    summary, grill = load_summary(args.run_id, args.grill)
    if summary["meta"]["steps"] != flow.FLOW:
        refuse("a baseline is a full run; this one ran a single step")
    BASELINES.mkdir(exist_ok=True)
    (BASELINES / f"{grill}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"baseline for {grill}: run {args.run_id} ({BASELINES / (grill + '.json')})")


def cmd_calibrate(args):
    """Two full runs of the same plugin, grill and scenarios: how far each metric moves on its own."""
    a, grill = load_summary(args.run_a, args.grill)
    b, _ = load_summary(args.run_b, args.grill)
    for key in ("steps", "grill_sha256", "runs_per_scenario"):
        if a["meta"][key] != b["meta"][key]:
            refuse(f"the two runs differ in {key}; calibrate from two runs of the same setup")
    if a["meta"]["steps"] != flow.FLOW:
        refuse("calibrate from full runs, not single steps")
    leave_out = args.leave_out or []
    metrics = scoring.noise(a["rows"], b["rows"], leave_out)
    BASELINES.mkdir(exist_ok=True)
    path = BASELINES / f"{grill}.noise.json"
    path.write_text(json.dumps({"runs": [args.run_a, args.run_b], "commits": [a["meta"]["commit"], b["meta"]["commit"]],
                                "left_out": leave_out, "metrics": metrics}, indent=2))
    print(f"noise for {grill} from runs {args.run_a} and {args.run_b}, {len(metrics)} metrics: {path}")


def cmd_analyse(args):
    summary, _ = load_summary(args.run_id, args.grill)
    if summary["meta"]["steps"] != flow.FLOW:
        refuse("analyse a full run, not a single step")
    run_analysis(summary, config())


def cmd_push(args):
    summary, _ = load_summary(args.run_id, args.grill)
    store(summary)


def cmd_pin(args):
    cfg = config()
    if args.name not in cfg["grills"]:
        refuse(f"no grill implementation '{args.name}' in config.json")
    print(flow.tree_hash(cfg["grills"][args.name]["plugin_dir"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline eval for the daily-work plugin.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="the full flow on the scenarios")
    p.add_argument("--scenario", action="append", help="a scenario folder name; repeat for several (default: all)")
    p.add_argument("--runs", type=int, help="runs per scenario (default: config.json)")
    p.add_argument("--grill", action="append", help="a grill implementation from config.json; give two for a side by side")
    p.add_argument("--jobs", type=int, help="runs at the same time (default: config.json)")
    p.add_argument("--yes", action="store_true", help="do not ask after printing the estimated cost")
    p.set_defaults(run=cmd_run)
    p = sub.add_parser("step", help="one step again, from the repo a run saved before it")
    p.add_argument("step", choices=flow.FLOW)
    p.add_argument("--from", dest="source", required=True, help="a run folder: evals/runs/<id>/<grill>/<scenario>/run-<n>")
    p.set_defaults(run=cmd_step)
    p = sub.add_parser("baseline", help="save a run as the baseline")
    p.add_argument("run_id")
    p.add_argument("--grill")
    p.set_defaults(run=cmd_baseline)
    p = sub.add_parser("calibrate", help="measure the noise from two runs of the same code")
    p.add_argument("run_a")
    p.add_argument("run_b")
    p.add_argument("--grill")
    p.add_argument("--leave-out", action="append", help="a scenario that changed between the two runs")
    p.set_defaults(run=cmd_calibrate)
    p = sub.add_parser("analyse", help="topics and confusion over a run's conversations")
    p.add_argument("run_id")
    p.add_argument("--grill")
    p.set_defaults(run=cmd_analyse)
    p = sub.add_parser("push", help="write a run's summary rows to Supabase")
    p.add_argument("run_id")
    p.add_argument("--grill")
    p.set_defaults(run=cmd_push)
    p = sub.add_parser("pin", help="print the sha256 of a grill implementation's folder")
    p.add_argument("name")
    p.set_defaults(run=cmd_pin)
    args = parser.parse_args()
    args.run(args)
