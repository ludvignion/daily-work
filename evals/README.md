# Offline eval

Runs the whole daily-work flow (brief, grill, work, record) on fixed scenarios with a simulated
user, scores every step and the flow end to end, and compares the result with a saved baseline.
Use it to catch a regression when the plugin, a skill or the model changes, to see which step a
drop first appears in, and to compare two grill implementations on the same scenarios.

Everything here is simulated data, and it stays apart from real use. Every temporary work repo
sets `DAILY_WORK_TARGET=test`, so its telemetry and content logging go to the test group, the
schema `test` (`test.events`, `test.content`, `test.feedback`), never to the real tables in
`live`. The eval's own tables, `test.eval_runs` and `test.eval_steps`, are in the test group too.
A run stops with an error if that switch changed during the run. The simulated sessions can then
be judged and shown like real ones: `sessions.py --target test`, `build.py --target test`.

## What a run does

For each scenario and run, `run.py`:

1. makes a temporary work repo with `scripts/init.sh` and copies in the scenario's `seed/`, if any;
2. sends `/daily-work:brief <request>` through `claude -p`, with this repo's working copy as the
   plugin, and lets the simulated user answer until `<project>/briefs/<task-name>.md` exists;
3. puts the scenario's `docs/` in `<project>/inputs/` and names them in `sources.md`;
4. runs the grill implementation on the brief until `<project>/tasks/<task-name>.md` exists and
   the brief is gone;
5. sends `work on <task-name>` until something in `<project>/outputs/` has changed;
6. sends `/daily-work:record <task-name>` in the same session as the work;
7. scores each step and writes the report.

Only the two plugins named on the command line are loaded; plugins installed on your machine
are left out.

## Running

Needs `claude` on the path and logged in, and Python 3. No packages to install.

```
python3 evals/run.py run                                    # every scenario, 3 runs each
python3 evals/run.py run --scenario 01-supplier-memo --runs 1
python3 evals/run.py baseline <run-id>                      # save that run as the baseline
python3 evals/run.py calibrate <run-id-a> <run-id-b>        # measure the noise between two runs
python3 evals/run.py push <run-id>                          # store a run in Supabase by hand
python3 evals/run.py analyse <run-id>                       # topics and confusion, by hand
python3 -m unittest tests.test_evals                        # the scoring and comparison tests
```

`run` prints the number of runs and their estimated size (tokens, minutes, and dollars at API
prices), then asks before it starts; `--yes` skips the question. The estimate comes from the
latest full run, or from `estimate_per_run` in `config.json` when there is none.

The dollar figure is what the tokens cost at API prices. That is your bill when `claude` runs on
an API key. When `claude` is logged in with a subscription, nothing is charged per run; the
tokens count against the plan's usage, and tokens and minutes are the figures to go by.

Output goes to `evals/runs/<run-id>/<grill>/`, which git ignores:

| Path | What |
| --- | --- |
| `report.md` | per step, per scenario and overall, against the baseline |
| `summary.json` | the same numbers, the config, tokens, runtime and cost at API prices |
| `<scenario>/run-<n>/run.json` | transcripts of every step and every file the run produced |
| `<scenario>/run-<n>/scores.json` | metrics, the file checks one by one, and the judge's reasons |
| `<scenario>/run-<n>/logs/` | the raw event log of every model call, tool calls included |
| `<scenario>/run-<n>/snapshots/after-<step>/` | the work repo as it was after each step |

### One step

```
python3 evals/run.py step grill --from evals/runs/<run-id>/<grill>/<scenario>/run-1
```

Starts from the repo that run saved before the step and runs only that step, once. Use it to
iterate on one skill without paying for the whole flow. A single step is never compared with the
baseline, and `record` run this way starts a new session, so it has the files but not the
conversation from the work.

### Baseline

`baseline <run-id>` copies that run's `summary.json` to `evals/baselines/<grill>.json`. Commit
that file. Every later full run with the same grill implementation is compared against it.

Only the overall rows (the mean over all scenarios) can be a regression. Three runs of one
scenario vary too much for one drop there to mean anything: two runs of the same code on
2026-10-14 differed by up to 4.7 questions and 0.7 judge points in single scenarios, which the
old per-scenario check flagged as 17 regressions. A scenario row whose drop is past its own
limit is marked "look" in the report, and each overall regression names the scenarios that
were.

A drop is past its limit when it is larger than both of these:

- the threshold in `config.json`, the floor:

  | Kind of metric | Threshold | Default |
  | --- | --- | --- |
  | a 1 to 5 judge score | `score`, in points | 0.5 |
  | a share from 0 to 1 | `share` | 0.15 |
  | a count where lower is better | `count_relative`, share of the baseline | 0.25 |

