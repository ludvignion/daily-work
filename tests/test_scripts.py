"""The shell scripts the skills run: init.sh, brief.sh and record.sh, each in a throwaway repo.
Telemetry and content logging are switched off, and HOME points into the temporary folder."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PLACEHOLDER = "<written by /daily-work:record>"


class ScriptCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.dir = tmp / "work"
        self.dir.mkdir()
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(tmp / "home"),
            "DAILY_WORK_TELEMETRY": "0", "DAILY_WORK_CONTENT": "0", "DAILY_WORK_DATE": "2026-03-02",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        }

    def run_script(self, name, *args, stdin=""):
        p = subprocess.run(["bash", str(SCRIPTS / name), *args], cwd=self.dir, env=self.env,
                           input=stdin, capture_output=True, text=True)
        return p.returncode, p.stdout

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.dir, env=self.env, capture_output=True,
                              text=True, check=True).stdout

    def read(self, path):
        return (self.dir / path).read_text()

    def init(self):
        code, _ = self.run_script("init.sh")
        self.assertEqual(code, 0)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    def brief(self, project="acme", task="q3-numbers", text="Q3 numbers\nSum up Q3 sales for the board."):
        return self.run_script("brief.sh", project, task, stdin=text)

    def grill(self, project="acme", task="q3-numbers"):
        """What a grilling session leaves behind: the task file, and no brief."""
        brief = self.dir / project / "briefs" / f"{task}.md"
        body = brief.read_text().split("\n\n", 2)[2]
        (self.dir / project / "tasks" / f"{task}.md").write_text(
            f"# Q3 numbers\n\nProject: {project}\nCreated: 2026-03-02\n\n## Ask\n\n{body}\n"
            "## Spec\n\nPurpose: the board sees Q3 sales.\n\nDone looks like:\n- one table per region\n\n"
            f"Decided:\n\nOut of scope:\n\n## Result\n\n{PLACEHOLDER}\n\n## Caveats\n\n{PLACEHOLDER}\n")
        brief.unlink()


class Init(ScriptCase):
    def test_copies_every_file_and_makes_a_git_repo(self):
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        for f in ["AGENTS.md", "README.md", ".gitignore", ".env.example", "pyproject.toml",
                  ".claude/settings.json", "tools/.gitkeep"]:
            self.assertTrue((self.dir / f).exists(), f)
            self.assertIn(f"{f}: copied", out)
        self.assertIn("git: initialized", out)

    def test_creates_no_claude_md(self):
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        self.assertFalse((self.dir / "CLAUDE.md").exists())
        self.assertNotIn("CLAUDE.md", out)

    def test_existing_claude_md_keeps_its_text_and_imports_agents_md(self):
        (self.dir / "CLAUDE.md").write_text("Mine.\n")
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        self.assertEqual(self.read("CLAUDE.md"), "Mine.\n@AGENTS.md\n")
        self.assertIn("CLAUDE.md: appended 1 missing lines", out)
        code, out = self.run_script("init.sh")
        self.assertIn("CLAUDE.md: skipped", out)
        self.assertEqual(self.read("CLAUDE.md"), "Mine.\n@AGENTS.md\n")

    def test_second_run_changes_nothing(self):
        self.run_script("init.sh")
        before = {p: p.read_bytes() for p in self.dir.rglob("*") if p.is_file() and ".git" not in p.parts}
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        self.assertNotIn("copied", out)
        self.assertNotIn("git: initialized", out)
        after = {p: p.read_bytes() for p in self.dir.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(before, after)

    def test_existing_agents_md_keeps_its_text_and_gets_the_missing_sections(self):
        (self.dir / "AGENTS.md").write_text("# Mine\n\n## My rules\n\nKeep this.\n")
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith("# Mine\n\n## My rules\n\nKeep this.\n"))
        template = (REPO / "templates" / "repo" / "AGENTS.md").read_text()
        for h in [l for l in template.splitlines() if l.startswith("## ")]:
            self.assertIn(h, agents.splitlines())
        self.assertRegex(out, r"AGENTS\.md: appended \d+ missing sections")

    def test_existing_gitignore_gets_only_missing_lines(self):
        (self.dir / ".gitignore").write_text("node_modules\n")
        self.run_script("init.sh")
        lines = self.read(".gitignore").splitlines()
        self.assertEqual(lines[0], "node_modules")
        self.assertEqual(len(lines), len(set(lines)))


class Python(ScriptCase):
    """The plugin's Python runs through uv only; without it the skills still work and say so."""
    def no_uv(self):
        self.env["PATH"] = "/usr/bin:/bin"

    def test_init_says_when_there_is_no_uv(self):
        self.no_uv()
        code, out = self.run_script("init.sh")
        self.assertEqual(code, 0)
        self.assertIn("python: missing (no uv)", out)

    def test_init_says_when_uv_has_no_python_yet(self):
        code, out = self.run_script("init.sh")
        self.assertRegex(out, r"python: missing \(uv [0-9.]+, no Python yet\)")

    def test_brief_without_python_writes_an_id_and_says_so(self):
        self.no_uv()
        self.run_script("init.sh")
        code, out = self.run_script("brief.sh", "acme", "q3-numbers", stdin="Q3 numbers\nSum up Q3.")
        self.assertEqual(code, 0, out)
        self.assertRegex(self.read("acme/briefs/q3-numbers.md"),
                         r"\nId: [0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\n")
        self.assertIn("daily-work: no Python set up", out)

    def test_ids_differ(self):
        self.run_script("init.sh")
        ids = set()
        for task in ["a", "b", "c"]:
            self.run_script("brief.sh", "acme", task, stdin=f"{task}\nx")
            ids.add(re.search(r"\nId: (\S+)\n", self.read(f"acme/briefs/{task}.md")).group(1))
        self.assertEqual(len(ids), 3)

    def test_nothing_calls_the_system_python(self):
        for f in [*SCRIPTS.glob("*.sh"), REPO / "claude-code" / "hooks.json",
                  REPO / "com.github.copilot" / "hooks" / "hooks.json", *(REPO / "skills").glob("*/SKILL.md")]:
            code = [l for l in f.read_text().splitlines() if not l.lstrip().startswith("#")]
            # A python on its own is the system one; every python here is uv's ("$u" ...).
            self.assertFalse([l for l in code if re.search(r"(^|[\s;|&(])python3?\s", l) and '"$u" ' not in l], f)


