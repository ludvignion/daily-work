#!/usr/bin/env python3
"""Build dashboard/out/index.html: the dashboard page, standalone, with the Eval tab filled from
the eval runs saved on this machine. Open the file in a browser; no key and no connection needed.

python3 dashboard/build.py [--target real|test]

The runs are those stored in Supabase (a run folder with stored.json), so the page shows what the
tables eval_runs and eval_steps hold. The Usage and Observability tabs read real sessions through
the claude.ai Supabase connector; here they stay empty unless SUPABASE_SERVICE_KEY is set: then
they are read from the dashboard_* views (one per query) into the file, a snapshot of that moment:
of real use (schema public, the default), or with --target test of the test group (schema sim).
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "evals"))
import report  # noqa: E402
import run as runner  # noqa: E402

INFORMATIONAL = {"turns", "tokens", "tokens_input", "tokens_cached", "tokens_output", "cost_usd", "seconds", "rounds"}
STEPS = ["brief", "grill", "work", "record", "end_to_end"]


def stored_runs(runs_dir):
    """Run folders (evals/runs/<id>/<grill>) that were stored in Supabase, oldest first."""
    return sorted(p.parent for p in Path(runs_dir).glob("*/*/stored.json"))


def overview(summaries):
    """As queries/eval_overview.sql: the overall mean, low and high of each score per run."""
    rows = []
    for s in summaries:
        for r in report.supabase_rows(s):
            if r["scenario"] != "ALL":
                continue
            for metric, v in sorted(r["metrics"].items()):
                if metric not in INFORMATIONAL:
                    rows.append({"run_id": s["meta"]["run_id"], "run_date": s["meta"]["date"],
                                 "version": s["meta"]["plugin_version"], "step": r["step"], "metric": metric,
                                 "mean": v["mean"], "low": v["min"], "high": v["max"]})
    return rows


def tokens(summaries):
    """As queries/eval_tokens.sql: size of each run."""
    out = []
    for s in summaries:
        e2e = next(r for r in s["rows"] if r["scenario"] == "ALL" and r["step"] == "end_to_end" and r["metric"] == "seconds")
        out.append({"run_id": s["meta"]["run_id"], "run_date": s["meta"]["date"], "tokens": s["totals"]["tokens"],
                    "minutes_per_run": round(e2e["mean"] / 60, 1), "scenarios": len(s["meta"]["scenarios"]),
                    "runs_per_scenario": s["meta"]["runs_per_scenario"]})
    return out


def scenarios(summary):
    """As queries/eval_scenarios.sql: per scenario of one run, weakest end to end first."""
    pick = {"end_to_end": ["request_to_done"], "work": ["meets_expected"], "grill": ["essential_share", "questions_docs_answer"],
            "record": ["caveats_honest"]}
    by = {}
    for r in summary["rows"]:
        if r["scenario"] == "ALL":
            continue
        row = by.setdefault(r["scenario"], {"scenario": r["scenario"]})
        if r["metric"] in pick.get(r["step"], []):
            row[r["metric"]] = r["mean"]
        if r["step"] == "end_to_end" and r["metric"] == "seconds":
            row["minutes"] = round(r["mean"] / 60, 1)
    return sorted(by.values(), key=lambda r: (r.get("request_to_done") is not None, r.get("request_to_done") or 0, r["scenario"]))


def steps(summary, folder):
    """As queries/eval_steps.sql: every step of one run, input and output cut at 3 000 characters."""
    rows = report.step_rows(summary, folder, runner.request_for(summary))
    return [{"run_id": r["run_id"], "scenario": r["scenario"], "run": r["run"], "step": r["step"],
             "completed": r["completed"], "metrics": r["metrics"], "reasons": r["reasons"],
             "input": r["input"][:3000], "output": r["output"][:3000], "messages": len(r["transcript"])} for r in rows]


def analysis(folder):
    """Topics and confusion of one run (evals/analyse.py), one row per kind."""
    path = Path(folder) / "analysis.json"
    if not path.is_file():
        return None
    a = json.loads(path.read_text())
    return [{"part": part, "name": g["name"], "run_count": len(g["runs"]), "runs_total": a["runs"],
             "bullets": g["bullets"], "runs": g["runs"]} for part in ("topics", "confusion") for g in a[part]]


# The Usage and Observability sources, read from the views in
# supabase/migrations/20261014030000_dashboard_views.sql: each is the query of the same name.
LIVE = ["kpis", "funnel", "daily", "tasks", "versions", "cycle", "hourly", "traces", "judge", "session_analysis"]


def live_rows(target="real"):
    """Rows of every LIVE view, read with SUPABASE_SERVICE_KEY when it is set; empty otherwise.
    The page's own loaders read them, as they read the claude.ai connector's answer."""
    if not os.environ.get("SUPABASE_SERVICE_KEY"):
        return {}
    import sessions
    db = sessions.Supabase(target)
    return {name: db.get(f"dashboard_{name}", "select=*") for name in LIVE}


def datasets(runs_dir):
    folders = stored_runs(runs_dir)
    if not folders:
        return {}
    summaries = [json.loads((f / "summary.json").read_text()) for f in folders]
    latest, folder = summaries[-1], folders[-1]
    data = {"eval_overview": overview(summaries), "eval_tokens": tokens(summaries),
            "eval_scenarios": scenarios(latest), "eval_steps": steps(latest, folder)}
    found = analysis(folder)
    if found is not None:
        data["eval_analysis"] = found
    return data


# Stands in for the claude.ai dashboard runtime: the same dash.data / dash.calc / dash.onData the
# page calls, over data built into the file. A source not built in reads as "connect".
SHIM = """
(() => {
  const DATA = JSON.parse(document.getElementById('dash-data').textContent);
  const LIVE = JSON.parse(document.getElementById('dash-live').textContent);
  const calcs = {}, loaders = {}, loaded = {}, listeners = [];
  // A live source goes through the page's loader, wrapped as the connector answers.
  const live = (id) => {
    if (!(id in loaded)) {
      const answer = { result: '<untrusted-data-0>\\n' + JSON.stringify(LIVE[id]) + '\\n</untrusted-data-0>' };
      try { loaded[id] = { status: 'ok', data: loaders[id].fn({ answer }).rows, meta: [] }; }
      catch (e) { loaded[id] = { status: 'error', data: [], message: String(e.message || e) }; }
    }
    return loaded[id];
  };
  window.dash = {
    colors: ['#376B94', '#E987BE', '#6E8B2A', '#A04F7B', '#D23A1F', '#A8D8FA', '#FFFF73', '#111111'],
    loader(id, spec) { loaders[id] = spec; },
    calc(id, spec) { calcs[id] = spec; },
    data(id) {
      if (id in LIVE && loaders[id]) return live(id);
      if (id in DATA) { const rows = DATA[id]; return { status: 'ok', data: rows, columns: rows.length ? Object.keys(rows[0]) : [], meta: [] }; }
      if (calcs[id]) {
        const ins = calcs[id].inputs.map((i) => window.dash.data(i));
        const bad = ins.find((x) => x.status !== 'ok');
        if (bad) return { status: bad.status, data: [], message: bad.message };
        return { status: 'ok', data: calcs[id].fn(...ins.map((x) => x.data)), meta: [] };
      }
      return { status: 'connect', data: [], message: 'Real-session data loads only in the claude.ai dashboard.' };
    },
    onData(fn) { listeners.push(fn); fn(); },
    setLink(name) { history.replaceState(null, '', '#' + name); },
    refresh() {}, params() { return {}; }, setParams() {}, resetParams() {},
  };
  let width = innerWidth;
  addEventListener('resize', () => { if (innerWidth !== width) { width = innerWidth; listeners.forEach((f) => f()); } });
})();
"""

TOKENS_CSS = """
:root {
  --font-anthropic-sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --color-fg: #111111; --color-fg-muted: #3B3B3B; --color-bg: #FBF9F4; --color-panel: #FFFFFF;
  --color-border-line: rgba(17,17,17,0.15); --color-ok: #6E8B2A; --color-warn: #B07A00; --color-bad: #D23A1F;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 14px; --cds-gap-lg: 20px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 18px; --cds-radius: 10px;
  --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 18px; --cds-font-size-title: 28px;
  --cds-font-weight-medium: 600; --cds-surface-popover: #FFFFFF; --cds-border: rgba(17,17,17,0.2);
  --cds-shadow-popover: 0 4px 16px rgba(0,0,0,0.12); --cds-text-secondary: #3B3B3B; --cds-dur-slow: 300ms;
}
body { margin: 0; background: var(--color-bg); color: var(--color-fg); }
#dash-root { max-width: 1400px; margin: 0 auto; padding: 16px; }
"""


def blob(data):
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def page(data, live=None):
    """The standalone page: the dashboard's own markup, the data, the live rows and the stand-in runtime."""
    body = (HERE / "index.html").read_text()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>daily-work dashboard</title>
<style>{TOKENS_CSS}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script type="application/json" id="dash-data">{blob(data)}</script>
<script type="application/json" id="dash-live">{blob(live or {})}</script>
<script>{SHIM}</script>
</head>
<body>
<div id="dash-root">
{body}
</div>
</body>
</html>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the standalone dashboard page.")
    parser.add_argument("--target", choices=["real", "test"], default="real",
                        help="Usage and Observability from real use (default) or the test group")
    target = parser.parse_args().target
    data, live = datasets(ROOT / "evals" / "runs"), live_rows(target)
    out = HERE / "out" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page(data, live))
    runs = sorted({r["run_id"] for r in data.get("eval_overview", [])})
    print(f"{out}: Eval tab from {len(runs)} stored runs ({', '.join(runs) or 'none'})"
          + ("" if "eval_analysis" in data else "; no analysis for the latest run (run.py analyse RUN_ID)"))
    print(f"Usage and Observability ({target}): " + (", ".join(f"{n} {len(r)}" for n, r in live.items()) + " rows"
                                         if live else "empty (set SUPABASE_SERVICE_KEY to read them)"))
    print(f"open file://{out}#eval")
