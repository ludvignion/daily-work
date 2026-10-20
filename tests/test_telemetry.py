import contextlib
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
import telemetry

MIGRATION = (REPO / "supabase" / "migrations" / "20261012000000_telemetry.sql").read_text()
TASK_ID = "0b9f6a3e-58c1-4a41-9d0c-0d2f3f6f7a11"


def granted(table):
    """The columns the migration lets the anon key insert into a table."""
    columns = re.search(rf"grant insert \(([^)]*)\)\s+on public\.{table} to anon;", MIGRATION).group(1)
    return {c.strip() for c in columns.split(",")}


class TelemetryCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.home = tmp / "config"
        self.project = tmp / "repo" / "acme"
        self.task = self.project / "tasks" / "q3-numbers.md"
        self.brief = self.project / "briefs" / "q3-numbers.md"
        self.task.parent.mkdir(parents=True)
        self.brief.parent.mkdir()
        self.task.write_text(f"# Q3\n\nProject: acme\nId: {TASK_ID}\n")
        self.sent = []
        self.enterContext(mock.patch.object(telemetry, "HOME", self.home))
        self.enterContext(mock.patch.object(telemetry, "config", lambda: ("https://x.supabase.co", "anon-key")))
        self.enterContext(mock.patch.object(telemetry, "send", lambda table, payload: self.sent.append((table, payload))))
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop("DAILY_WORK_TELEMETRY", None)

    def emit(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            telemetry.emit(*args)
        return out.getvalue()


class InstallId(TelemetryCase):
    def test_is_a_random_uuid_made_once_and_stored(self):
        first = telemetry.install_id()
        self.assertEqual(uuid.UUID(first).version, 4)
        self.assertEqual(first, telemetry.install_id())
        self.assertEqual((self.home / "install-id").read_text().strip(), first)

    def test_deleting_the_file_resets_it(self):
        first = telemetry.install_id()
        (self.home / "install-id").unlink()
        self.assertNotEqual(first, telemetry.install_id())

    def test_a_damaged_file_is_replaced(self):
        self.home.mkdir()
        (self.home / "install-id").write_text("not a uuid")
        self.assertEqual(uuid.UUID(telemetry.install_id()).version, 4)

    def test_nothing_about_the_person_or_machine_goes_into_it(self):
        source = (REPO / "scripts" / "telemetry.py").read_text()
        for word in ("hashlib", "hmac", "salt", "user.email", "getpass", "gethostname", "uuid1", "getnode", "platform"):
            self.assertNotIn(word, source)


class TaskId(TelemetryCase):
    def test_is_read_from_the_id_line_of_the_task_file(self):
        self.assertEqual(telemetry.task_id(self.task), TASK_ID)

    def test_before_grilling_it_is_read_from_the_brief(self):
        self.task.rename(self.brief)
        self.assertEqual(telemetry.task_id(self.task), TASK_ID)

    def test_missing_or_damaged_line_means_no_task_id(self):
        self.task.write_text("# Q3\n\nId: acme/tasks/q3-numbers\n")
        self.assertIsNone(telemetry.task_id(self.task))
        self.task.write_text("# Q3\n")
        self.assertIsNone(telemetry.task_id(self.task))
        self.task.unlink()
        self.assertIsNone(telemetry.task_id(self.task))
        self.assertNotIn("task_id", telemetry.common(self.task))

    def test_a_task_without_an_id_line_still_sends_its_record_event(self):
        self.task.write_text("# Q3\n")
        self.emit("record", self.task)  # first run: the notice
        self.emit("record", self.task)
        self.assertEqual(set(self.sent[0][1]), {"event", "ts", "plugin_version", "install_id"})


class SupabasePayloads(TelemetryCase):
    def events(self):
        self.emit("brief", self.task)  # first run: the notice
        self.emit("brief", self.task)
        self.emit("record", self.task)
        with redirect_stdout(io.StringIO()):
            hook = {"cwd": "/", "tool_input": {"file_path": str(self.task)}}
            self.brief.write_text("x")
            with mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook).encode()))):
                telemetry.main(["telemetry.py", "hook"])
        return self.sent

    def test_each_event_goes_to_the_events_table_with_exactly_its_fields(self):
        base = {"event", "ts", "plugin_version", "install_id", "task_id"}
        (t1, brief), (t2, record), (t3, grill) = self.events()
        self.assertEqual({t1, t2, t3}, {"events"})
        self.assertEqual(set(brief), base)
        self.assertEqual(set(record), base)
        self.assertEqual(set(grill), base | {"outcome"})
        self.assertEqual((brief["event"], record["event"], grill["outcome"]), ("brief", "record", "completed"))

    def test_values_fit_the_migration(self):
        for _, payload in self.events():
            self.assertLessEqual(set(payload), granted("events"))
            self.assertEqual(payload["task_id"], TASK_ID)
            self.assertEqual(payload["install_id"], telemetry.install_id())
            self.assertRegex(payload["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertRegex(payload["plugin_version"], r"^\d+\.\d+\.\d+$")

    def test_no_path_or_name_is_in_any_payload(self):
        text = json.dumps(self.events())
        for clear in ("acme", "q3-numbers", "tasks", str(self.project.parent)):
            self.assertNotIn(clear, text)

    def test_request_is_an_insert_with_the_anon_key(self):
        r = telemetry.request("events", b"{}")
        self.assertEqual(r.full_url, "https://x.supabase.co/rest/v1/events")
        self.assertEqual(r.get_method(), "POST")
        self.assertEqual(r.get_header("Apikey"), "anon-key")
        self.assertEqual(r.get_header("Prefer"), "return=minimal")
        self.assertEqual(r.get_header("Content-type"), "application/json")
        self.assertEqual(r.get_header("Content-profile"), "public")

    def test_test_sessions_go_to_the_sim_schema(self):
        with mock.patch.dict(os.environ, {"DAILY_WORK_TARGET": "test"}):
            self.assertEqual(telemetry.request("events", b"{}").get_header("Content-profile"), "sim")
        with mock.patch.dict(os.environ, {"DAILY_WORK_TARGET": "real"}):
            self.assertEqual(telemetry.request("events", b"{}").get_header("Content-profile"), "public")

    def test_no_rating_is_asked_for_or_sent(self):
        self.assertNotIn("rating", (REPO / "scripts" / "telemetry.py").read_text())
        self.assertNotIn("rating", (REPO / "scripts" / "record.sh").read_text())
        skill = (REPO / "skills" / "record" / "SKILL.md").read_text()
        self.assertNotIn("rating", skill)
        self.assertNotIn("Was this useful", skill)

    def test_feedback_payload_has_exactly_the_feedback_columns(self):
        import feedback
        with redirect_stdout(io.StringIO()) as out:
            feedback.preview(str(self.task), "grill asked too much")
        payload = json.loads((self.home / "feedback-pending.json").read_text())
        self.assertEqual(set(payload), granted("feedback"))
        self.assertEqual((payload["comment"], payload["content"]), ("grill asked too much", self.task.read_text()))
        self.assertIn((self.home / "feedback-pending.json").read_text(), out.getvalue())
        self.assertEqual(self.sent, [])


    def test_feedback_finds_a_task_by_its_name(self):
        import feedback
        with contextlib.chdir(self.project.parent), redirect_stdout(io.StringIO()):
            feedback.preview("q3-numbers", "fine")
        payload = json.loads((self.home / "feedback-pending.json").read_text())
        self.assertEqual((payload["task_id"], payload["content"]), (TASK_ID, self.task.read_text()))


class Packaging(unittest.TestCase):
    def test_copilot_hooks_run_the_plugin_scripts_with_the_content_switch(self):
        hooks = json.loads((REPO / "com.github.copilot" / "hooks" / "hooks.json").read_text())
        self.assertEqual(hooks["version"], 1)
        self.assertEqual(set(hooks["hooks"]), {"postToolUse", "userPromptSubmitted", "agentStop"})
        for event, entries in hooks["hooks"].items():
            command = entries[0]["bash"]
            self.assertIn('"$PLUGIN_ROOT/scripts/', command)
            if event != "postToolUse":
                self.assertIn('[ "${DAILY_WORK_CONTENT:-}" = 0 ] ||', command)

    def test_every_manifest_carries_the_same_version(self):
        claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        shared = json.loads((REPO / "plugin.json").read_text())
        versions = {claude["version"], shared["version"], market["metadata"]["version"], market["plugins"][0]["version"]}
        self.assertEqual(versions, {telemetry.version()})
        self.assertEqual({claude["name"], shared["name"], market["plugins"][0]["name"]}, {"daily-work"})

    def test_hooks_are_loaded_by_claude_code_only(self):
        claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
        self.assertTrue((REPO / claude["hooks"]).is_file())
        # Codex and Copilot pick up hooks/hooks.json on their own; ours speak Claude Code's events.
        self.assertFalse((REPO / "hooks").exists())
        self.assertNotIn("hooks", json.loads((REPO / "plugin.json").read_text()))

    def test_skills_find_the_plugin_folder_without_a_claude_only_variable(self):
        for skill in (REPO / "skills").glob("*/SKILL.md"):
            text = skill.read_text()
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", text, skill)
            self.assertIn("<plugin>/scripts/", text, skill)
            self.assertIn(f"this file is `<plugin>/skills/{skill.parent.name}/SKILL.md`", text, skill)

    def test_skills_load_in_copilot(self):
        # Copilot CLI skips a skill with disable-model-invocation, even when typed as a command.
        for skill in (REPO / "skills").glob("*/SKILL.md"):
            self.assertNotIn("disable-model-invocation", skill.read_text(), skill)


class Migration(unittest.TestCase):
    def test_anon_can_only_insert(self):
        self.assertIn("revoke all on public.events, public.feedback from anon, authenticated;", MIGRATION)
        self.assertEqual(MIGRATION.count("enable row level security"), 2)
        self.assertEqual(re.findall(r"for (\w+) to anon", MIGRATION), ["insert", "insert"])
        self.assertEqual(re.findall(r"grant (\w+)", MIGRATION), ["insert", "insert"])

    def test_events_and_feedback_are_separate_tables(self):
        self.assertEqual(granted("events"), {"event", "ts", "plugin_version", "install_id", "task_id", "outcome", "rating"})
        self.assertEqual(granted("feedback"), {"ts", "plugin_version", "install_id", "task_id", "comment", "content"})


class OptOut(TelemetryCase):
    def test_opted_out_sends_nothing_shows_nothing_and_writes_nothing(self):
        os.environ["DAILY_WORK_TELEMETRY"] = "0"
        self.assertEqual(self.emit("brief", self.task), "")
        self.assertEqual(self.sent, [])
        self.assertFalse(self.home.exists())
        self.assertFalse(telemetry.ready())

    def test_empty_telemetry_json_sends_nothing(self):
        with mock.patch.object(telemetry, "config", lambda: None):
            self.assertEqual(self.emit("brief", self.task), "")
            self.assertFalse(telemetry.ready())
        self.assertEqual(self.sent, [])
        self.assertFalse(self.home.exists())

    def test_telemetry_json_holds_only_the_url_and_the_public_key(self):
        c = json.loads((REPO / "telemetry.json").read_text())
        self.assertEqual(set(c), {"url", "anon_key"})
        self.assertNotIn("secret", c["anon_key"])

    def test_first_run_shows_the_notice_and_sends_nothing(self):
        shown = self.emit("brief", self.task)
        self.assertIn("DAILY_WORK_TELEMETRY=0", shown)
        self.assertEqual(self.sent, [])

    def test_second_run_sends_without_a_notice(self):
        self.emit("brief", self.task)
        self.assertTrue(telemetry.ready())
        self.assertEqual(self.emit("brief", self.task), "")
        self.assertEqual([p["event"] for _, p in self.sent], ["brief"])


class GrillHook(TelemetryCase):
    def hook(self, name):
        return {"cwd": str(self.project), "tool_input": {"file_path": str(self.project / name)}}

    def test_a_task_file_written_for_an_existing_brief_is_a_finished_grilling(self):
        self.brief.write_text("x")
        self.assertEqual(telemetry.grilled_task(self.hook("tasks/q3-numbers.md")), str(self.task))

    def test_a_relative_path_is_read_from_the_cwd(self):
        self.brief.write_text("x")
        hook = {"cwd": str(self.project.parent), "tool_input": {"file_path": "acme/tasks/q3-numbers.md"}}
        self.assertEqual(telemetry.grilled_task(hook), str(self.task))

    def test_a_windows_path_is_read_too(self):
        self.brief.write_text("x")
        hook = {"cwd": str(self.project.parent), "tool_input": {"file_path": "acme\\tasks\\q3-numbers.md"}}
        self.assertEqual(telemetry.grilled_task(hook), str(self.task))

    def test_a_task_file_without_a_brief_is_not(self):
        self.assertIsNone(telemetry.grilled_task(self.hook("tasks/q3-numbers.md")))

    def test_other_files_are_not(self):
        self.brief.write_text("x")
        self.assertIsNone(telemetry.grilled_task(self.hook("outputs/q3-numbers.md")))
        self.assertIsNone(telemetry.grilled_task(self.hook("tasks/other.md")))
        self.assertIsNone(telemetry.grilled_task(self.hook("briefs/q3-numbers.md")))
        self.assertIsNone(telemetry.grilled_task({}))


class CopilotGrillHook(TelemetryCase):
    def hook(self, patch, tool="apply_patch"):
        return {"sessionId": "s", "cwd": str(self.project.parent), "toolName": tool, "toolArgs": patch}

    def test_a_patch_adding_the_task_and_deleting_its_brief_is_a_finished_grilling(self):
        patch = "*** Begin Patch\n*** Add File: acme/tasks/q3-numbers.md\n+# Q3\n*** Delete File: acme/briefs/q3-numbers.md\n*** End Patch"
        self.assertEqual(telemetry.copilot_grilled_task(self.hook(patch)), str(self.task))

    def test_a_patch_adding_the_task_while_the_brief_exists_is_too(self):
        self.brief.write_text("x")
        patch = "*** Begin Patch\n*** Add File: acme/tasks/q3-numbers.md\n+# Q3\n*** End Patch"
        self.assertEqual(telemetry.copilot_grilled_task(self.hook(patch)), str(self.task))

    def test_other_patches_and_tools_are_not(self):
        self.brief.write_text("x")
        self.assertIsNone(telemetry.copilot_grilled_task(self.hook("*** Add File: acme/tasks/other.md\n")))
        self.assertIsNone(telemetry.copilot_grilled_task(self.hook("*** Update File: acme/tasks/q3-numbers.md\n")))
        self.assertIsNone(telemetry.copilot_grilled_task(self.hook({"path": "acme/tasks/q3-numbers.md"}, tool="view")))
        self.assertIsNone(telemetry.copilot_grilled_task({}))


if __name__ == "__main__":
    unittest.main()
