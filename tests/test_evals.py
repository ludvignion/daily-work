import io
import json
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "evals"))
import flow
import report
import scoring

THRESHOLDS = {"score": 0.5, "share": 0.15, "count_relative": 0.25}

BRIEF = """# Supplier memo

Project: supplier-review
Written: 2026-10-13
Id: 11111111-2222-3333-4444-555555555555

A short memo on whether to keep Nordfrakt.

Output: a memo
"""

# What a grilling session should leave: every layout check holds.
TASK = """# Supplier memo

Project: supplier-review
Created: 2026-10-13
Id: 11111111-2222-3333-4444-555555555555

## Ask
A short memo on whether to keep Nordfrakt.

Output: a memo

## Spec
Purpose: the steering group decides whether to renew.
Done looks like:
- The memo is one page.
- The cost difference reconciles to the scorecard.
Decided:
- stated: one page at most
- assumed: volume stays at 18 400 pallets
Out of scope:
- Contract negotiation.

## Result
<written by /daily-work:record>

## Caveats
<written by /daily-work:record>
"""

RECORDED = TASK.replace("## Result\n<written by /daily-work:record>", "## Result\nMemo in outputs/memo.md: keep Nordfrakt.") \
               .replace("## Caveats\n<written by /daily-work:record>", "## Caveats\nNone.")
README = "# supplier-review\n\n## Tasks\n- 2026-10-13 supplier-memo: done, memo recommending Nordfrakt\n"
COMMITS = ["daily-work: record supplier-memo", "eval: start"]


class BriefLayout(unittest.TestCase):
    def test_a_brief_from_brief_sh_passes_every_check(self):
        self.assertEqual(scoring.share(scoring.brief_layout(BRIEF)), 1.0)

    def test_missing_id_and_description_are_two_of_five(self):
        broken = "# Supplier memo\n\nProject: supplier-review\nWritten: 2026-10-13\n"
        checks = scoring.brief_layout(broken)
        self.assertFalse(checks["id_line"])
        self.assertFalse(checks["has_description"])
        self.assertEqual(scoring.share(checks), 0.6)


class TaskLayout(unittest.TestCase):
    def test_the_layout_agents_md_asks_for_passes_every_check(self):
        checks = scoring.task_layout(TASK, BRIEF, brief_deleted=True)
        self.assertEqual([k for k, v in checks.items() if not v], [])

    def test_brief_left_behind(self):
        self.assertFalse(scoring.task_layout(TASK, BRIEF, brief_deleted=False)["brief_deleted"])

    def test_ask_rewritten_by_the_grill(self):
        changed = TASK.replace("A short memo on whether to keep Nordfrakt.", "A memo on freight suppliers.")
        self.assertFalse(scoring.task_layout(changed, BRIEF, True)["ask_is_brief"])

    def test_id_not_copied_from_the_brief(self):
        changed = TASK.replace("11111111", "99999999")
        self.assertFalse(scoring.task_layout(changed, BRIEF, True)["id_copied"])

    def test_done_lines_left_as_the_template_placeholder(self):
        changed = TASK.replace("- The memo is one page.\n- The cost difference reconciles to the scorecard.",
                               "- <a check a person can confirm in under a minute>")
        self.assertFalse(scoring.task_layout(changed, BRIEF, True)["spec_done_lines"])

    def test_result_filled_in_by_the_grill(self):
        self.assertFalse(scoring.task_layout(RECORDED, BRIEF, True)["result_left"])

    def test_extra_section_breaks_the_order(self):
        changed = TASK.replace("## Result", "## Notes\nx\n\n## Result")
        self.assertFalse(scoring.task_layout(changed, BRIEF, True)["sections_in_order"])

    def test_a_file_with_no_sections_fails_and_does_not_raise(self):
        checks = scoring.task_layout("just some text", BRIEF, True)
        self.assertEqual(sorted(k for k, v in checks.items() if v), ["brief_deleted"])


