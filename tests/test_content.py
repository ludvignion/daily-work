import io
import json
import os
import re
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "metrics"))
import content
import export_content
import telemetry

MIGRATION = (REPO / "supabase" / "migrations" / "20261012010000_content.sql").read_text()
LIVE_MIGRATION = (REPO / "supabase" / "migrations" / "20261022000000_live_and_test.sql").read_text()
GRANTED = {c.strip() for c in re.search(r"grant insert \(([^)]*)\)\s+on live\.content to anon;", LIVE_MIGRATION).group(1).split(",")}
SESSION = "9594fe37-af3a-4682-a455-d242193f5901"


class ContentCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.home = tmp / "config"
        self.repo = tmp / "repo"
        self.project = self.repo / "acme"
        self.task = self.project / "tasks" / "q3-numbers.md"
        self.brief = self.project / "briefs" / "q3-numbers.md"
        self.id_file = self.project / "tasks" / ".q3-numbers.content-id"
        for d in ("tasks", "briefs", "outputs"):
            (self.project / d).mkdir(parents=True)
        self.sent = []
        self.enterContext(mock.patch.object(telemetry, "HOME", self.home))
        self.enterContext(mock.patch.object(telemetry, "config", lambda: ("https://x.supabase.co", "anon-key")))
        self.enterContext(mock.patch.object(telemetry, "send", lambda table, payload: self.sent.append((table, payload))))
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop("DAILY_WORK_TELEMETRY", None)
        os.environ.pop("DAILY_WORK_CONTENT", None)

    def run_main(self, *argv, hook=None):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook or {}, ensure_ascii=False).encode()), encoding="cp1252")):
            content.main(["content.py", *argv])
        return out.getvalue()

    def hook(self, event, **fields):
        return self.run_main("hook", hook={"hook_event_name": event, "session_id": SESSION, "cwd": str(self.repo), **fields})

    def command(self, name, args, prompt_id="p1"):
        prompt = f"/{name} {args}"
        self.hook("UserPromptExpansion", command_name=name, command_args=args, prompt=prompt, prompt_id=prompt_id)
        self.hook("UserPromptSubmit", prompt=prompt, prompt_id=prompt_id)

    def say(self, text, prompt_id="p2"):
        self.hook("UserPromptSubmit", prompt=text, prompt_id=prompt_id)

    def reply(self, text):
        self.hook("Stop", last_assistant_message=text)

    def accept_notice(self):
        self.run_main("created", str(self.task))

    def brief_run(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.reply("Brief draft ... Write this brief, or what should change?")
        self.say("write it")
        self.run_main("created", str(self.task))
        self.brief.write_text("# Q3\n")
        self.reply("Created acme/briefs/q3-numbers.md")


class OptIn(ContentCase):
    def test_on_by_default(self):
        self.assertTrue(content.enabled())
        self.accept_notice()
        self.brief_run()
        self.assertEqual([p["kind"] for _, p in self.sent], ["run"])

    def test_set_to_0_nothing_is_kept_or_sent(self):
        os.environ["DAILY_WORK_CONTENT"] = "0"
        self.assertEqual(self.run_main("created", str(self.task)), "")
        self.brief_run()
        self.assertEqual(self.run_main("outcome", str(self.task)), "")
        self.assertEqual(self.sent, [])
        self.assertFalse(self.home.exists())
        self.assertFalse(self.id_file.exists())

    def test_only_the_value_0_turns_it_off(self):
        for value in ("1", "false", "no", ""):
            os.environ["DAILY_WORK_CONTENT"] = value
            self.assertTrue(content.enabled())

    def test_the_shell_and_the_hooks_use_the_same_switch(self):
        self.assertIn('[ "${DAILY_WORK_CONTENT:-}" = 0 ] && return 0', (REPO / "scripts" / "lib.sh").read_text())
        hooks = (REPO / "claude-code" / "hooks.json").read_text()
        self.assertEqual(hooks.count('[ \\"${DAILY_WORK_CONTENT:-}\\" = 0 ] || bash \\"${CLAUDE_PLUGIN_ROOT}/scripts/run-py.sh\\" content.py'), 3)
        self.assertNotIn("= 1 ]", hooks)

    def test_empty_telemetry_json_sends_nothing(self):
        with mock.patch.object(telemetry, "config", lambda: None):
            self.assertEqual(self.run_main("created", str(self.task)), "")
            self.brief_run()
        self.assertEqual(self.sent, [])

    def test_independent_of_the_telemetry_opt_out(self):
        os.environ["DAILY_WORK_TELEMETRY"] = "0"
        self.accept_notice()
        self.brief_run()
        self.assertEqual([p["kind"] for _, p in self.sent], ["run"])
        self.assertFalse((self.home / "install-id").exists())

    def test_content_being_on_does_not_turn_telemetry_on_or_off(self):
        os.environ["DAILY_WORK_TELEMETRY"] = "0"
        self.assertTrue(telemetry.opted_out())
        del os.environ["DAILY_WORK_TELEMETRY"]
        self.assertFalse(telemetry.opted_out())
        self.assertFalse(telemetry.ready())  # its own first-run notice has not been shown


class FirstRunNotice(ContentCase):
    def test_first_run_shows_the_notice_and_sends_nothing(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.reply("draft")
        shown = self.run_main("created", str(self.task))
        self.reply("Created")
        for phrase in ("DAILY_WORK_CONTENT", "30 days", "Supabase", "DAILY_WORK_CONTENT=0", "what you typed"):
            self.assertIn(phrase, shown)
        self.assertEqual(self.sent, [])
        self.assertFalse((self.home / "content-runs").exists())

    def test_notice_from_record_also_sends_nothing(self):
        self.assertIn("shown once", self.run_main("outcome", str(self.task)))
        self.assertEqual(self.sent, [])

    def test_next_run_sends_and_shows_no_notice(self):
        self.accept_notice()
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.assertEqual(self.run_main("created", str(self.task)), "")
        self.reply("Created")
        self.assertEqual(len(self.sent), 1)


class Runs(ContentCase):
    def setUp(self):
        super().setUp()
        self.accept_notice()

    def test_brief_run_sends_every_turn_in_order(self):
        self.brief_run()
        (table, p), = self.sent
        self.assertEqual(table, "content")
        self.assertEqual(set(p), {"kind", "skill", "ts", "plugin_version", "content_id", "turns", "files"})
        self.assertEqual((p["kind"], p["skill"]), ("run", "brief"))
        self.assertEqual([(t["role"], t["text"]) for t in p["turns"]], [
            ("user", "/daily-work:brief acme pull the Q3 numbers"),
            ("assistant", "Brief draft ... Write this brief, or what should change?"),
            ("user", "write it"),
            ("assistant", "Created acme/briefs/q3-numbers.md"),
        ])
        self.assertFalse((self.home / "content-runs" / f"{SESSION}.json").exists())

    def test_nothing_is_sent_before_the_run_ends(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.reply("draft")
        self.say("change the title")
        self.reply("new draft")
        self.assertEqual(self.sent, [])

    def test_content_id_is_random_stored_beside_the_task_file_and_reused(self):
        self.brief_run()
        stored = self.id_file.read_text().split("\n")[0]
        self.assertEqual(uuid.UUID(stored).version, 4)
        self.assertEqual(self.sent[0][1]["content_id"], stored)
        self.run_main("outcome", str(self.task))
        self.assertEqual(self.sent[1][1]["content_id"], stored)

    def test_files_are_paths_inside_the_project_folder_without_contents(self):
        self.command("daily-work:record", "acme/tasks/q3-numbers.md")
        self.task.write_text("secret figures")
        (self.project / "outputs" / "q3.xlsx").write_text("secret figures")
        self.run_main("outcome", str(self.task))
        self.reply("Done")
        run = next(p for _, p in self.sent if p["kind"] == "run")
        self.assertEqual(run["files"], [".content-id", "outputs/q3.xlsx", "task.md"])
        self.assertNotIn("secret figures", json.dumps(run))

    def test_no_task_name_is_in_the_files_list(self):
        (self.project / "tasks" / "other-task.md").write_text("x")
        (self.project / "briefs" / "third-task.md").write_text("x")
        self.brief_run()
        self.assertEqual(self.sent[0][1]["files"], [".content-id", "brief.md"])

    def test_files_untouched_during_the_run_are_not_listed(self):
        old = self.project / "outputs" / "old.csv"
        old.write_text("x")
        os.utime(old, (1, 1))
        self.brief_run()
        self.assertNotIn("outputs/old.csv", self.sent[0][1]["files"])

    def test_grill_run_ends_when_the_task_file_exists(self):
        self.brief.write_text("# Q3\n")
        self.command("mattpocock-skills:grill-with-docs", "acme/briefs/q3-numbers.md")
        self.reply("Question 1?")
        self.say("yes")
        self.assertEqual(self.sent, [])
        self.task.write_text("# Q3\n")
        self.reply("task file written")
        (_, p), = self.sent
        self.assertEqual((p["skill"], len(p["turns"])), ("grill", 4))

    def test_a_grill_run_can_name_the_brief_by_its_task_name(self):
        self.brief.write_text("# Q3\n")
        self.command("mattpocock-skills:grill-with-docs", "q3-numbers")
        self.task.write_text("# Q3\n")
        self.reply("task file written")
        self.assertEqual([p["skill"] for _, p in self.sent], ["grill"])

    def test_a_task_name_with_briefs_in_two_projects_is_not_a_run(self):
        self.brief.write_text("# Q3\n")
        other = self.repo / "globex" / "briefs" / "q3-numbers.md"
        other.parent.mkdir(parents=True)
        other.write_text("# Q3\n")
        self.command("mattpocock-skills:grill-with-docs", "q3-numbers")
        self.assertFalse(list((self.home / "content-runs").glob("*.json")))

    def test_a_record_run_without_an_argument_gets_its_task_from_record_sh(self):
        self.command("daily-work:record", "")
        self.reply("Reading the task")
        self.say("go on")
        self.run_main("outcome", str(self.task))
        self.reply("committed")
        self.assertEqual([(p["kind"], p.get("skill")) for _, p in self.sent], [("outcome", None), ("run", "record")])
        self.assertEqual(len({p["content_id"] for _, p in self.sent}), 1)

    def test_a_command_typed_inside_a_sentence_starts_a_run_too(self):
        self.say("Looks great! /daily-work:record q3-numbers works. Can the colour change?")
        self.reply("Reading the task")
        self.say("go on", prompt_id="p3")
        self.run_main("outcome", str(self.task))
        self.reply("committed")
        run = next(p for _, p in self.sent if p["kind"] == "run")
        self.assertEqual((run["skill"], [t["role"] for t in run["turns"]]), ("record", ["user", "assistant", "user", "assistant"]))
        self.assertIn("Looks great!", run["turns"][0]["text"])

    def test_a_grill_command_inside_a_sentence_names_its_brief(self):
        self.brief.write_text("# Q3\n")
        self.say("ok now /mattpocock-skills:grill-with-docs q3-numbers please")
        self.task.write_text("# Q3\n")
        self.reply("task file written")
        self.assertEqual([p["skill"] for _, p in self.sent], ["grill"])

    def test_a_slash_command_is_kept_once_not_twice(self):
        self.command("daily-work:record", "q3-numbers")
        self.run_main("outcome", str(self.task))
        self.reply("committed")
        run = next(p for _, p in self.sent if p["kind"] == "run")
        self.assertEqual([t["text"] for t in run["turns"]], ["/daily-work:record q3-numbers", "committed"])

    def test_other_text_with_a_slash_starts_nothing(self):
        self.say("see docs/daily-work:record and /some-plugin:other x")
        self.assertFalse(list((self.home / "content-runs").glob("*.json")))

    def test_grilling_something_other_than_a_brief_is_not_a_run(self):
        self.command("mattpocock-skills:grill-with-docs", "the whole repo")
        self.reply("Question 1?")
        self.command("mattpocock-skills:grill-with-docs", "acme/tasks/q3-numbers.md")
        self.reply("Question 1?")
        self.command("mattpocock-skills:grill-with-docs", "q3-numbers")  # no brief of that name
        self.reply("Question 1?")
        self.assertFalse(list((self.home / "content-runs").glob("*.json")))

    def test_another_slash_command_drops_the_open_run(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.reply("draft")
        self.command("some-plugin:other", "x", prompt_id="p9")
        self.say("unrelated client question")
        self.reply("unrelated answer")
        self.run_main("created", str(self.task))
        self.reply("Created")
        self.assertEqual(self.sent, [])

    def test_task_notifications_are_not_user_turns(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.say("<task-notification>\n<task-id>x</task-id>")
        self.run_main("created", str(self.task))
        self.reply("Created")
        self.assertEqual([t["role"] for t in self.sent[0][1]["turns"]], ["user", "assistant"])

    def test_a_run_left_open_too_long_is_dropped(self):
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        with mock.patch.object(content.time, "time", lambda: 10 ** 10):
            self.run_main("created", str(self.task))
            self.reply("Created")
        self.assertEqual(self.sent, [])

    def test_timestamps_are_rounded_to_the_hour(self):
        self.brief_run()
        self.run_main("outcome", str(self.task))
        for _, p in self.sent:
            self.assertRegex(p["ts"], r"^\d{4}-\d\d-\d\dT\d\d:00:00Z$")


class Windows(ContentCase):
    """What broke in Claude desktop on Windows: the code page, path styles, hooks running at once."""
    def setUp(self):
        super().setUp()
        self.accept_notice()

    def test_hook_input_is_read_as_utf8_whatever_the_code_page(self):
        # run_main hands the hook its input through a cp1252 text layer, as Windows does.
        self.brief.write_text("# Q3\n")
        self.command("mattpocock-skills:grill-with-docs", "acme/briefs/q3-numbers.md")
        self.say("Göteborg — så klart")
        self.task.write_text("# Q3\n")
        self.reply("Klart — tack")
        (_, p), = self.sent
        self.assertEqual([t["text"] for t in p["turns"]][1:], ["Göteborg — så klart", "Klart — tack"])

    def test_a_task_path_in_another_style_is_inside_the_run_repo(self):
        import ntpath
        with mock.patch.object(content.os, "path", ntpath):
            self.assertTrue(content.inside("C:/Users/a/work/acme/tasks/q3.md", "C:\\Users\\a\\work"))
            self.assertTrue(content.inside("c:\\users\\a\\work\\acme\\tasks\\q3.md", "C:\\Users\\a\\work\\"))
            self.assertFalse(content.inside("C:/Users/a/work2/acme/tasks/q3.md", "C:\\Users\\a\\work"))

    def test_a_lock_left_by_a_killed_hook_does_not_block(self):
        lock = self.home / "content-runs.lock"
        lock.write_text("")
        os.utime(lock, (1, 1))
        self.command("daily-work:brief", "acme pull the Q3 numbers")
        self.assertTrue(list((self.home / "content-runs").glob("*.json")))
        self.assertFalse(lock.exists())


class Copilot(ContentCase):
    """Copilot CLI's hooks: camelCase fields, the event in the command line, no assistant replies."""
    def setUp(self):
        super().setUp()
        self.accept_notice()

    def copilot(self, event, **fields):
        return self.run_main("hook", event, hook={"sessionId": SESSION, "timestamp": 1, "cwd": str(self.repo), **fields})

    def test_a_grill_run_sends_what_the_person_typed(self):
        self.brief.write_text("# Q3\n")
        self.copilot("copilot-prompt", prompt="/mattpocock-skills:grill-with-docs acme/briefs/q3-numbers.md")
        self.copilot("copilot-stop", transcriptPath="/x/events.jsonl", stopReason="end_turn")
        self.copilot("copilot-prompt", prompt="1. fiscal Q3 2. net revenue")
        self.assertEqual(self.sent, [])
        self.task.write_text("# Q3\n")
        self.copilot("copilot-stop", transcriptPath="/x/events.jsonl", stopReason="end_turn")
        (table, p), = self.sent
        self.assertEqual((table, p["skill"]), ("content", "grill"))
        self.assertEqual([(t["role"], t["text"]) for t in p["turns"]], [
            ("user", "/mattpocock-skills:grill-with-docs acme/briefs/q3-numbers.md"),
            ("user", "1. fiscal Q3 2. net revenue")])
        self.assertTrue(content.grilled(str(self.task)))

    def test_a_brief_run_ends_when_brief_sh_names_its_task(self):
        self.copilot("copilot-prompt", prompt="/daily-work:brief acme pull the Q3 numbers")
        self.copilot("copilot-stop")
        self.copilot("copilot-prompt", prompt="write it")
        self.run_main("created", str(self.task))
        self.copilot("copilot-stop")
        (_, p), = self.sent
        self.assertEqual((p["skill"], len(p["turns"])), ("brief", 2))

    def test_the_transcript_is_never_read(self):
        transcript = self.repo / "events.jsonl"
        transcript.write_text('{"type": "assistant.message", "data": {"content": "SECRET REPLY"}}\n')
        self.brief.write_text("# Q3\n")
        self.copilot("copilot-prompt", prompt="/mattpocock-skills:grill-with-docs q3-numbers")
        self.task.write_text("# Q3\n")
        self.copilot("copilot-stop", transcriptPath=str(transcript))
        (_, p), = self.sent
        self.assertNotIn("SECRET REPLY", json.dumps(p))

    def test_system_notifications_are_not_user_turns(self):
        self.brief.write_text("# Q3\n")
        self.copilot("copilot-prompt", prompt="/mattpocock-skills:grill-with-docs q3-numbers")
        self.copilot("copilot-prompt", prompt='<system_notification>\nAgent "x" (explore) has finished\n</system_notification>')
        self.task.write_text("# Q3\n")
        self.copilot("copilot-stop")
        (_, p), = self.sent
        self.assertEqual(len(p["turns"]), 1)

    def test_other_prompts_start_nothing(self):
        self.copilot("copilot-prompt", prompt="work on q3-numbers")
        self.copilot("copilot-stop")
        self.assertEqual(self.sent, [])


class Truncation(ContentCase):
    def setUp(self):
        super().setUp()
        self.accept_notice()

    def test_text_up_to_50_kb_is_kept_whole(self):
        t = content.turn("user", "x" * 50_000)
        self.assertEqual((len(t["text"]), t["truncated"]), (50_000, False))

    def test_text_above_50_kb_is_cut_and_marked(self):
        t = content.turn("assistant", "x" * 50_001)
        self.assertEqual((len(t["text"]), t["truncated"]), (50_000, True))

    def test_the_limit_is_in_bytes_and_never_splits_a_character(self):
        t = content.turn("user", "å" * 30_000)  # 60 000 bytes
        self.assertTrue(t["truncated"])
        self.assertEqual(len(t["text"].encode()), 50_000)
        self.assertEqual(t["text"], "å" * 25_000)

    def test_a_long_prompt_and_a_long_reply_are_truncated_in_the_sent_run(self):
        self.command("daily-work:brief", "acme " + "p" * 60_000)
        self.run_main("created", str(self.task))
        self.reply("r" * 60_000)
        turns = self.sent[0][1]["turns"]
        self.assertEqual([t["truncated"] for t in turns], [True, True])
        self.assertTrue(all(len(t["text"].encode()) == 50_000 for t in turns))


class Outcome(ContentCase):
    def setUp(self):
        super().setUp()
        self.accept_notice()

    def record(self):
        self.command("daily-work:record", "acme/tasks/q3-numbers.md")
        self.run_main("id", str(self.task))
        self.run_main("outcome", str(self.task))
        self.reply("committed")

    def test_record_sends_one_outcome_row_and_the_record_run(self):
        self.record()
        (t1, outcome), (t2, run) = self.sent
        self.assertEqual((t1, t2), ("content", "content"))
        self.assertEqual(outcome, {"kind": "outcome", "ts": outcome["ts"], "plugin_version": telemetry.version(),
                                   "content_id": run["content_id"], "outcome": "completed",
                                   "grill_completed": False})
        self.assertEqual((run["kind"], run["skill"], len(run["turns"])), ("run", "record", 2))

    def test_grill_completed_is_true_after_a_logged_grill_run(self):
        self.brief.write_text("# Q3\n")
        self.command("mattpocock-skills:grill-with-docs", "acme/briefs/q3-numbers.md")
        self.task.write_text("# Q3\n")
        self.reply("task file written")
        self.record()
        outcome = next(p for _, p in self.sent if p["kind"] == "outcome")
        self.assertTrue(outcome["grill_completed"])
        self.assertEqual({p["content_id"] for _, p in self.sent}, {outcome["content_id"]})


class Separation(ContentCase):
    def test_install_id_and_telemetry_task_id_are_never_in_content_payloads(self):
        task_id = str(uuid.uuid4())
        install = telemetry.install_id()
        self.accept_notice()
        self.brief_run()
        self.brief.unlink()
        self.task.write_text(f"# Q3\n\nId: {task_id}\n")
        self.assertEqual(telemetry.task_id(self.task), task_id)
        self.command("daily-work:record", "acme/tasks/q3-numbers.md")
        self.run_main("outcome", str(self.task))
        self.reply("committed")
        self.assertEqual(len(self.sent), 3)
        for table, payload in self.sent:
            self.assertEqual(table, "content")
            self.assertNotIn("install_id", payload)
            self.assertNotIn("task_id", payload)
            text = json.dumps(payload)
            self.assertNotIn(install, text)
            self.assertNotIn(task_id, text)
            self.assertNotEqual(payload["content_id"], task_id)

    def test_the_content_code_never_touches_either_id(self):
        source = (REPO / "scripts" / "content.py").read_text()
        code = source.split('"""', 2)[2]
        for word in ("install_id", "install-id", "task_id(", "common(", "transcript_path"):
            self.assertNotIn(word, code)
        self.assertNotIn("Id:", code)

    def test_payloads_use_only_columns_the_migration_grants(self):
        self.accept_notice()
        self.brief_run()
        self.run_main("outcome", str(self.task))
        for _, payload in self.sent:
            self.assertLessEqual(set(payload), GRANTED)
        self.assertNotIn("install_id", GRANTED)
        self.assertNotIn("task_id", GRANTED)

    def test_migration_is_insert_only_and_deletes_after_30_days(self):
        self.assertIn("revoke all on public.content from anon, authenticated;", MIGRATION)
        self.assertIn("alter table public.content enable row level security;", MIGRATION)
        self.assertEqual(re.findall(r"for (\w+) to anon", MIGRATION), ["insert"])
        self.assertEqual(re.findall(r"grant (\w+)", MIGRATION), ["insert"])
        self.assertIn("delete from public.content where received_at < now() - interval '30 days'", MIGRATION)


class Export(unittest.TestCase):
    ROWS = [
        {"id": 1, "kind": "run", "content_id": "a", "skill": "brief", "ts": "t1", "plugin_version": "0.7.0", "turns": [1], "files": []},
        {"id": 2, "kind": "run", "content_id": "b", "skill": "brief", "ts": "t2", "plugin_version": "0.7.0", "turns": [2], "files": []},
        {"id": 3, "kind": "run", "content_id": "a", "skill": "grill", "ts": "t3", "plugin_version": "0.7.0", "turns": [3], "files": ["task.md"]},
        {"id": 5, "kind": "run", "content_id": "a", "skill": "record", "ts": "t5", "plugin_version": "0.7.0", "turns": [5], "files": []},
        {"id": 4, "kind": "outcome", "content_id": "a", "ts": "t4", "plugin_version": "0.7.0", "outcome": "completed",
         "rating": 4, "grill_completed": True, "skill": None, "turns": None, "files": None},
    ]

    def test_runs_are_grouped_by_content_id_in_order_with_the_outcome(self):
        a, b = export_content.group(self.ROWS)
        self.assertEqual(a["content_id"], "a")
        self.assertEqual([r["skill"] for r in a["runs"]], ["brief", "grill", "record"])
        self.assertEqual(a["runs"][1], {"skill": "grill", "ts": "t3", "plugin_version": "0.7.0", "turns": [3], "files": ["task.md"]})
        self.assertEqual(a["outcome"], {"outcome": "completed", "rating": 4, "grill_completed": True, "ts": "t4"})

    def test_a_task_without_a_record_has_no_outcome(self):
        _, b = export_content.group(self.ROWS)
        self.assertEqual((b["content_id"], b["outcome"], len(b["runs"])), ("b", None, 1))

    def test_row_order_in_the_input_does_not_matter(self):
        self.assertEqual(export_content.group(self.ROWS[::-1]), export_content.group(self.ROWS))

    def test_no_rows(self):
        self.assertEqual(export_content.group([]), [])


if __name__ == "__main__":
    unittest.main()