class Brief(ScriptCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_new_project_and_brief(self):
        code, out = self.brief()
        self.assertEqual(code, 0, out)
        for d in ["tasks", "inputs", "outputs"]:
            self.assertTrue((self.dir / "acme" / d / ".gitkeep").exists())
        self.assertTrue((self.dir / "acme" / "sources.md").exists())
        brief = self.read("acme/briefs/q3-numbers.md")
        self.assertTrue(brief.startswith("# Q3 numbers\n\nProject: acme\nWritten: 2026-03-02\nId: "))
        self.assertTrue(brief.rstrip().endswith("Sum up Q3 sales for the board."))
        self.assertIn("- 2026-03-02 q3-numbers: open", self.read("acme/README.md"))
        self.assertIn("- acme", self.read("README.md").splitlines())
        self.assertIn("New project: acme/", out)
        self.assertIn("Created acme/briefs/q3-numbers.md", out)

    def test_second_task_in_the_same_project(self):
        self.brief()
        code, out = self.brief(task="q4-plan", text="Q4 plan\nDraft the Q4 plan.")
        self.assertEqual(code, 0, out)
        self.assertNotIn("New project", out)
        readme = self.read("acme/README.md")
        self.assertIn("- 2026-03-02 q3-numbers: open", readme)
        self.assertIn("- 2026-03-02 q4-plan: open", readme)
        self.assertEqual(self.read("README.md").splitlines().count("- acme"), 1)

    def test_refuses(self):
        cases = [
            (("Acme", "q3", "T\nx"), "outside [a-z0-9-]"),
            (("acme", "Q3 numbers", "T\nx"), "outside [a-z0-9-]"),
            (("acme", "q3", "Title only"), "usage:"),
        ]
        for (project, task, text), message in cases:
            code, out = self.brief(project, task, text)
            self.assertEqual(code, 1)
            self.assertIn(message, out)
        self.assertFalse((self.dir / "acme").exists())

    def test_refuses_an_existing_brief_or_task(self):
        self.brief()
        code, out = self.brief()
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        self.grill()
        code, out = self.brief()
        self.assertEqual(code, 1)
        self.assertIn("acme/tasks/q3-numbers.md already exists", out)

    def test_refuses_a_folder_that_is_not_a_project(self):
        (self.dir / "docs").mkdir()
        code, out = self.brief(project="docs")
        self.assertEqual(code, 1)
        self.assertIn("is not a project", out)

    def test_refuses_without_agents_md(self):
        (self.dir / "AGENTS.md").unlink()
        code, out = self.brief()
        self.assertEqual(code, 1)
        self.assertIn("no AGENTS.md here", out)


class Record(ScriptCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.brief()

    def write_result(self):
        task = self.dir / "acme" / "tasks" / "q3-numbers.md"
        task.write_text(task.read_text().replace(PLACEHOLDER, "Done, see outputs/q3.md.", 1)
                        .replace(PLACEHOLDER, "Region totals not checked against finance."))

    def test_list(self):
        _, out = self.run_script("record.sh", "list")
        self.assertEqual(out, "acme/briefs/q3-numbers.md (not grilled yet)\n")
        self.grill()
        _, out = self.run_script("record.sh", "list")
        self.assertEqual(out, "acme/tasks/q3-numbers.md\n")

    def test_list_with_nothing_open(self):
        (self.dir / "acme" / "README.md").write_text("# acme\n\n## Tasks\n- 2026-03-02 q3-numbers: done, x\n")
        _, out = self.run_script("record.sh", "list")
        self.assertEqual(out, "no open tasks\n")

    def test_begin_then_finish_commits_and_marks_done(self):
        self.grill()
        (self.dir / "acme" / "outputs" / "q3.md").write_text("| Region | Sales |\n")
        code, out = self.run_script("record.sh", "begin", "q3-numbers")
        self.assertEqual(code, 0, out)
        self.assertIn("task: acme/tasks/q3-numbers.md", out)
        self.assertIn("  acme/outputs/q3.md", out)
        self.write_result()
        code, out = self.run_script("record.sh", "finish", "q3-numbers", stdin="Q3 table\nfor the board\n")
        self.assertEqual(code, 0, out)
        self.assertIn("- 2026-03-02 q3-numbers: done, Q3 table for the board", self.read("acme/README.md"))
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), "daily-work: record q3-numbers")
        committed = self.git("show", "--name-only", "--format=", "HEAD").split()
        self.assertIn("acme/tasks/q3-numbers.md", committed)
        self.assertIn("acme/outputs/q3.md", committed)
        self.assertIn("  - one table per region", out)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_begin_refuses_a_brief_not_yet_grilled(self):
        code, out = self.run_script("record.sh", "begin", "q3-numbers")
        self.assertEqual(code, 1)
        self.assertIn("is still a brief", out)

    def test_begin_refuses_an_unknown_task(self):
        code, out = self.run_script("record.sh", "begin", "nothing-here")
        self.assertEqual(code, 1)
        self.assertIn("no task named 'nothing-here'", out)

    def test_finish_refuses_without_begin(self):
        self.grill()
        self.write_result()
        code, out = self.run_script("record.sh", "finish", "q3-numbers", stdin="x")
        self.assertEqual(code, 1)
        self.assertIn("run record.sh begin", out)

    def test_finish_refuses_a_changed_spec(self):
        self.grill()
        self.run_script("record.sh", "begin", "acme/tasks/q3-numbers.md")
        self.write_result()
        task = self.dir / "acme" / "tasks" / "q3-numbers.md"
        task.write_text(task.read_text().replace("one table per region", "one chart"))
        code, out = self.run_script("record.sh", "finish", "q3-numbers", stdin="x")
        self.assertEqual(code, 1)
        self.assertIn("changed since begin", out)
        self.assertIn("- 2026-03-02 q3-numbers: open", self.read("acme/README.md"))

    def test_finish_refuses_the_placeholder(self):
        self.grill()
        self.run_script("record.sh", "begin", "q3-numbers")
        code, out = self.run_script("record.sh", "finish", "q3-numbers", stdin="x")
        self.assertEqual(code, 1)
        self.assertIn("still holds the placeholder", out)

    def test_finish_refuses_an_empty_summary(self):
        self.grill()
        self.run_script("record.sh", "begin", "q3-numbers")
        self.write_result()
        code, out = self.run_script("record.sh", "finish", "q3-numbers", stdin="  \n")
        self.assertEqual(code, 1)
        self.assertIn("no one-line summary", out)


if __name__ == "__main__":
    unittest.main()