class RecordChecks(unittest.TestCase):
    def test_a_good_record_passes_every_check(self):
        checks = scoring.record_checks(TASK, RECORDED, README, "supplier-memo", COMMITS)
        self.assertEqual(scoring.share(checks), 1.0)

    def test_spec_edited_during_record(self):
        edited = RECORDED.replace("- stated: one page at most", "- stated: two pages at most")
        self.assertFalse(scoring.record_checks(TASK, edited, README, "supplier-memo", COMMITS)["ask_spec_unchanged"])

    def test_placeholder_left_readme_open_and_no_commit(self):
        checks = scoring.record_checks(TASK, TASK, README.replace("done, memo recommending Nordfrakt", "open"),
                                       "supplier-memo", ["eval: start"])
        self.assertEqual(checks, {"ask_spec_unchanged": True, "result_written": False, "caveats_written": False,
                                  "readme_done": False, "committed": False})

    def test_another_tasks_done_line_does_not_count(self):
        self.assertFalse(scoring.record_checks(TASK, RECORDED, README, "memo", COMMITS)["readme_done"])


class Judge(unittest.TestCase):
    def test_json_wrapped_in_prose_and_a_code_fence(self):
        reply = 'Here is my grading:\n```json\n{"scores": {"goal_captured": {"score": 4, "reason": "clear"}}}\n```\nDone.'
        self.assertEqual(scoring.judge_scores(scoring.parse_judge(reply), ["goal_captured"]), {"goal_captured": 4})

    def test_a_bare_number_is_accepted_as_the_score(self):
        self.assertEqual(scoring.judge_scores({"scores": {"a": 5}}, ["a"]), {"a": 5})

    def test_missing_criterion_out_of_range_and_non_integer_are_refused(self):
        for scores in ({}, {"a": {"score": 6}}, {"a": {"score": 0}}, {"a": {"score": 4.5}}, {"a": {"score": "4"}}, {"a": {"score": True}}):
            with self.assertRaises(ValueError):
                scoring.judge_scores({"scores": scores}, ["a"])

    def test_no_json_at_all(self):
        with self.assertRaises(ValueError):
            scoring.parse_judge("I cannot grade this.")


FACTS = [{"id": "goal", "essential": True}, {"id": "audience", "essential": True},
         {"id": "deadline", "essential": True}, {"id": "length", "essential": True},
         {"id": "format", "essential": False}]


class Facts(unittest.TestCase):
    def test_three_of_four_essential_facts_one_of_them_assumed(self):
        judged = {"goal": "stated", "audience": "stated", "deadline": "assumed", "length": "absent", "format": "absent"}
        self.assertEqual(scoring.fact_metrics(FACTS, judged),
                         {"essential_share": 0.75, "facts_share": 0.6, "stated_share": 2 / 3})

    def test_a_fact_the_judge_left_out_counts_as_absent(self):
        self.assertEqual(scoring.fact_metrics(FACTS, {"goal": "stated"})["essential_share"], 0.25)

    def test_nothing_found(self):
        self.assertEqual(scoring.fact_metrics(FACTS, {}), {"essential_share": 0.0, "facts_share": 0.0, "stated_share": 0.0})

    def test_questions_the_docs_answer_are_counted(self):
        questions = [{"question": "who reads it", "docs_answer": False}, {"question": "price per pallet", "docs_answer": True},
                     {"question": "contract end", "docs_answer": True}]
        self.assertEqual(scoring.question_metrics(questions, rounds=2),
                         {"questions": 3, "questions_docs_answer": 2, "rounds": 2})


def run(scenario, n, **steps):
    return {"scenario": scenario, "run": n, "metrics": steps}


