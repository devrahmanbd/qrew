"""
macOS Workflow & Task Monitoring MCP Server.
Provides tools for querying active app/window focus, historical application usage,
and reading/modifying local Markdown task lists or Obsidian Task-List vaults.
Supports both FastMCP (when mcp is installed) and a built-in JSON-RPC 2.0 stdio server.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .activity_tracker import (
    ActivityMonitorDaemon,
    get_current_focus as sys_get_current_focus,
    get_running_apps as sys_get_running_apps,
)
from .db import ActivityDB
from .task_manager import MarkdownTaskManager

logger = logging.getLogger("macos_workflow_mcp.server")

# Try importing FastMCP if available
try:
    from mcp.server.fastmcp import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False


def resolve_default_task_file() -> Optional[str]:
    """Resolve default markdown task file from env or standard paths."""
    env_file = os.environ.get("DEFAULT_TASK_FILE")
    if env_file:
        return str(Path(os.path.expanduser(env_file)).resolve())

    todo = Path(os.path.expanduser("~/todo.md")).resolve()
    tasks = Path(os.path.expanduser("~/tasks.md")).resolve()
    if todo.exists():
        return str(todo)
    if tasks.exists():
        return str(tasks)
    return None


def resolve_default_task_dir() -> Optional[str]:
    """Resolve default task directory (e.g., Obsidian Task-List vault) from env."""
    env_dir = os.environ.get("DEFAULT_TASK_DIR")
    if env_dir:
        return str(Path(os.path.expanduser(env_dir)).resolve())
    return None


class WorkflowService:
    """
    Core service coordinating ActivityDB, ActivityMonitorDaemon,
    and MarkdownTaskManager for MCP tools.
    """

    def __init__(
        self,
        db: Optional[ActivityDB] = None,
        task_manager: Optional[MarkdownTaskManager] = None,
        default_task_file: Optional[str] = None,
        default_task_dir: Optional[str] = None,
        enable_daemon: bool = True,
        poll_interval: float = 3.0,
    ) -> None:
        self.db = db if db is not None else ActivityDB()
        self.default_task_file = default_task_file or resolve_default_task_file()
        self.default_task_dir = default_task_dir or resolve_default_task_dir()
        self.task_manager = task_manager if task_manager is not None else MarkdownTaskManager(
            default_file=self.default_task_file,
            task_dir=self.default_task_dir,
        )

        # Check env var for daemon enablement
        env_daemon = os.environ.get("ENABLE_ACTIVITY_DAEMON", "").lower()
        if env_daemon in ("0", "false", "no"):
            enable_daemon = False

        self.enable_daemon = enable_daemon
        self.poll_interval = poll_interval
        self.daemon: Optional[ActivityMonitorDaemon] = None

        if self.enable_daemon:
            self.daemon = ActivityMonitorDaemon(db=self.db, poll_interval=self.poll_interval)

    def start(self) -> None:
        """Start background services if enabled."""
        if self.daemon and not self.daemon.is_running:
            logger.info("Starting background ActivityMonitorDaemon...")
            self.daemon.start()

    def stop(self) -> None:
        """Stop background services gracefully."""
        if self.daemon and self.daemon.is_running:
            logger.info("Stopping background ActivityMonitorDaemon...")
            self.daemon.stop()

    # --- Tool Implementations ---

    def get_current_focus(self) -> Dict[str, str]:
        """Active app, window title, and bundle ID."""
        return sys_get_current_focus()

    def get_running_apps(self) -> List[str]:
        """List of visible running apps."""
        return sys_get_running_apps()

    def get_activity_summary(self, since_minutes: int = 60, limit: int = 15) -> List[Dict[str, Any]]:
        """App usage summary, percentage, and sample windows."""
        if self.daemon and self.daemon.is_running:
            self.daemon.flush()
        return self.db.get_activity_summary(since_minutes=since_minutes, limit=limit)

    def get_recent_activity(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Chronological activity log."""
        if self.daemon and self.daemon.is_running:
            self.daemon.flush()
        return self.db.get_recent_events(limit=limit)

    def list_task_files(self) -> List[str]:
        """List all markdown files available in the task directory."""
        return self.task_manager.list_task_files()

    def list_tasks(
        self,
        file_path: str = "",
        status: str = "all",
        section: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        """List markdown tasks with optional status, section, and tag filters."""
        target_path = file_path.strip() if file_path else None
        try:
            return self.task_manager.list_tasks(
                file_path=target_path,
                status=status or "all",
                section=section.strip() if section else None,
                tag=tag.strip() if tag else None,
            )
        except FileNotFoundError:
            return []

    def add_task(
        self,
        task_text: str,
        file_path: str = "",
        section: str = "",
    ) -> Dict[str, Any]:
        """Add a new task to the markdown task file."""
        target_path = file_path.strip() if file_path else None
        sec = section.strip() if section else None
        return self.task_manager.add_task(
            file_path=target_path,
            task_text=task_text,
            section=sec,
        )

    def update_task_status(
        self,
        task_identifier: str,
        completed: bool = True,
        file_path: str = "",
    ) -> Dict[str, Any]:
        """Toggle task completion status."""
        target_path = file_path.strip() if file_path else None
        return self.task_manager.update_task_status(
            file_path=target_path,
            task_identifier=task_identifier,
            completed=completed,
        )

    def delete_task(
        self,
        task_identifier: str,
        file_path: str = "",
    ) -> Dict[str, Any]:
        """Delete a task from the markdown task file."""
        target_path = file_path.strip() if file_path else None
        return self.task_manager.delete_task(
            file_path=target_path,
            task_identifier=task_identifier,
        )

    def get_task_summary(self, file_path: str = "") -> Dict[str, Any]:
        """Statistical summary of tasks and section breakdowns."""
        target_path = file_path.strip() if file_path else None
        try:
            return self.task_manager.get_task_summary(file_path=target_path)
        except FileNotFoundError:
            return {
                "file": "none",
                "total_tasks": 0,
                "open_tasks": 0,
                "completed_tasks": 0,
                "breakdown_by_section": {},
                "top_open_tasks": [],
            }


TOOLS_SCHEMA = [
    {
        "name": "get_current_focus",
        "description": "Get the currently active frontmost macOS application, window title, and bundle identifier.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_running_apps",
        "description": "List names of all currently running visible GUI applications on macOS.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_activity_summary",
        "description": "Get summary of time spent per application over the last N minutes with percentage and sample window titles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since_minutes": {
                    "type": "integer",
                    "description": "Number of minutes into the past to aggregate (default 60).",
                    "default": 60,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of apps to return (default 15).",
                    "default": 15,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_recent_activity",
        "description": "Get chronological log of recent application and window focus changes (most recent first).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return (default 30).",
                    "default": 30,
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_task_files",
        "description": "List all markdown files available in the configured task directory (e.g. 17-Sep.md, 18-Sep.md).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks from a local Markdown task file or Obsidian vault (supports 'today', '17-Sep', or custom file_path) with status, section, and tag filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file, relative date like '17-Sep' or 'today' (defaults to today's note in DEFAULT_TASK_DIR or DEFAULT_TASK_FILE).",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Task status filter: 'all', 'open', or 'completed' (default 'all').",
                    "default": "all",
                },
                "section": {
                    "type": "string",
                    "description": "Filter by section header name (e.g. '## 17-Sep' or 'Inbox').",
                    "default": "",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag (e.g. '#urgent' or '@dev').",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_task",
        "description": "Add a new checkbox task to a markdown file (defaults to today's note under matching ## DD-MMM header).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_text": {
                    "type": "string",
                    "description": "The description of the task to add.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target markdown file or date (e.g. '17-Sep' or 'today'). Defaults to today's note.",
                    "default": "",
                },
                "section": {
                    "type": "string",
                    "description": "Section header to place the task under. If empty, automatically matches the date header (e.g. ## 17-Sep) or appends to file.",
                    "default": "",
                },
            },
            "required": ["task_text"],
        },
    },
    {
        "name": "update_task_status",
        "description": "Toggle task completion between [ ] and [x] in a markdown file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_identifier": {
                    "type": "string",
                    "description": "1-based line number or query text matching the task description.",
                },
                "completed": {
                    "type": "boolean",
                    "description": "True to mark completed ([x]), False to mark uncompleted ([ ]).",
                    "default": True,
                },
                "file_path": {
                    "type": "string",
                    "description": "Target markdown file or date (e.g. '17-Sep' or 'today').",
                    "default": "",
                },
            },
            "required": ["task_identifier"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task line from a markdown file by line number or query text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_identifier": {
                    "type": "string",
                    "description": "1-based line number or query text matching the task description.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target markdown file or date (e.g. '17-Sep' or 'today').",
                    "default": "",
                },
            },
            "required": ["task_identifier"],
        },
    },
    {
        "name": "get_task_summary",
        "description": "Get summary metrics for tasks (total, open, completed, breakdown by section, top open tasks).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Target markdown file or date (e.g. '17-Sep' or 'today').",
                    "default": "",
                },
            },
            "required": [],
        },
    },
]