- the noise, when it has been measured: `noise_multiplier` (default 3) times the standard
  deviation of the scenario differences between two runs of the same code. For the overall row
  that is divided by the square root of the number of scenarios.

Measure the noise from two full runs of the same plugin, grill and scenarios:

```
python3 evals/run.py calibrate <run-id-a> <run-id-b> [--leave-out <scenario>]
```

It writes `evals/baselines/<grill>.noise.json`; commit it with the baseline. Leave out a
scenario that changed between the two runs. Recalibrate when the scenarios or the models change.

The report names the first step in the flow with a regression. Turns, tokens, cost and runtime
are shown with their change but never counted as a regression.

### Two grill implementations

Add the second one under `grills` in `config.json` (see "Pinning a grill implementation"), then:

```
python3 evals/run.py run --grill mattpocock-1.2.3 --grill ours
```

Each gets its own report, and `evals/runs/<run-id>/compare.md` puts the grill, work and
end-to-end metrics side by side.

### Pinning a grill implementation

A grill implementation is a plugin folder, the command that starts it (`{brief}` is the path of
the brief) and the sha256 of the folder's contents:

```
python3 evals/run.py pin mattpocock-1.2.3
```

prints the sha256; put it in `config.json`. A run refuses to start if the folder no longer
matches, so a plugin update cannot change the results unnoticed. The `.in_use/` lock files
Claude Code writes into the folder are left out of the sum. The sha256 is in every report.
Whatever the implementation, the generated `AGENTS.md` is what tells the session to end by
writing the task file and deleting the brief.

## Analysis

After a complete run, one more call to the judge model reads every run's grill and work
conversations and the judge's reasons, and writes `analysis.json` next to the run's summary:

- **Topics**: what the conversations dealt with (audience, dates, figures from the documents and
  so on), at most six kinds, three bullets each on how the plugin handled them.
- **Confusion**: where the plugin, the simulated user or two steps did not understand each
  other, at most six kinds, three bullets each.

Every bullet is one sentence of at most 25 words; a reply that breaks this is asked for again, told what was wrong, up to three times.

Each kind names the runs it comes from. The dashboard's Eval tab shows the latest run's
(`dashboard/build.py`). It is a model's reading, like the judge's: check a claim against the
steps it names before acting on it. `analyse <run-id>` makes it for a run that has none.

## Real sessions

`evals/sessions.py` judges real sessions afterwards, in a batch, with the same judge model:

```
SUPABASE_SERVICE_KEY=... python3 evals/sessions.py [--target live|test] [--limit 50] [--days 7] [--dry-run]
```

`--target live` (the default) judges real use, the tables in `live`; `--target test` judges
the test group, the same tables in the schema `test` (`supabase/migrations/20261022000000_live_and_test.sql`):
the eval's simulated sessions and your own tries with `DAILY_WORK_TARGET=test`.

1. Every brief, grill and record run in the table `content` that has no score yet is scored 1
   to 5 on the rubric for its skill (`session_rubrics` in `config.json`), into `session_scores`.
2. The runs judged in the last `--days` are grouped into topics and confusion, three bullets
   each as for the eval, into `session_analysis`.

The judge sees what `content` holds: the person's prompts, the assistant's replies and the
names of the files written, not their contents. So the rubric is about the conversation (were
the questions needed, was it clear what was settled), not the output. It is told not to quote
people, but its words can still echo theirs, so reasons are cleared and analyses deleted after
30 days, as `content` itself is. Both tables are read and written with the secret key only
(`supabase/migrations/20261014020000_session_judging.sql`); run the batch in your own terminal
or as a scheduled job, at least every 30 days, before `content` deletes the runs.

## What is scored

Checks on files are exact. Judge scores are 1 to 5 per criterion with a one-sentence reason, by
the rubric in `config.json`. The report gives the mean and the spread (lowest to highest) over
the runs of a scenario; "Overall" is the mean of the scenario means.

| Step | From the files | From the judge |
| --- | --- | --- |
| brief | `layout_share`: heading, Project, Written and Id lines, a description | `goal_captured`, `scope_right`, `nothing_invented` |
| grill | `layout_share`: the task file layout AGENTS.md asks for, Ask equal to the brief, Id copied, Result and Caveats left alone, brief deleted | `essential_share` (essential hidden facts found in the task file), `facts_share`, `stated_share` (found facts written as stated, not assumed), `questions`, `questions_docs_answer` (lower is better), `task_quality` |
| work | | `meets_task`, `meets_expected` |
| record | `checks_share`: Ask and Spec unchanged, Result and Caveats written, README line done, commit made | `result_true`, `caveats_honest` |
| end to end | `completed`, total `turns`, `tokens`, `tokens_input`, `tokens_cached`, `tokens_output`, `cost_usd`, `seconds` | `request_to_done` |