# Two scenarios, three runs each. Scenario a: goal_captured 5, 4, 3. Scenario b: 2, 2, 2.
RUNS = [run("a", 1, brief={"goal_captured": 5}, grill={"essential_share": 1.0, "questions": 8}),
        run("a", 2, brief={"goal_captured": 4}, grill={"essential_share": 0.8, "questions": 10}),
        run("a", 3, brief={"goal_captured": 3}, grill={"essential_share": 0.6, "questions": 12}),
        run("b", 1, brief={"goal_captured": 2}, grill={"essential_share": 0.4, "questions": 4}),
        run("b", 2, brief={"goal_captured": 2}, grill={"essential_share": 0.4, "questions": 4}),
        run("b", 3, brief={"goal_captured": 2}, grill={"essential_share": 0.4, "questions": 4})]


def pick(rows, scenario, step, metric):
    return next(r for r in rows if (r["scenario"], r["step"], r["metric"]) == (scenario, step, metric))


class Aggregate(unittest.TestCase):
    def setUp(self):
        self.rows = scoring.aggregate(RUNS)

    def test_mean_and_spread_over_the_three_runs(self):
        r = pick(self.rows, "a", "brief", "goal_captured")
        self.assertEqual((r["n"], r["mean"], r["min"], r["max"], r["sd"]), (3, 4.0, 3.0, 5.0, 1.0))

    def test_identical_runs_have_no_spread(self):
        r = pick(self.rows, "b", "brief", "goal_captured")
        self.assertEqual((r["mean"], r["min"], r["max"], r["sd"]), (2.0, 2.0, 2.0, 0.0))

    def test_overall_is_the_mean_of_the_scenario_means(self):
        r = pick(self.rows, "ALL", "brief", "goal_captured")
        self.assertEqual((r["n"], r["mean"], r["min"], r["max"]), (2, 3.0, 2.0, 4.0))
        self.assertEqual(pick(self.rows, "ALL", "grill", "questions")["mean"], 7.0)

    def test_a_missing_value_is_left_out_and_not_counted_as_zero(self):
        rows = scoring.aggregate([run("a", 1, brief={"goal_captured": 4}), run("a", 2, brief={"goal_captured": None})])
        self.assertEqual((rows[0]["n"], rows[0]["mean"]), (1, 4.0))

    def test_steps_come_in_flow_order(self):
        rows = scoring.aggregate([run("a", 1, end_to_end={"x": 1}, record={"x": 1}, brief={"x": 1}, work={"x": 1}, grill={"x": 1})])
        self.assertEqual([r["step"] for r in rows if r["scenario"] == "a"], scoring.STEPS)


def rows(**metrics):
    """Rows for scenario 'a' and 'ALL' from step__metric=mean."""
    out = []
    for key, mean in metrics.items():
        step, metric = key.split("__")
        for scenario in ("a", "ALL"):
            out.append({"scenario": scenario, "step": step, "metric": metric, "n": 3, "mean": mean, "min": mean, "max": mean, "sd": 0.0})
    return out


