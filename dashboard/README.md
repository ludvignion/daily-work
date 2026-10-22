# Dashboard

A first draft of the daily-work dashboard, with three tabs: Usage and Observability on real
sessions, and Eval on simulated data from the offline eval (`evals/`). It runs as a
dashboard on claude.ai, which reads Supabase through its Supabase connector; it does not open as
a plain web page, because it uses that runtime's `dash` object (`dash.loader`, `dash.data`,
`dash.calc`) and its style tokens. No key is in these files: the connector holds the access.

| Path | What |
| --- | --- |
| `index.html` | the page: styles, markup, the loaders for each data source, the drawing |
| `queries/<source>.sql` | the read-only query behind each data source, named as in `index.html` |
| `build.py` | builds `out/index.html`, the page standalone (see below) |

## Standalone

```
python3 dashboard/build.py
```

writes `dashboard/out/index.html` (git-ignored), which opens in any browser with no key and no
connection. A small stand-in for the claude.ai runtime serves the page its data from the file.
The Eval tab is filled from the eval runs saved on this machine that were stored in Supabase
(a run folder with `stored.json`), so it shows what `eval_runs` and `eval_steps` hold; the
analysis is the latest run's `analysis.json`. Rebuild after a run.

The Usage and Observability tabs read real sessions, so they stay empty, marked "Failed to
load", unless the secret key is set:

```
SUPABASE_SERVICE_KEY=<secret key> python3 dashboard/build.py [--target live|test]
```

`--target live` (the default) shows real use, schema `live`; `--target test` shows the test
group, schema `test`: the eval's simulated sessions and your own tries with
`DAILY_WORK_TARGET=test`.

Then the build reads the views `dashboard_<source>` in Supabase, one per query in `queries/`
(`supabase/migrations/20261022000000_live_and_test.sql`), and the page's own loaders read
the rows as on claude.ai. Only the secret key can read those views. The file is then a snapshot
of real sessions, including the judge's reasons: it is git-ignored, and the 30-day cleanup in
Supabase does not reach it, so rebuild or delete it. "What grill asks" stays empty: its two
attached files are not here.

The Usage and Observability queries read `live.events` (and, for the test group's views, the
same tables in `test`). The Eval queries read only `test.eval_runs` and `test.eval_steps`, which
hold nothing from real sessions.

## Data sources

| Source | From | Shown on |
| --- | --- | --- |
| `kpis` | `queries/kpis.sql` | Usage headline, Observability headline |
| `funnel` | `queries/funnel.sql` | Usage: brief, grill, record |
| `daily` | `queries/daily.sql` | Usage: skill runs per day |
| `tasks` | `queries/tasks.sql` | Usage: tasks table |
| `cycle` | `queries/cycle.sql` | Observability: tasks closed, cycle time |
| `hourly` | `queries/hourly.sql` | Observability: completion by hour |
| `versions` | `queries/versions.sql` | Observability: release marks on the hourly chart |
| `traces` | `queries/traces.sql` | Observability: task traces |
| `judge` | `queries/judge.sql` (`session_scores`) | Observability: LLM judge |
| `session_analysis` | `queries/session_analysis.sql` | Observability: topics and confusion |
| `grill_questions` | attached file `grill_questions_v2.json` | Observability: what grill asks |
| `grill_themes` | attached file `grill_themes.json` | Observability: what grill asks |
| `grill_topics`, `grill_summary` | worked out in the page from the two above | Observability: what grill asks |
| `eval_overview` | `queries/eval_overview.sql` | Eval: headline, scores per run |
| `eval_tokens` | `queries/eval_tokens.sql` | Eval: size of each run, under scores per run |
| `eval_scenarios` | `queries/eval_scenarios.sql` | Eval: scenarios of the latest run, weakest first |
| `eval_steps` | `queries/eval_steps.sql` | Eval: each step's input, output and the judge's reasons |
| `eval_analysis` | the latest run's `analysis.json`, standalone build only | Eval: topics and confusion |

The two attached files are not in this folder yet.
