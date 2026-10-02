#""Comprehensive test suite for MarkdownTaskManager."""

import os
import tempfile
import unittest
from pathlib import Path

from macos_workflow_mcp.task_manager import MarkdownTaskManager


class TestMarkdownTaskManager(unittest.TestCase):
    """Unit and integration tests for MarkdownTaskManager."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sample_md_path = os.path.join(self.temp_dir.name, "tasks.md")
        self.sample_content = """# Tasks Overview
- [ ] Pre-section task #general @admin

## Work
- [ ] Implement auth flow #urgent #backend
- [x] Fix navbar bug @frontend
  * [ ] Indented subtask #p1

## Personal
- [x] Buy groceries #errands
+ [ ] Read chapter 4 #book
"""
        with open(self.sample_md_path, "w", encoding="utf-8") as f:
            f.write(self.sample_content)

        self.manager = MarkdownTaskManager(default_file=self.sample_md_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_tasks_all(self) -> None:
        tasks = self.manager.list_tasks()
        self.assertEqual(len(tasks), 6)

        t0 = tasks[0]
        self.assertEqual(t0["line_number"], 2)
        self.assertEqual(t0["text"], "Pre-section task #general @admin")
        self.assertFalse(t0["completed"])
        self.assertEqual(t0["section"], "# Tasks Overview")
        self.assertIn("#general", t0["tags"])
        self.assertIn("@admin", t0["tags"])
        self.assertEqual(t0["raw_line"], "- [ ] Pre-section task #general @admin")

        t3 = tasks[3]
        self.assertEqual(t3["section"], "## Work")
        self.assertFalse(t3["completed"])
        self.assertIn("#p1", t3["tags"])

    def test_list_tasks_status_filter(self) -> None:
        open_tasks = self.manager.list_tasks(status="open")
        self.assertEqual(len(open_tasks), 4)
        for t in open_tasks:
            self.assertFalse(t["completed"])

        done_tasks = self.manager.list_tasks(status="completed")
        self.assertEqual(len(done_tasks), 2)
        for t in done_tasks:
            self.assertTrue(t["completed"])

        done_alias = self.manager.list_tasks(status="done")
        self.assertEqual(len(done_alias), 2)

        with self.assertRaises(ValueError):
            self.manager.list_tasks(status="invalid_status")

    def test_list_tasks_section_filter(self) -> None:
        work_tasks = self.manager.list_tasks(section="work")
        self.assertEqual(len(work_tasks), 3)
        for t in work_tasks:
            self.assertEqual(t["section"], "## Work")

        personal_tasks = self.manager.list_tasks(section="Personal")
        self.assertEqual(len(personal_tasks), 2)

    def test_list_tasks_tag_filter(self) -> None:
        urgent_tasks = self.manager.list_tasks(tag="#urgent")
        self.assertEqual(len(urgent_tasks), 1)
        self.assertEqual(urgent_tasks[0]["text"], "Implement auth flow #urgent #backend")

        urgent_no_hash = self.manager.list_tasks(tag="urgent")
        self.assertEqual(len(urgent_no_hash), 1)

        admin_tasks = self.manager.list_tasks(tag="admin")
        self.assertEqual(len(admin_tasks), 1)
        self.assertEqual(admin_tasks[0]["text"], "Pre-section task #general @admin")

    def test_empty_file(self) -> None:
        empty_path = os.path.join(self.temp_dir.name, "empty.md")
        Path(empty_path).touch()

        tasks = self.manager.list_tasks(file_path=empty_path)
        self.assertEqual(tasks, [])

        summary = self.manager.get_task_summary(file_path=empty_path)
        self.assertEqual(summary["total_tasks"], 0)
        self.assertEqual(summary["open_tasks"], 0)
        self.assertEqual(summary["completed_tasks"], 0)
        self.assertEqual(summary["breakdown_by_section"], {})
        self.assertEqual(summary["top_open_tasks"], [])

    def test_add_task_to_existing_section(self) -> None:
        added = self.manager.add_task(task_text="Review PR #42 #urgent", section="Work")
        self.assertEqual(added["text"], "Review PR #42 #urgent")
        self.assertEqual(added["section"], "## Work")
        self.assertIn("#urgent", added["tags"])

        with open(self.sample_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        work_idx = content.find("## Work")
        new_task_idx = content.find("Review PR #42")
        personal_idx = content.find("## Personal")
        self.assertTrue(work_idx < new_task_idx < personal_idx)

    def test_add_task_to_new_section(self) -> None:
        added = self.manager.add_task(task_text="Capture idea #inbox", section="Inbox")
        self.assertEqual(added["text"], "Capture idea #inbox")
        self.assertEqual(added["section"], "## Inbox")

        with open(self.sample_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("## Inbox", content)
        self.assertIn("- [ ] Capture idea #inbox", content)

    def test_add_task_with_no_section(self) -> None:
        added = self.manager.add_task(task_text="Standalone task", section=None)
        self.assertEqual(added["text"], "Standalone task")

        with open(self.sample_md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(lines[-1].strip(), "- [ ] Standalone task")

    def test_add_task_empty_text_error(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.add_task(task_text="   ")

    def test_update_task_status_by_line_number(self) -> None:
        updated = self.manager.update_task_status(task_identifier=5, completed=True)
        self.assertTrue(updated["completed"])
        self.assertEqual(updated["line_number"], 5)

        with open(self.sample_md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(lines[4].strip(), "- [x] Implement auth flow #urgent #backend")

        reverted = self.manager.update_task_status(task_identifier="5", completed=False)
        self.assertFalse(reverted["completed"])

        with open(self.sample_md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(lines[4].strip(), "- [ ] Implement auth flow #urgent #backend")

    def test_update_task_status_preserving_indentation_and_bullet(self) -> None:
        updated = self.manager.update_task_status(task_identifier="Indented subtask", completed=True)
        self.assertTrue(updated["completed"])
        self.assertEqual(updated["raw_line"], "  * [x] Indented subtask #p1")

    def test_update_task_status_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.update_task_status(task_identifier=999, completed=True)

        with self.assertRaises(ValueError):
            self.manager.update_task_status(task_identifier=1, completed=True)

        with self.assertRaises(ValueError):
            self.manager.update_task_status(task_identifier="Non-existent description", completed=True)

    def test_delete_task_by_query_and_line_number(self) -> None:
        deleted = self.manager.delete_task(task_identifier="Fix navbar bug")
        self.assertEqual(deleted["text"], "Fix navbar bug @frontend")

        tasks_after = self.manager.list_tasks()
        self.assertEqual(len(tasks_after), 5)
        self.assertNotIn("Fix navbar bug", [t["text"] for t in tasks_after])

        t_first = tasks_after[0]
        deleted_first = self.manager.delete_task(task_identifier=t_first["line_number"])
        self.assertEqual(deleted_first["text"], t_first["text"])

        tasks_remaining = self.manager.list_tasks()
        self.assertEqual(len(tasks_remaining), 4)

    def test_delete_task_non_existent_error(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.delete_task(task_identifier="completely missing task")

    def test_get_task_summary(self) -> None:
        summary = self.manager.get_task_summary()
        self.assertEqual(summary["total_tasks"], 6)
        self.assertEqual(summary["open_tasks"], 4)
        self.assertEqual(summary["completed_tasks"], 2)

        breakdown = summary["breakdown_by_section"]
        self.assertIn("## Work", breakdown)
        self.assertEqual(breakdown["## Work"]["total"], 3)
        self.assertEqual(breakdown["## Work"]["open"], 2)
        self.assertEqual(breakdown["## Work"]["completed"], 1)

        self.assertIn("## Personal", breakdown)
        self.assertEqual(breakdown["## Personal"]["total"], 2)
        self.assertEqual(breakdown["## Personal"]["open"], 1)
        self.assertEqual(breakdown["## Personal"]["completed"], 1)

        top_open = summary["top_open_tasks"]
        self.assertLessEqual(len(top_open), 5)
        self.assertTrue(all(not t["completed"] for t in top_open))

    def test_file_not_found(self) -> None:
        missing_mgr = MarkdownTaskManager(default_file="/path/to/nonexistent/file.md")
        with self.assertRaises(FileNotFoundError):
            missing_mgr.list_tasks()

    def test_no_file_specified(self) -> None:
        no_file_mgr = MarkdownTaskManager()
        with self.assertRaises(ValueError):
            no_file_mgr.list_tasks()




if __name__ == "__main__":
    unittest.main()