class Baseline(unittest.TestCase):
    def one(self, base, now, key):
        step, metric = key.split("__")
        comparison = scoring.compare(rows(**{key: now}), rows(**{key: base}), THRESHOLDS)
        return next(c for c in comparison if c["scenario"] == "ALL")

    def test_score_drop_past_half_a_point_is_a_regression(self):
        c = self.one(4.0, 3.33, "brief__goal_captured")
        self.assertEqual((c["delta"], c["regression"]), (-0.67, True))

    def test_score_drop_of_exactly_half_a_point_is_not(self):
        self.assertFalse(self.one(4.0, 3.5, "brief__goal_captured")["regression"])

    def test_a_rise_is_never_a_regression(self):
        c = self.one(3.0, 5.0, "brief__goal_captured")
        self.assertEqual((c["delta"], c["regression"]), (2.0, False))

    def test_share_drop_past_fifteen_points(self):
        self.assertTrue(self.one(0.8, 0.6, "grill__essential_share")["regression"])
        self.assertFalse(self.one(0.8, 0.7, "grill__essential_share")["regression"])

    def test_more_questions_the_docs_answer_is_worse(self):
        c = self.one(2.0, 3.0, "grill__questions_docs_answer")
        self.assertEqual((c["delta"], c["regression"]), (-1.0, True))

    def test_fewer_questions_is_better(self):
        c = self.one(10.0, 6.0, "grill__questions")
        self.assertEqual((c["delta"], c["regression"]), (4.0, False))

    def test_count_within_a_quarter_is_not_a_regression(self):
        self.assertFalse(self.one(10.0, 12.0, "grill__questions")["regression"])
        self.assertTrue(self.one(10.0, 13.0, "grill__questions")["regression"])

    def test_count_rising_from_zero(self):
        self.assertTrue(self.one(0.0, 1.0, "grill__questions_docs_answer")["regression"])
        self.assertFalse(self.one(0.0, 0.33, "grill__questions_docs_answer")["regression"])

    def test_a_metric_the_baseline_lacks_is_not_compared(self):
        self.assertEqual(scoring.compare(rows(brief__goal_captured=1.0), rows(brief__scope_right=5.0), THRESHOLDS), [])

    def test_first_drop_is_the_earliest_step_in_the_flow(self):
        base = rows(brief__goal_captured=5.0, grill__essential_share=1.0, work__meets_task=5.0, end_to_end__request_to_done=5.0)
        now = rows(brief__goal_captured=5.0, grill__essential_share=0.5, work__meets_task=3.0, end_to_end__request_to_done=2.0)
        comparison = scoring.compare(now, base, THRESHOLDS)
        self.assertEqual(scoring.first_drop(comparison), "grill")
        self.assertEqual(len(scoring.regressions(comparison)), 3)

    def test_a_scenario_row_past_its_limit_is_a_look_not_a_regression(self):
        comparison = scoring.compare(rows(grill__task_quality=3.0), rows(grill__task_quality=4.0), THRESHOLDS)
        a = next(c for c in comparison if c["scenario"] == "a")
        self.assertEqual((a["beyond"], a["regression"]), (True, False))
        self.assertEqual(scoring.looks(comparison), [a])
        self.assertEqual([c["scenario"] for c in scoring.regressions(comparison)], ["ALL"])

    def test_no_drop(self):
        same = rows(brief__goal_captured=4.0)
        self.assertIsNone(scoring.first_drop(scoring.compare(same, same, THRESHOLDS)))

    def test_cost_and_time_are_reported_but_never_the_first_drop(self):
        comparison = scoring.compare(rows(work__cost_usd=9.0, work__seconds=900.0), rows(work__cost_usd=1.0, work__seconds=100.0), THRESHOLDS)
        self.assertTrue(all(c["beyond"] for c in comparison))
        self.assertEqual(scoring.regressions(comparison), [])
        self.assertEqual(scoring.looks(comparison), [])
        self.assertIsNone(scoring.first_drop(comparison))



def scenario_rows(step, metric, means, overall):
    out = [{"scenario": s, "step": step, "metric": metric, "n": 3, "mean": m, "min": m, "max": m, "sd": 0.0} for s, m in means.items()]
    return out + [{"scenario": "ALL", "step": step, "metric": metric, "n": len(means), "mean": overall, "min": 0, "max": 0, "sd": 0.0}]


