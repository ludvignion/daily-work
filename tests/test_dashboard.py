"""The eval analysis's checks and the standalone dashboard build."""
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "evals"))
sys.path.insert(0, str(REPO / "dashboard"))
import analyse  # noqa: E402
import sessions  # noqa: E402
import build  # noqa: E402


class Analysis(unittest.TestCase):
    def test_keeps_six_kinds_of_three_bullets_and_only_known_runs(self):
        group = {"name": "dates", "runs": ["a/1", "zz/9"], "bullets": ["one", "two", "three"]}
        parsed = {"topics": [group] * 8, "confusion": [{"name": "x", "runs": [], "bullets": ["a", "b", "c"]}]}
        out = analyse.check(parsed, {"a/1"})
        self.assertEqual(len(out["topics"]), analyse.MAX_GROUPS)
        self.assertEqual(out["topics"][0], {"name": "dates", "runs": ["a/1"], "bullets": ["one", "two", "three"]})

    def test_refuses_other_than_three_bullets(self):
        for bullets in (["a", "b"], ["a", "b", "c", "d"], ["a", "b", "  "]):
            with self.assertRaises(ValueError):
                analyse.check({"topics": [{"name": "n", "bullets": bullets}], "confusion": [{"name": "x", "bullets": ["a", "b", "c"]}]}, set())

    def test_refuses_a_long_bullet_or_a_kind_without_a_name(self):
        ok = {"name": "x", "bullets": ["a", "b", "c"]}
        long = {"name": "n", "bullets": ["a", "b", " ".join(["word"] * (analyse.MAX_WORDS + 1))]}
        for bad in (long, {"name": "", "bullets": ["a", "b", "c"]}):
            with self.assertRaises(ValueError):
                analyse.check({"topics": [bad], "confusion": [ok]}, set())

    def test_refuses_a_reply_without_both_parts(self):
        with self.assertRaises(ValueError):
            analyse.check({"topics": [{"name": "x", "bullets": ["a", "b", "c"]}]}, set())

    def test_material_names_the_run_and_every_step(self):
        record = {"transcripts": {"grill": [{"role": "assistant", "text": "Who reads it?"}]}}
        scores = {"metrics": {"work": {"completed": 0}}, "reasons": {"work": {"meets_task": "nothing written"}}}
        text = analyse.material("01-x", 2, record, scores, "write a memo")
        self.assertIn("=== 01-x/2", text)
        self.assertIn("assistant: Who reads it?", text)
        self.assertIn("work (NOT COMPLETED):\n  meets_task None: nothing written", text)

    def test_retry_names_the_error_once(self):
        once = analyse.retry("PROMPT", ValueError("'x' has a bullet over 15 words"))
        twice = analyse.retry(once, ValueError("'y' has 2 bullets, not 3"))
        self.assertTrue(twice.startswith("PROMPT\n\nYour last reply was refused: 'y' has 2 bullets"))
        self.assertNotIn("'x'", twice)


ROW = {"id": 7, "ts": "2026-10-14T12:00:00+00:00", "plugin_version": "0.9.0", "content_id": "c" * 8,
       "skill": "grill", "turns": [{"role": "user", "text": "a memo"}, {"role": "assistant", "text": "Who reads it?"}],
       "files": ["task.md"]}


class Sessions(unittest.TestCase):
    rubric = {"questions_needed": "x", "settled_clearly": "y"}

    def test_prompt_holds_the_rubric_conversation_and_file_names(self):
        prompt = sessions.judge_prompt(ROW, self.rubric)
        for part in ("- questions_needed: x", "user: a memo", "assistant: Who reads it?", "Files written: task.md", "grill step"):
            self.assertIn(part, prompt)

    def test_score_row_keeps_scores_and_reasons(self):
        parsed = {"scores": {"questions_needed": {"score": 4, "reason": "fine"}, "settled_clearly": {"score": 2, "reason": "vague"}}}
        row = sessions.score_row(ROW, parsed, self.rubric, "opus")
        self.assertEqual((row["content_row"], row["skill"], row["run_ts"]), (7, "grill", ROW["ts"]))
        self.assertEqual(row["scores"], {"questions_needed": 4, "settled_clearly": 2})
        self.assertEqual(row["reasons"]["settled_clearly"], "vague")

    def test_score_row_refuses_a_missing_score(self):
        with self.assertRaises(ValueError):
            sessions.score_row(ROW, {"scores": {"questions_needed": 4}}, self.rubric, "opus")

    def test_material_names_the_run_by_skill_and_row(self):
        text = sessions.material(ROW, {"scores": {"questions_needed": 4}, "reasons": {"questions_needed": "fine"}})
        self.assertTrue(text.startswith("=== grill/7\n  questions_needed 4: fine"))

    def test_every_skill_has_a_rubric(self):
        cfg = json.loads((REPO / "evals" / "config.json").read_text())
        self.assertEqual(set(cfg["session_rubrics"]), {"brief", "grill", "record"})


