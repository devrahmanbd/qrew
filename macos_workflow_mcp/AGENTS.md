# AGENTS.md — macos_workflow_mcp (scoped; see repo-root AGENTS.md for shared env/commands)

## Tool truth
- Single source: `TOOLS_SCHEMA` in `/Users/rahman/Downloads/complete_intellect_ecosystem/macos_workflow_mcp/server.py` — exactly 10 tools. `list_task_files` returns `[]` unless `DEFAULT_TASK_DIR` points at a real dir.
- `server.py` imports only `activity_tracker`, `db`, `task_manager`. `ai_engine.py`, `graph_engine.py`, `notifications.py` are reachable only via `api_server.py`, never over MCP stdio.
- `run_server()` takes zero args; `WorkflowService(enable_daemon, poll_interval)` knobs are in-process only.

## Broken / sharp edges
- `python3 -m macos_workflow_mcp server` (with subcommand) crashes: `__main__.cmd_server` forwards `db_path/task_file/poll_interval/use_fastmcp` kwargs that `server.run_server()` does not accept. Bare `python3 -m macos_workflow_mcp` (no subcommand) works; `daemon | focus | summary | tasks` are unaffected.
- `init.py` is a stray file containing `hello` — the real package init is `__init__.py`. Never import `init`.
- `api_server.py` is its own FastAPI app (`/ws`, `/` dashboard) defaulting `DEFAULT_TASK_DIR` to a hardcoded vault path; the launchd plist must target `macos_workflow_mcp.daemon_runner`, not `api_server`.

## Module facts worth knowing
- `activity_tracker.py`: macOS focus via `osascript` + `System Events` only (no JXA). Non-darwin returns mock via `set_mock_focus()` / `set_mock_running_apps()`; `get_current_focus(force_mock=True)` and CLI `--mock` force it.
- `task_manager.py`: bullets `- * +`, tags `[#@][\w-]` (`TAG_REGEX`), section match is case-insensitive substring (`#` stripped). `file_path` accepts `today`, `DD-MMM` (e.g. `17-Sep`), or a path. `add_task` with empty/`Inbox` section auto-targets the `## DD-MMM` date header in dated files. Writes are atomic (temp file + `os.replace`).
- `db.py`: SQLite WAL + `synchronous=NORMAL`, single table `activity_log`. Direct `ActivityDB` defaults differ from the service layer: `get_activity_summary(limit=20)` vs service/CLI `15`; `get_recent_events(limit=50)` vs service `30`.
- `daemon_runner.py` defaults: `--poll-interval 3.0`, `--min-duration 0.5` (sub-second focuses are dropped).