class Noise(unittest.TestCase):
    def test_is_the_spread_of_the_scenario_differences(self):
        a = scenario_rows("work", "meets_task", {"x": 4.0, "y": 4.0, "z": 5.0}, 4.33)
        b = scenario_rows("work", "meets_task", {"x": 5.0, "y": 3.0, "z": 5.0}, 4.33)
        self.assertEqual(scoring.noise(a, b), {"work/meets_task": {"sd": 1.0, "scenarios": 3}})

    def test_a_left_out_scenario_does_not_count(self):
        a = scenario_rows("work", "meets_task", {"x": 4.0, "y": 4.0, "z": 1.0}, 3.0)
        b = scenario_rows("work", "meets_task", {"x": 4.0, "y": 4.0, "z": 5.0}, 4.33)
        self.assertEqual(scoring.noise(a, b, ["z"])["work/meets_task"]["sd"], 0.0)

    def test_widens_the_limit_beyond_the_config_threshold(self):
        noise = {"work/meets_task": {"sd": 1.0, "scenarios": 9}}
        base = rows(work__meets_task=4.0)
        now = rows(work__meets_task=2.5)
        by = {c["scenario"]: c for c in scoring.compare(now, base, THRESHOLDS, noise)}
        # Three standard deviations for one scenario; divided by the square root of 9 overall.
        self.assertEqual((by["a"]["limit"], by["a"]["beyond"]), (3.0, False))
        self.assertEqual((by["ALL"]["limit"], by["ALL"]["regression"]), (1.0, True))

    def test_never_narrows_it_below_the_config_threshold(self):
        noise = {"work/meets_task": {"sd": 0.0, "scenarios": 9}}
        c = scoring.compare(rows(work__meets_task=3.6), rows(work__meets_task=4.0), THRESHOLDS, noise)
        self.assertTrue(all(x["limit"] == 0.5 and not x["beyond"] for x in c))

CONFIG = {"thresholds": THRESHOLDS, "models": {"plugin": "p", "user": "u", "judge": "j"}}


def summary(run_id, grill, **metrics):
    return {"meta": {"run_id": run_id, "date": "2026-10-13", "grill": grill, "grill_sha256": "ab" * 32,
                     "plugin_version": "0.9.0", "commit": "abc1234", "scenarios": ["a"], "runs_per_scenario": 3,
                     "steps": ["brief", "grill", "work", "record"], "config": CONFIG},
            "rows": rows(**metrics), "runs": [],
            "totals": {"cost_usd": 3.5, "judge_cost_usd": 1.0, "tokens": 1000, "tokens_input": 50, "tokens_cached": 900, "tokens_output": 50, "judge_tokens": 200, "seconds": 600.0, "wall_seconds": 300.0}}


class Report(unittest.TestCase):
    def test_regression_is_flagged_and_the_first_step_named(self):
        text = report.write(summary("new", "g", brief__goal_captured=5.0, grill__essential_share=0.5),
                            summary("old", "g", brief__goal_captured=5.0, grill__essential_share=1.0))
        self.assertIn("**1 regression overall. First step with a drop: grill.**", text)
        self.assertIn("- grill, essential_share: 1 to 0.5; past its limit in a", text)
        self.assertIn("| grill | essential_share | 0.5 | 1 | worse 0.5 | REGRESSION |", text)
        self.assertIn("| grill | essential_share | 0.5 | 1 | worse 0.5 | look |", text)
        self.assertIn("| brief | goal_captured | 5 | 5 | same 0 |  |", text)
        self.assertIn("Baseline: run old", text)

    def test_no_baseline_says_so(self):
        text = report.write(summary("new", "g", brief__goal_captured=5.0), None)
        self.assertIn("No baseline saved", text)
        self.assertNotIn("REGRESSION", text)

    def test_tokens_lead_and_dollars_are_labelled_as_api_prices(self):
        text = report.write(summary("new", "g", brief__goal_captured=5.0), None)
        self.assertIn("- Tokens: 1000 = input 50 + cached input 900 + output 50 (of which judge 200)", text)
        self.assertIn("- Cost at API prices: 3.50 USD (of which judge 1.00). On a subscription login this is usage, not a charge.", text)

    def test_config_is_in_the_report(self):
        self.assertIn('"count_relative": 0.25', report.write(summary("new", "g", brief__goal_captured=5.0), None))

    def test_side_by_side_names_the_better_grill_by_the_metrics_direction(self):
        text = report.side_by_side(summary("r", "ours", grill__essential_share=0.9, grill__questions=6.0, brief__goal_captured=1.0),
                                   summary("r", "theirs", grill__essential_share=0.7, grill__questions=4.0, brief__goal_captured=5.0))
        self.assertIn("| grill | essential_share | 0.9 | 0.7 | ours |", text)
        self.assertIn("| grill | questions | 6 | 4 | theirs |", text)
        self.assertNotIn("goal_captured", text)  # brief does not depend on the grill

    def test_supabase_rows_are_one_per_scenario_and_step(self):
        out = report.supabase_rows(summary("r", "g", grill__essential_share=0.9, grill__questions=6.0, brief__goal_captured=4.0))
        self.assertEqual(len(out), 4)  # a and ALL, brief and grill
        row = next(r for r in out if (r["scenario"], r["step"]) == ("a", "grill"))
        self.assertEqual(sorted(row["metrics"]), ["essential_share", "questions"])
        self.assertEqual(row["metrics"]["questions"]["mean"], 6.0)
        self.assertEqual((row["run_id"], row["grill"], row["model"], row["plugin_version"]), ("r", "g", "p", "0.9.0"))
        json.dumps(out)