def summary(run_id):
    rows = [{"scenario": s, "step": step, "metric": m, "n": 3, "mean": v, "min": v, "max": v, "sd": 0.0}
            for s in ("ALL", "a", "b") for step, m, v in
            [("end_to_end", "request_to_done", 4.0 if s != "b" else 3.0), ("end_to_end", "seconds", 120.0),
             ("work", "meets_expected", 5.0), ("grill", "tokens", 9.0)]]
    return {"meta": {"run_id": run_id, "date": "2026-10-14", "grill": "g", "plugin_version": "0.9.0",
                     "scenarios": ["a", "b"], "runs_per_scenario": 3, "steps": ["brief", "grill", "work", "record"],
                     "config": {"models": {"plugin": "p"}}},
            "rows": rows, "runs": [], "totals": {"tokens": 1000}}


class Build(unittest.TestCase):
    def test_overview_leaves_out_size_and_scenario_rows(self):
        rows = build.overview([summary("r1")])
        self.assertEqual({(r["step"], r["metric"]) for r in rows},
                         {("end_to_end", "request_to_done"), ("work", "meets_expected")})
        self.assertTrue(all(r["run_id"] == "r1" for r in rows))

    def test_scenarios_weakest_first(self):
        rows = build.scenarios(summary("r1"))
        self.assertEqual([r["scenario"] for r in rows], ["b", "a"])
        self.assertEqual((rows[0]["request_to_done"], rows[0]["meets_expected"], rows[0]["minutes"]), (3.0, 5.0, 2.0))

    def test_views_are_the_queries_unchanged(self):
        migration = (REPO / "supabase" / "migrations" / "20261014030000_dashboard_views.sql").read_text()
        for name in build.LIVE:
            sql = [l for l in (REPO / "dashboard" / "queries" / f"{name}.sql").read_text().splitlines() if not l.startswith("--")][0]
            self.assertIn(f"create or replace view public.dashboard_{name} with (security_invoker = true) as\n{sql}", migration)
            self.assertIn(f"revoke all on public.dashboard_{name} from anon, authenticated;", migration)

    def test_sim_has_the_same_tables_and_views(self):
        migration = (REPO / "supabase" / "migrations" / "20261014040000_sim_schema.sql").read_text()
        for table in ("events", "content", "feedback", "session_scores", "session_analysis"):
            self.assertIn(f"create table if not exists sim.{table}", migration)
            self.assertIn(f"alter table sim.{table}", migration)
        for name in build.LIVE:
            sql = [l for l in (REPO / "dashboard" / "queries" / f"{name}.sql").read_text().splitlines() if not l.startswith("--")][0]
            self.assertIn(f"create or replace view sim.dashboard_{name} with (security_invoker = true) as\n{sql.replace('public.', 'sim.')}", migration)
            self.assertIn(f"revoke all on sim.dashboard_{name} from anon, authenticated;", migration)
        # anon may insert into the three tables the plugin writes, nothing else
        grants = re.findall(r"grant insert \([^)]*\)\s+on sim\.(\w+) to anon", migration)
        self.assertEqual(sorted(grants), ["content", "events", "feedback"])

    def test_sessions_pick_the_schema(self):
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "k"}):
            self.assertEqual(sessions.Supabase("test").headers["Accept-Profile"], "sim")
            self.assertEqual(sessions.Supabase().headers["Content-Profile"], "public")

    def test_page_holds_the_live_rows(self):
        html = build.page({}, {"kpis": [{"installs": 2}]})
        blob = html.split('id="dash-live">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(blob), {"kpis": [{"installs": 2}]})

    def test_tokens_per_run(self):
        self.assertEqual(build.tokens([summary("r1")])[0]["minutes_per_run"], 2.0)

    def test_page_holds_the_data_and_cannot_end_its_script_early(self):
        html = build.page({"eval_steps": [{"output": "</script><b>x</b>"}]})
        blob = html.split('id="dash-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(blob)["eval_steps"][0]["output"], "</script><b>x</b>")
        self.assertIn('<div id="dash-root">', html)

    def test_no_key_in_the_dashboard(self):
        for p in (REPO / "dashboard").rglob("*"):
            if p.is_file() and "out" not in p.relative_to(REPO / "dashboard").parts and p.suffix in (".html", ".sql", ".py", ".md"):
                self.assertNotRegex(p.read_text(), r"sb_secret_|sk-ant-|eyJhbGci|service_role")


if __name__ == "__main__":
    unittest.main()