class StdioMcpServer:
    """
    Standard JSON-RPC 2.0 stdio server conforming to Model Context Protocol (MCP).
    Operates without requiring third-party dependencies.
    """

    def __init__(self, service: Optional[WorkflowService] = None) -> None:
        self.service = service if service is not None else WorkflowService()

    def handle_message(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process an in-memory JSON-RPC request dictionary."""
        return self.handle_request(req)

    def run(self, in_stream: Optional[Any] = None, out_stream: Optional[Any] = None) -> None:
        """Run the stdio message processing loop."""
        inp = in_stream if in_stream is not None else sys.stdin
        out = out_stream if out_stream is not None else sys.stdout

        self.service.start()
        try:
            for line in inp:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    request = json.loads(line_str)
                except Exception as e:
                    logger.error(f"Invalid JSON received: {e}")
                    self._send_error(None, -32700, "Parse error", out_stream=out)
                    continue

                response = self.handle_request(request)
                if response is not None:
                    out.write(json.dumps(response) + "\n")
                    out.flush()
        finally:
            self.service.stop()

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming JSON-RPC request and return response."""
        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                    },
                    "serverInfo": {
                        "name": "macos-workflow-mcp",
                        "version": "1.0.0",
                    },
                },
            }

        elif method in ("notifications/initialized", "initialized"):
            return None

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS_SCHEMA,
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {}) or {}
            return self._handle_tool_call(msg_id, tool_name, tool_args)

        else:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            return None

    def _handle_tool_call(self, msg_id: Any, tool_name: Optional[str], args: Dict[str, Any]) -> Dict[str, Any]:
        tools_map = {
            "get_current_focus": lambda a: self.service.get_current_focus(),
            "get_running_apps": lambda a: self.service.get_running_apps(),
            "get_activity_summary": lambda a: self.service.get_activity_summary(
                since_minutes=int(a.get("since_minutes", 60)),
                limit=int(a.get("limit", 15)),
            ),
            "get_recent_activity": lambda a: self.service.get_recent_activity(
                limit=int(a.get("limit", 30))
            ),
            "list_task_files": lambda a: self.service.list_task_files(),
            "list_tasks": lambda a: self.service.list_tasks(
                file_path=str(a.get("file_path", "")),
                status=str(a.get("status", "all")),
                section=str(a.get("section", "")),
                tag=str(a.get("tag", "")),
            ),
            "add_task": lambda a: self.service.add_task(
                task_text=str(a.get("task_text", "")),
                file_path=str(a.get("file_path", "")),
                section=str(a.get("section", "")),
            ),
            "update_task_status": lambda a: self.service.update_task_status(
                task_identifier=str(a.get("task_identifier", "")),
                completed=bool(a.get("completed", True)),
                file_path=str(a.get("file_path", "")),
            ),
            "delete_task": lambda a: self.service.delete_task(
                task_identifier=str(a.get("task_identifier", "")),
                file_path=str(a.get("file_path", "")),
            ),
            "get_task_summary": lambda a: self.service.get_task_summary(
                file_path=str(a.get("file_path", ""))
            ),
        }

        if not tool_name or tool_name not in tools_map:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}",
                },
            }

        try:
            res = tools_map[tool_name](args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res, indent=2, default=str),
                        }
                    ],
                    "isError": False,
                },
            }
        except Exception as e:
            logger.exception(f"Error executing tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: {type(e).__name__}: {str(e)}",
                        }
                    ],
                    "isError": True,
                },
            }

    def _send_error(self, msg_id: Any, code: int, message: str, out_stream: Optional[Any] = None) -> None:
        out = out_stream if out_stream is not None else sys.stdout
        err = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        sys.stdout.write(json.dumps(err) + "\n")
        sys.stdout.flush()