class Files(unittest.TestCase):
    def file(self, name, data):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = Path(folder) / name
        path.write_bytes(data)
        return path

    def office(self, name, parts):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            for part, xml in parts.items():
                z.writestr(part, xml)
        return self.file(name, buffer.getvalue())

    def test_a_word_file_gives_its_text_one_line_per_paragraph(self):
        path = self.office("memo.docx", {"word/document.xml": "<w:document><w:p><w:r><w:t>Day 1: laptop &amp; accounts</w:t></w:r></w:p>"
                                                               "<w:p><w:r><w:t>Day 2: shadowing</w:t></w:r></w:p></w:document>",
                                         "docProps/core.xml": "<x>not shown</x>"})
        self.assertEqual(flow.read_text(path).strip().splitlines(), ["Day 1: laptop & accounts", "Day 2: shadowing"])

    def test_a_powerpoint_file_gives_the_text_of_its_slides(self):
        path = self.office("deck.pptx", {"ppt/slides/slide1.xml": "<p:sld><a:p><a:r><a:t>Targets</a:t></a:r></a:p></p:sld>",
                                         "ppt/slides/slide2.xml": "<p:sld><a:p><a:r><a:t>Priorities</a:t></a:r></a:p></p:sld>"})
        self.assertEqual(flow.read_text(path).split(), ["Targets", "Priorities"])

    def test_any_other_binary_file_is_named_and_not_shown(self):
        self.assertEqual(flow.read_text(self.file("chart.png", b"\x89PNG\0\0\0binary")), "(binary file, 13 bytes, contents not shown)")
        self.assertEqual(flow.read_text(self.office("book.xlsx", {"xl/workbook.xml": "<x/>"}))[:13], "(binary file,")

    def test_no_null_byte_ever_reaches_the_judge(self):
        for path in (self.file("a.bin", b"ab\0cd"), self.office("m.docx", {"word/document.xml": "<w:p>x</w:p>"})):
            self.assertNotIn("\0", flow.read_text(path))

    def test_text_and_a_missing_file(self):
        self.assertEqual(flow.read_text(self.file("a.md", "räksmörgås\n".encode())), "räksmörgås\n")
        self.assertEqual(flow.read_text(Path("/nonexistent/x.md")), "")


