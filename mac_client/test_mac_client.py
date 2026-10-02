"""Unit tests for mac_client modules."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from mac_client.focus_streamer import DesktopFocusStreamer
from mac_client.mcp_bridge import StdioMcpBridge, McpServerProxy, TOOLS_SCHEMA
from mac_client.vault_sync import ObsidianVaultSync


class TestMacClient(unittest.TestCase):
    def test_vault_sync_loop_prevention(self):
        with tempfile.TemporaryDirectory() as td:
            sync = ObsidianVaultSync(vault_dir=td, poll_interval=0.1)
            sync.scan_initial_state()

            # Apply remote update (e.g. from Android)
            file_name = "17-Sep.md"
            content = "## 17-Sep\n\n- [x] Account Recovery of Flynn, Shaheen(first)\n"
            applied = sync.apply_remote_update(file_name, content)
            self.assertTrue(applied)

            # Check that file on disk was written
            disk_content = (Path(td) / file_name).read_text(encoding="utf-8")
            self.assertEqual(disk_content, content)

            # Check that hash suppression was registered
            file_hash = sync._compute_hash(content)
            self.assertIn(file_hash, sync._suppressed_hashes)

            # Perform a poll step and verify suppression is consumed without error
            sync._poll_step()
            self.assertNotIn(file_hash, sync._suppressed_hashes)

    def test_focus_streamer_mock(self):
        streamer = DesktopFocusStreamer(poll_interval=0.1)
        streamer.set_mock_focus("Google Chrome", "Pull Requests · GitHub", "com.google.Chrome")
        focus = streamer.get_current_focus()
        self.assertEqual(focus["app_name"], "Google Chrome")
        self.assertEqual(focus["window_title"], "Pull Requests · GitHub")

    def test_mcp_bridge_protocol(self):
        bridge = StdioMcpBridge()

        # Initialize
        init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = bridge.handle_message(init_req)
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "workflow-mcp-bridge")

        # Tools list
        tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        tools_resp = bridge.handle_message(tools_req)
        self.assertEqual(len(tools_resp["result"]["tools"]), len(TOOLS_SCHEMA))
        tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
        self.assertIn("list_tasks", tool_names)
        self.assertIn("add_task", tool_names)
        self.assertIn("prioritize_tasks", tool_names)


if __name__ == "__main__":
    unittest.main()