def create_fastmcp_server(service: Optional[WorkflowService] = None) -> Any:
    """Create and configure FastMCP server instance if mcp is installed."""
    if not HAS_FASTMCP:
        raise ImportError("The 'mcp' package is not installed. Use StdioMcpServer instead.")

    service = service if service is not None else WorkflowService()
    mcp = FastMCP("macos-workflow-mcp")

    @mcp.tool()
    def get_current_focus() -> Dict[str, str]:
        """Get the currently active frontmost macOS application, window title, and bundle identifier."""
        return service.get_current_focus()

    @mcp.tool()
    def get_running_apps() -> List[str]:
        """List names of all currently running visible GUI applications on macOS."""
        return service.get_running_apps()

    @mcp.tool()
    def get_activity_summary(since_minutes: int = 60, limit: int = 15) -> List[Dict[str, Any]]:
        """Get summary of time spent per application over the last N minutes."""
        return service.get_activity_summary(since_minutes=since_minutes, limit=limit)

    @mcp.tool()
    def get_recent_activity(limit: int = 30) -> List[Dict[str, Any]]:
        """Get chronological log of recent application and window focus changes."""
        return service.get_recent_activity(limit=limit)

    @mcp.tool()
    def list_task_files() -> List[str]:
        """List all markdown files available in the configured task directory."""
        return service.list_task_files()

    @mcp.tool()
    def list_tasks(
        file_path: str = "",
        status: str = "all",
        section: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        """List tasks from a local Markdown task file or Obsidian vault."""
        return service.list_tasks(file_path=file_path, status=status, section=section, tag=tag)

    @mcp.tool()
    def add_task(
        task_text: str,
        file_path: str = "",
        section: str = "",
    ) -> Dict[str, Any]:
        """Add a new task to the markdown task file."""
        return service.add_task(task_text=task_text, file_path=file_path, section=section)

    @mcp.tool()
    def update_task_status(
        task_identifier: str,
        completed: bool = True,
        file_path: str = "",
    ) -> Dict[str, Any]:
        """Toggle task completion status between [ ] and [x]."""
        return service.update_task_status(
            task_identifier=task_identifier,
            completed=completed,
            file_path=file_path,
        )

    @mcp.tool()
    def delete_task(
        task_identifier: str,
        file_path: str = "",
    ) -> Dict[str, Any]:
        """Delete a task from the markdown task file."""
        return service.delete_task(task_identifier=task_identifier, file_path=file_path)

    @mcp.tool()
    def get_task_summary(file_path: str = "") -> Dict[str, Any]:
        """Get summary metrics for tasks (total, open, completed, section breakdown)."""
        return service.get_task_summary(file_path=file_path)

    return mcp


def run_server() -> None:
    """Start standard stdio MCP server."""
    server = StdioMcpServer()
    server.run()