class Scenarios(unittest.TestCase):
    def test_dates_are_relative_to_the_day_of_the_run(self):
        self.assertEqual(flow.render("due {{today+14d}}, ends {{today+0d}}", date(2026, 12, 25)), "due 2027-01-08, ends 2026-12-25")

    def test_every_scenario_loads_and_is_complete(self):
        folders = sorted(p for p in (REPO / "evals" / "scenarios").iterdir() if p.is_dir())
        self.assertTrue(folders)
        for folder in folders:
            with self.subTest(folder.name):
                s = flow.load_scenario(folder)
                self.assertTrue(s["request"])
                self.assertTrue(s["expected"].strip())
                self.assertRegex(s["card"]["project"], r"^[a-z0-9-]+$")
                self.assertTrue(any(f["essential"] for f in s["card"]["facts"]))
                self.assertEqual(len({f["id"] for f in s["card"]["facts"]}), len(s["card"]["facts"]))
                for covered in s["card"].get("covered_by_docs", []):
                    self.assertIn(covered["doc"], s["docs"])
                rendered = json.dumps(s["card"]) + s["request"] + s["expected"] + "".join(s["docs"].values())
                self.assertNotIn("{{", rendered)
                self.assertNotIn("today", rendered.lower().replace("today's", ""), "a date placeholder was not filled in")

    def test_the_publishable_key_may_insert_every_column_a_row_carries(self):
        sql = (REPO / "supabase" / "migrations" / "20261014000000_eval_runs_insert.sql").read_text()
        granted = re.search(r"grant insert \(([^)]*)\)\s+on public\.eval_runs to anon;", sql).group(1)
        row = report.supabase_rows(summary("r", "g", brief__goal_captured=5.0))[0]
        self.assertEqual({c.strip() for c in granted.split(",")}, set(row))

    def test_step_rows_carry_input_output_and_reasons(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        run_dir = folder / "a" / "run-1"
        run_dir.mkdir(parents=True)
        files = {"brief": "B", "task_after_grill": "T1", "task_after_work": "T1", "task_final": "T2",
                 "outputs": {"p/outputs/x.md": "X"}}
        (run_dir / "run.json").write_text(json.dumps({"files": files, "transcripts": {"grill": [{"role": "user", "text": "q"}]}}))
        metrics = {step: {"completed": 1} for step in scoring.STEPS}
        (run_dir / "scores.json").write_text(json.dumps({"metrics": metrics, "checks": {"grill": {"heading": True}},
                                                         "reasons": {"work": {"meets_task": "ok"}}}))
        s = summary("r", "g", brief__goal_captured=5.0)
        s["runs"] = [{"scenario": "a", "run": 1}]
        rows = {r["step"]: r for r in report.step_rows(s, folder, lambda name: "REQ")}
        self.assertEqual(list(rows), scoring.STEPS)
        self.assertEqual((rows["brief"]["input"], rows["brief"]["output"]), ("REQ", "B"))
        self.assertEqual((rows["grill"]["input"], rows["grill"]["output"]), ("B", "T1"))
        self.assertEqual(rows["work"]["output"], "=== p/outputs/x.md\nX")
        self.assertEqual((rows["end_to_end"]["input"], rows["end_to_end"]["output"]), ("REQ", "T2"))
        self.assertEqual(rows["grill"]["transcript"], [{"role": "user", "text": "q"}])
        self.assertEqual(rows["grill"]["checks"], {"heading": True})
        self.assertEqual(rows["work"]["reasons"], {"meets_task": "ok"})

    def test_the_publishable_key_may_insert_every_column_a_step_row_carries(self):
        sql = (REPO / "supabase" / "migrations" / "20261014010000_eval_steps.sql").read_text()
        granted = re.search(r"grant insert \(([^)]*)\)\s+on public\.eval_steps to anon;", sql).group(1)
        columns = {"run_id", "run_date", "plugin_version", "grill", "model", "scenario", "run", "step", "completed",
                   "input", "output", "transcript", "metrics", "checks", "reasons"}
        self.assertEqual({c.strip() for c in granted.split(",")}, columns)

    def test_no_key_is_committed_under_evals(self):
        for p in (REPO / "evals").rglob("*"):
            if p.is_file() and "runs" not in p.relative_to(REPO / "evals").parts and p.suffix in (".py", ".json", ".md"):
                self.assertNotRegex(p.read_text(), r"sb_secret_|sk-ant-|service_role")


if __name__ == "__main__":
    unittest.main()