Every step also has `completed`, `turns`, `tokens`, `cost_usd`, `seconds` and, for grill,
`rounds`. `tokens` is input, cached input and output added together, for the plugin and the
simulated user; the report's header gives the split for the whole run, judge included. Cached
input is most of the total and much the cheapest: every `claude -p` call re-reads Claude Code's
own instructions from the cache. `cost_usd` is at API prices. A step that did not complete, or had nothing to work from because an earlier step
failed, scores 1 on each of its criteria and 0 on its shares.

## Adding a scenario

A folder under `evals/scenarios/`:

| File | What |
| --- | --- |
| `request.md` | the request as a person would type it, without the project name |
| `docs/*.md` | 1 to 4 short documents; optional |
| `card.json` | what only the simulated user knows |
| `expected.md` | what a good final output must contain, and must not |
| `seed/` | optional: files to put in the work repo before the brief, such as an existing project with something in `outputs/` |

`card.json`:

```json
{
  "kind": "memo",
  "project": "supplier-review",
  "facts": [
    {"id": "audience", "essential": true, "fact": "The logistics steering group, five people."}
  ],
  "covered_by_docs": [
    {"topic": "price per pallet per supplier", "doc": "freight-scorecard-2025.md"}
  ]
}
```

`essential` marks the facts a good task file cannot do without. `covered_by_docs` lists what the
documents already answer: the simulated user refers such questions to the documents, and the
judge counts them against the grill. Write `{{today+14d}}` for a date 14 days after the run, so
a deadline is never in the past. Invented content only: no real client names or data.

Save a new baseline after adding or changing a scenario.

## Config

`config.json` holds the models, runs per scenario, turn caps per step, the grill
implementations, the thresholds and the rubrics. The whole file is copied into every
`summary.json` and printed at the end of every report.

`temperature` is `null` because `claude -p` has no temperature setting; all three models run at
their default.

## Supabase

Every complete run (every scenario, `runs_per_scenario` runs each) writes to two tables:

| Table | One row per | Holds |
| --- | --- | --- |
| `eval_runs` | run, scenario and step | the metrics as mean, spread and count over the runs; scenario `ALL` is the overall |
| `eval_steps` | run, scenario, run number and step | what went into the step, what came out, the conversation, the metrics, the file checks and the judge's reasons |

For `eval_steps`, the input and output of each step are: brief, the request and the brief;
grill, the brief and the task file; work, the task file and every changed file in `outputs/`;
record, the task file before and after; end to end, the request and the final task file.

A trial on some scenarios, or with fewer runs, is not stored, so the tables hold only runs
that can be compared with one another. `eval_runs` is made by
`supabase/migrations/20261013000000_eval_runs.sql` and
`supabase/migrations/20261014000000_eval_runs_insert.sql`; `eval_steps` by
`supabase/migrations/20261014010000_eval_steps.sql`.

A run is written with the publishable key and URL in `telemetry.json`, as telemetry is. That key
can insert into `eval_runs` and `eval_steps` and do nothing else: it cannot read, change or delete a row. No
secret key is needed to run the eval. A run already stored is refused as a whole, not
duplicated. Reading the rows, for a dashboard, takes the secret key.

When the write fails, the run is kept on disk and its last line says `NOT STORED`;
`push <run-id>` stores it later. Push only a run that belongs on the dashboard: a run whose
scenarios were wrong stays off it, because a stored run cannot be taken back with the
publishable key.

## Known limits

- **Judge variance.** The judge is a model. The same files can get a 4 one time and a 5 the
  next, and its count of the grill's questions is its own reading of the conversation. The
  thresholds are set so that one point on one run does not flag; a flagged drop still deserves
  a look at `scores.json` before it is believed.
- **Simulated user.** It answers briefly and only from the card. Real people ramble, change
  their mind and volunteer things. A grill that scores well here has shown that it asks for
  what it needs, not that people enjoy being asked.
- **Small sample.** Ten scenarios and three runs each. A difference inside the spread is not a
  finding.
- **Noise from one pair of runs.** The calibration rests on two runs, so its standard deviations
  are rough. A third run of unchanged code is the check: it should show no regressions.
- **No temperature control**, as above, so runs differ more than they would at temperature 0.
- **Claude Code only.** The flow is driven through `claude -p`. Codex and Copilot CLI are not
  covered.
- **Record in single-step mode** has no work conversation to read.
- **Dates.** The model knows the real date, so scenarios use dates relative to the day of the
  run; a run on another day sees other dates.
