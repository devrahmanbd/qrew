"""
Local Stdio MCP Bridge for Claude Desktop / Cursor.
Implements Model Context Protocol (MCP) JSON-RPC 2.0 over stdio,
transparently proxying tool calls directly to the 24/7 central workflow server.
Zero external dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("mac_client.mcp_bridge")

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8765").rstrip("/")

TOOLS_SCHEMA = [
    {
        "name": "list_tasks",
        "description": "List tasks from the active Obsidian daily note (e.g. 17-Sep.md) with status, section, and tag filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Target date note (e.g. '17-Sep' or 'today'). Defaults to today's note.",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'all', 'open', or 'completed'.",
                    "default": "all",
                },
                "section": {
                    "type": "string",
                    "description": "Filter by section heading (e.g. '## 17-Sep').",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_task",
        "description": "Add a new task to the Obsidian vault and sync instantly across Mac, Android, and Chrome.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_text": {
                    "type": "string",
                    "description": "Description of the task to create.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target date note (e.g. '17-Sep' or 'today').",
                    "default": "",
                },
                "section": {
                    "type": "string",
                    "description": "Section header. Defaults to ## DD-MMM matching the note.",
                    "default": "",
                },
            },
            "required": ["task_text"],
        },
    },
    {
        "name": "update_task_status",
        "description": "Toggle task completion status ([ ] <-> [x]) in Obsidian vault and push real-time updates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_identifier": {
                    "type": "string",
                    "description": "Task description match or 1-based line number.",
                },
                "completed": {
                    "type": "boolean",
                    "description": "True to mark completed ([x]), False for open ([ ]).",
                    "default": True,
                },
                "file_path": {
                    "type": "string",
                    "description": "Target date note (e.g. '17-Sep').",
                    "default": "",
                },
            },
            "required": ["task_identifier"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task line from the Obsidian vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_identifier": {
                    "type": "string",
                    "description": "Task description match or line number.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target date note (e.g. '17-Sep').",
                    "default": "",
                },
            },
            "required": ["task_identifier"],
        },
    },
    {
        "name": "prioritize_tasks",
        "description": "Run graph topological sorting and AI reasoning to return prioritized roadmap and immediate focus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Target date note (e.g. '17-Sep').",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_current_focus",
        "description": "Get current active desktop application, window title, and active browser tab.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_task_files",
        "description": "List all daily notes available in the Obsidian Task-List vault (e.g. 17-Sep.md).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


class McpServerProxy:
    """Proxies MCP tool calls over HTTP to the central server."""

    def __init__(self, server_url: Optional[str] = None) -> None:
        self.server_url = (server_url or SERVER_URL).rstrip("/")

    def _http_request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = f"{self.server_url}{endpoint}"
        if query_params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query_params.items() if v})

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Server HTTP {e.code}: {err_body}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to central server at {self.server_url}: {e}")

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to corresponding server REST API endpoint."""
        if name == "list_tasks":
            return self._http_request(
                "/api/tasks",
                method="GET",
                query_params={
                    "file_path": args.get("file_path", ""),
                    "status": args.get("status", "all"),
                    "section": args.get("section", ""),
                },
            )

        elif name == "add_task":
            return self._http_request(
                "/api/tasks",
                method="POST",
                payload={
                    "text": args.get("task_text", ""),
                    "file_path": args.get("file_path", ""),
                    "section": args.get("section", ""),
                },
            )

        elif name == "update_task_status":
            task_id = urllib.parse.quote(str(args.get("task_identifier", "")))
            return self._http_request(
                f"/api/tasks/{task_id}",
                method="PATCH",
                payload={
                    "completed": bool(args.get("completed", True)),
                    "file_path": args.get("file_path", ""),
                },
            )

        elif name == "delete_task":
            task_id = urllib.parse.quote(str(args.get("task_identifier", "")))
            return self._http_request(
                f"/api/tasks/{task_id}",
                method="DELETE",
                query_params={"file_path": args.get("file_path", "")},
            )

        elif name == "prioritize_tasks":
            return self._http_request(
                "/api/tasks/prioritize",
                method="GET",
                query_params={"file_path": args.get("file_path", "")},
            )

        elif name == "get_current_focus":
            return self._http_request("/api/focus/current", method="GET")

        elif name == "list_task_files":
            return self._http_request("/api/tasks/files", method="GET")

        else:
            raise ValueError(f"Unknown tool: {name}")


class StdioMcpBridge:
    """Handles JSON-RPC 2.0 protocol over stdio."""

    def __init__(self, proxy: Optional[McpServerProxy] = None) -> None:
        self.proxy = proxy or McpServerProxy()

    def handle_message(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "workflow-mcp-bridge", "version": "1.0.0"},
                },
            }

        elif method in ("notifications/initialized", "initialized"):
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS_SCHEMA}}

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {}) or {}
            try:
                res = self.proxy.execute_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                        "isError": False,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True,
                    },
                }

        else:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            return None

    def run(self, in_stream=None, out_stream=None) -> None:
        """Run stdio message processing loop."""
        inp = in_stream or sys.stdin
        out = out_stream or sys.stdout

        for line in inp:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
            except Exception:
                err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                out.write(json.dumps(err) + "\n")
                out.flush()
                continue

            resp = self.handle_message(req)
            if resp is not None:
                out.write(json.dumps(resp) + "\n")
                out.flush()


def main():
    bridge = StdioMcpBridge()
    bridge.run()


if __name__ == "__main__":
    main()
