"""
Unit test suite for macOS Workflow & Task Monitoring MCP Server.
Verifies tool list schemas, tool executions, JSON-RPC 2.0 stdio protocol handling,
and integration with ActivityDB, ActivityMonitorDaemon, and MarkdownTaskManager.
"""

import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from macos_workflow_mcp.activity_tracker import set_mock_focus, set_mock_running_apps
from macos_workflow_mcp.db import ActivityDB
from macos_workflow_mcp.server import (
    TOOLS_SCHEMA,
    StdioMcpServer,
    WorkflowService,
    resolve_default_task_file,
)
from macos_workflow_mcp.task_manager import MarkdownTaskManager


class TestWorkflowService(unittest.TestCase):
    """Tests for the WorkflowService core business logic and tool functions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_activity.db")
        self.task_path = os.path.join(self.temp_dir.name, "test_tasks.md")

        self.db = ActivityDB(db_path=self.db_path)
        self.task_manager = MarkdownTaskManager(default_file=self.task_path)
        self.service = WorkflowService(
            db=self.db,
            task_manager=self.task_manager,
            default_task_file=self.task_path,
            enable_daemon=False,
        )

        set_mock_focus("Visual Studio Code", "server.py — macos_workflow_mcp", "com.microsoft.VSCode")
        set_mock_running_apps(["Finder", "Visual Studio Code", "Terminal", "Safari"])

    def tearDown(self) -> None:
        self.service.stop()
        self.temp_dir.cleanup()

    def test_get_current_focus(self) -> None:
        focus = self.service.get_current_focus()
        self.assertEqual(focus.get("app_name"), "Visual Studio Code")
        self.assertIn("server.py", focus.get("window_title", ""))
        self.assertEqual(focus.get("bundle_id"), "com.microsoft.VSCode")

    def test_get_running_apps(self) -> None:
        apps = self.service.get_running_apps()
        self.assertIsInstance(apps, list)
        self.assertIn("Visual Studio Code", apps)
        self.assertIn("Terminal", apps)

    def test_activity_summary_and_recent(self) -> None:
        now = datetime.now(timezone.utc)
        self.db.record_activity(
            app_name="Visual Studio Code",
            window_title="server.py",
            bundle_id="com.microsoft.VSCode",
            start_time=now - timedelta(minutes=40),
            end_time=now - timedelta(minutes=10),
            duration_seconds=1800.0,
        )
        self.db.record_activity(
            app_name="Terminal",
            window_title="zsh",
            bundle_id="com.apple.Terminal",
            start_time=now - timedelta(minutes=10),
            end_time=now,
            duration_seconds=600.0,
        )

        summary = self.service.get_activity_summary(since_minutes=60, limit=5)
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["app_name"], "Visual Studio Code")
        self.assertEqual(summary[0]["total_duration_seconds"], 1800.0)
        self.assertEqual(summary[0]["percentage"], 75.0)
        self.assertIn("server.py", summary[0]["sample_window_titles"])

        recent = self.service.get_recent_activity(limit=10)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["app_name"], "Terminal")

    def test_task_management_workflow(self) -> None:
        # Initially empty
        tasks = self.service.list_tasks(status="all")
        self.assertEqual(tasks, [])

        initial_summary = self.service.get_task_summary()
        self.assertEqual(initial_summary["total_tasks"], 0)

        # Add tasks
        t1 = self.service.add_task("Implement MCP tool routes #core @backend", section="Development")
        self.assertEqual(t1["text"], "Implement MCP tool routes #core @backend")
        self.assertFalse(t1["completed"])

        t2 = self.service.add_task("Write documentation #docs", section="Documentation")
        self.assertEqual(t2["text"], "Write documentation #docs")

        # Filter by status
        open_tasks = self.service.list_tasks(status="open")
        self.assertEqual(len(open_tasks), 2)

        # Filter by tag
        core_tasks = self.service.list_tasks(tag="#core")
        self.assertEqual(len(core_tasks), 1)
        self.assertEqual(core_tasks[0]["text"], "Implement MCP tool routes #core @backend")

        # Filter by section
        dev_tasks = self.service.list_tasks(section="Development")
        self.assertEqual(len(dev_tasks), 1)

        # Update task status
        updated = self.service.update_task_status("Implement MCP", completed=True)
        self.assertTrue(updated["completed"])

        # Summary check
        summary = self.service.get_task_summary()
        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["open_tasks"], 1)
        self.assertEqual(summary["completed_tasks"], 1)

        # Delete task
        deleted = self.service.delete_task("Write documentation")
        self.assertEqual(deleted["text"], "Write documentation #docs")

        remaining = self.service.list_tasks()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["text"], "Implement MCP tool routes #core @backend")

    def test_daemon_lifecycle_in_service(self) -> None:
        service_with_daemon = WorkflowService(
            db=self.db,
            task_manager=self.task_manager,
            enable_daemon=True,
            poll_interval=0.2,
        )
        self.assertIsNotNone(service_with_daemon.daemon)
        self.assertFalse(service_with_daemon.daemon.is_running)

        service_with_daemon.start()
        self.assertTrue(service_with_daemon.daemon.is_running)

        # Flush should execute cleanly
        service_with_daemon.daemon.poll_once()
        summary = service_with_daemon.get_activity_summary(since_minutes=10)
        self.assertIsInstance(summary, list)

        service_with_daemon.stop()
        self.assertFalse(service_with_daemon.daemon.is_running)


class TestStdioMcpServer(unittest.TestCase):
    """Tests for JSON-RPC 2.0 stdio MCP server protocol compliance."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_mcp.db")
        self.task_path = os.path.join(self.temp_dir.name, "test_mcp_tasks.md")

        self.db = ActivityDB(db_path=self.db_path)
        self.task_manager = MarkdownTaskManager(default_file=self.task_path)
        self.service = WorkflowService(
            db=self.db,
            task_manager=self.task_manager,
            default_task_file=self.task_path,
            enable_daemon=False,
        )
        self.server = StdioMcpServer(self.service)

        set_mock_focus("Google Chrome", "GitHub — Pull Request", "com.google.Chrome")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_schema_tool_count_and_keys(self) -> None:
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        resp = self.server.handle_message(req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.get("id"), 1)
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), 10)

        tool_names = {t["name"] for t in tools}
        expected_names = {
            "get_current_focus",
            "get_running_apps",
            "get_activity_summary",
            "get_recent_activity",
            "list_task_files",
            "list_tasks",
            "add_task",
            "update_task_status",
            "delete_task",
            "get_task_summary",
        }
        self.assertEqual(tool_names, expected_names)

        for t in tools:
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_initialize_and_ping(self) -> None:
        init_req = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        init_resp = self.server.handle_message(init_req)
        self.assertEqual(init_resp["id"], "init-1")
        self.assertEqual(init_resp["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "macos-workflow-mcp")

        # Notification handling
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        notif_resp = self.server.handle_message(notif)
        self.assertIsNone(notif_resp)

        # Ping
        ping_req = {"jsonrpc": "2.0", "id": 99, "method": "ping"}
        ping_resp = self.server.handle_message(ping_req)
        self.assertEqual(ping_resp["result"], {})

    def test_unknown_method(self) -> None:
        bad_req = {"jsonrpc": "2.0", "id": 42, "method": "non_existent_rpc"}
        resp = self.server.handle_message(bad_req)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_tool_call_get_current_focus(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "get_current_focus", "arguments": {}},
        }
        resp = self.server.handle_message(req)
        self.assertEqual(resp["id luxuries", "id"] if False else resp["id"], 10)
        self.assertFalse(resp["result"]["isError"])
        content_text = resp["result"]["content"][0]["text"]
        data = json.loads(content_text)
        self.assertEqual(data["app_name"], "Google Chrome")

    def test_tool_call_task_operations(self) -> None:
        # Add task
        add_req = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "add_task",
                "arguments": {"task_text": "Test MCP tool calling", "section": "MCP"},
            },
        }
        add_resp = self.server.handle_message(add_req)
        self.assertFalse(add_resp["result"]["isError"])
        added = json.loads(add_resp["result"]["content"][0]["text"])
        self.assertEqual(added["text"], "Test MCP tool calling")

        # List tasks
        list_req = {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "list_tasks", "arguments": {"status": "open"}},
        }
        list_resp = self.server.handle_message(list_req)
        tasks = json.loads(list_resp["result"]["content"][0]["text"])
        self.assertEqual(len(tasks), 1)

        # Update task
        update_req = {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "update_task_status",
                "arguments": {"task_identifier": "Test MCP", "completed": True},
            },
        }
        update_resp = self.server.handle_message(update_req)
        updated = json.loads(update_resp["result"]["content"][0]["text"])
        self.assertTrue(updated["completed"])

        # Task summary
        summary_req = {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {"name": "get_task_summary", "arguments": {}},
        }
        summary_resp = self.server.handle_message(summary_req)
        sum_data = json.loads(summary_resp["result"]["content"][0]["text"])
        self.assertEqual(sum_data["total_tasks"], 1)
        self.assertEqual(sum_data["completed_tasks"], 1)

        # Delete task
        del_req = {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {"name": "delete_task", "arguments": {"task_identifier": "Test MCP"}},
        }
        del_resp = self.server.handle_message(del_req)
        self.assertFalse(del_resp["result"]["isError"])

    def test_tool_call_invalid_tool_name(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {"name": "invalid_tool_foo", "arguments": {}},
        }
        resp = self.server.handle_message(req)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_tool_call_execution_error_handling(self) -> None:
        # add_task with empty task_text should raise ValueError inside tool
        req = {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {"name": "add_task", "arguments": {"task_text": ""}},
        }
        resp = self.server.handle_message(req)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("ValueError", resp["result"]["content"][0]["text"])

    def test_stdio_server_stream_run(self) -> None:
        req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_running_apps", "arguments": {}}})
        in_stream = io.StringIO(req1 + "\n" + req2 + "\n")
        out_stream = io.StringIO()

        self.server.run(in_stream=in_stream, out_stream=out_stream)
        out_lines = [line.strip() for line in out_stream.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(out_lines), 2)

        resp1 = json.loads(out_lines[0])
        self.assertEqual(resp1["id"], 1)
        self.assertEqual(resp1["result"], {})

        resp2 = json.loads(out_lines[1])
        self.assertEqual(resp2["id"], 2)
        apps = json.loads(resp2["result"]["content"][0]["text"])
        self.assertIn("Finder", apps)


if __name__ == "__main__":
    unittest.main()
