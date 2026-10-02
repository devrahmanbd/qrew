"""
CLI Entrypoint for macOS Workflow & Task Monitoring MCP Server.
Provides subcommands: server, daemon, focus, summary, tasks.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional

from .activity_tracker import get_current_focus, set_mock_focus
from .db import ActivityDB
from .server import run_server
from .daemon_runner import run_daemon
from .task_manager import MarkdownTaskManager
from .server import resolve_default_task_file

logger = logging.getLogger("macos_workflow_mcp")


def cmd_server(args: argparse.Namespace) -> None:
    """Run MCP server on stdio."""
    enable_daemon = not args.no_daemon
    run_server(
        db_path=args.db_path,
        task_file=args.task_file,
        enable_daemon=enable_daemon,
        poll_interval=args.poll_interval,
        use_fastmcp=args.use_fastmcp,
    )


def cmd_daemon(args: argparse.Namespace) -> None:
    """Run background monitoring daemon."""
    run_daemon(
        poll_interval=args.poll_interval,
        db_path=args.db_path,
        min_duration=args.min_duration,
        verbose=args.verbose,
    )


def cmd_focus(args: argparse.Namespace) -> None:
    """Print current active frontmost app focus."""
    if args.mock:
        focus = get_current_focus(force_mock=True)
    else:
        focus = get_current_focus()

    if args.json:
        print(json.dumps(focus, indent=2))
    else:
        app = focus.get("app_name") or "(none)"
        title = focus.get("window_title") or "(no title)"
        bundle = focus.get("bundle_id") or "(none)"
        print(f"Active App:    {app}")
        print(f"Window Title:  {title}")
        print(f"Bundle ID:     {bundle}")


def cmd_summary(args: argparse.Namespace) -> None:
    """Print recent activity summary."""
    db = ActivityDB(db_path=args.db_path)
    summary = db.get_activity_summary(since_minutes=args.minutes, limit=args.limit)

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print(f"Activity Summary (Past {args.minutes} minutes):")
    if not summary:
        print("  No activity recorded in this time range.")
        return

    sep = "-" * 80
    print(sep)
    print(f"{'Application':<25} {'Duration':<15} {'Share':<10} {'Events':<8} {'Sample Windows'}")
    print(sep)
    for item in summary:
        app = item["app_name"][:23]
        dur = item["formatted_duration"]
        pct = f"{item['percentage']}%"
        evts = str(item["event_count"])
        wins = ", ".join(item.get("sample_window_titles", []))[:30]
        print(f"{app:<25} {dur:<15} {pct:<10} {evts:<8} {wins}")
    print(sep)


def cmd_tasks(args: argparse.Namespace) -> None:
    """List markdown tasks with optional filters."""
    file_path = args.file or resolve_default_task_file()
    tm = MarkdownTaskManager(default_file=file_path)
    try:
        tasks = tm.list_tasks(
            file_path=file_path,
            status=args.status,
            section=args.section,
            tag=args.tag,
        )
    except FileNotFoundError:
        print(f"Task file not found: {file_path}")
        return

    if args.json:
        print(json.dumps(tasks, indent=2))
        return

    print(f"Tasks in {file_path} (Filter: status={args.status}):")
    if not tasks:
        print("  No matching tasks found.")
        return

    sep = "-" * 80
    print(sep)
    for t in tasks:
        status_box = "[x]" if t["completed"] else "[ ]"
        line_no = f"L{t['line_number']:<4}"
        tags_str = (" " + " ".join(t.get("tags", []))) if t.get("tags") else ""
        section = f" [{t['section']}]" if t.get("section") else ""
        print(f"{status_box} {line_no} {t['text']}{tags_str}{section}")
    print(sep)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macos-workflow-mcp",
        description="macOS Workflow & Task Monitoring MCP Server and CLI tools.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Subcommand: server
    p_server = subparsers.add_parser("server", help="Run the MCP server over stdio.")
    p_server.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path.")
    p_server.add_argument("--task-file", type=str, default=None, help="Default markdown task file path.")
    p_server.add_argument("--no-daemon", action="store_true", help="Disable background activity monitoring thread.")
    p_server.add_argument("--poll-interval", type=float, default=3.0, help="Activity poll interval in seconds.")
    p_server.add_argument("--use-fastmcp", action="store_true", help="Force using FastMCP if installed.")

    # Subcommand: daemon
    p_daemon = subparsers.add_parser("daemon", help="Run standalone background activity monitor daemon.")
    p_daemon.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval in seconds.")
    p_daemon.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path.")
    p_daemon.add_argument("--min-duration", type=float, default=0.5, help="Minimum focus duration threshold.")
    p_daemon.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging.")

    # Subcommand: focus
    p_focus = subparsers.add_parser("focus", help="Print active frontmost macOS app & window.")
    p_focus.add_argument("--json", action="store_true", help="Output in JSON format.")
    p_focus.add_argument("--mock", action="store_true", help="Force mock output (useful for non-macOS tests).")

    # Subcommand: summary
    p_summary = subparsers.add_parser("summary", help="Print recent application activity summary.")
    p_summary.add_argument("--minutes", type=int, default=60, help="Minutes to look back (default 60).")
    p_summary.add_argument("--limit", type=int, default=15, help="Maximum number of applications to display.")
    p_summary.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path.")
    p_summary.add_argument("--json", action="store_true", help="Output in JSON format.")

    # Subcommand: tasks
    p_tasks = subparsers.add_parser("tasks", help="Inspect and list local Markdown tasks.")
    p_tasks.add_argument("--file", type=str, default=None, help="Path to markdown tasks file.")
    p_tasks.add_argument("--status", type=str, default="all", choices=["all", "open", "completed"], help="Filter by task status.")
    p_tasks.add_argument("--section", type=str, default=None, help="Filter by section header substring.")
    p_tasks.add_argument("--tag", type=str, default=None, help="Filter by tag (e.g. #urgent).")
    p_tasks.add_argument("--json", action="store_true", help="Output in JSON format.")

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        run_server()
        return

    cmd_handlers = {
        "server": cmd_server,
        "daemon": cmd_daemon,
        "focus": cmd_focus,
        "summary": cmd_summary,
        "tasks": cmd_tasks,
    }

    handler = cmd_handlers.get(args.subcommand)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
