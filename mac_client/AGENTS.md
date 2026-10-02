# AGENTS.md — mac_client (macOS bridge, stdlib only)

## Entrypoints (absolute paths)

- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/mac_daemon.py` — `MacClientDaemon` (`run()` / `stop()` / `main()`); starts `ObsidianVaultSync.start_watching()` + `DesktopFocusStreamer.start_streaming()`, then 2s loop that calls `_sync_latest_tasks_from_server()` (GET `/api/tasks` → `apply_remote_update`) every 5th iteration (~10s).
- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/vault_sync.py` — `ObsidianVaultSync`; pushes local edits via POST `/api/sync/vault` (`push_file_to_server`), applies server state via `apply_remote_update`.
- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/focus_streamer.py` — `DesktopFocusStreamer`; `get_current_focus()` shells to `OSASCRIPT_QUERY` (returns `app|||bundle|||title`), `stream_focus_to_server()` POSTs `/api/focus/browser_tab` with `{"title": "[app] window", "url": "app://bundle"}`; `_poll_step()` only POSTs when app_name/window_title changes (poll_interval 2.5s).
- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/mcp_bridge.py` — `StdioMcpBridge.run()` (JSON-RPC 2.0 over stdio) + `McpServerProxy.execute_tool()`; exact 7 tools in `TOOLS_SCHEMA`: `list_tasks`→GET `/api/tasks`, `add_task`→POST `/api/tasks`, `update_task_status`→PATCH `/api/tasks/{id}`, `delete_task`→DELETE `/api/tasks/{id}`, `prioritize_tasks`→GET `/api/tasks/prioritize`, `get_current_focus`→GET `/api/focus/current`, `list_task_files`→GET `/api/tasks/files`. Handshake: `initialize` returns protocolVersion `2024-11-05`, serverInfo `workflow-mcp-bridge/1.0.0`; `ping`, `tools/list`, `tools/call` supported.
- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/com.workflow.macclient.plist` — Label `com.workflow.macclient`, `ProgramArguments`=`/usr/bin/python3 -m mac_client.mac_daemon`, `RunAtLoad`+`KeepAlive`, logs at `/Users/rahman/Library/Logs/workflow_macclient_stdout.log` / `..._stderr.log`.
- `/Users/rahman/Downloads/complete_intellect_ecosystem/mac_client/__init__.py` re-exports `ObsidianVaultSync`, `DesktopFocusStreamer`, `MacClientDaemon`, `StdioMcpBridge`, `McpServerProxy`, `TOOLS_SCHEMA`.

## Run / test (cwd must be repo root `/Users/rahman/Downloads/complete_intellect_ecosystem`)

- `python3 -m mac_client.mac_daemon` — manual daemon; `SERVER_URL`/`OBSIDIAN_VAULT_DIR` taken from env, else defaults below.
- `python3 -m mac_client.mcp_bridge` — stdio bridge (same cwd requirement; Claude `claude_desktop_config.json` needs matching `cwd`).
- `python3 -m unittest mac_client.test_mac_client -v` — 3 tests, all offline (verified passing): `test_vault_sync_loop_prevention`, `test_focus_streamer_mock`, `test_mcp_bridge_protocol`.
- launchd: `cp mac_client/com.workflow.macclient.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.workflow.macclient.plist`.

## Env / config specifics (per-file behavior)

- `SERVER_URL` read + `.rstrip("/")` in `mac_daemon.py:42`, `vault_sync.py:46`, `focus_streamer.py:47`, `mcp_bridge.py:22` (module-level `SERVER_URL` constant).
- `OBSIDIAN_VAULT_DIR` read with `os.path.expanduser` in `mac_daemon.py:43-45` and `vault_sync.py:40-45`; plist hardcodes both vars (`plist:17-20`) so launchd ignores shell env.
- Zero third-party deps: `urllib`, `subprocess`, `threading`, `tempfile` only.

## Quirks (do not "fix" these)

- Loop-suppression is two-sided by design: `apply_remote_update()` (`vault_sync.py:113`) adds sha256 to `_suppressed_hashes` under `_lock`; `_poll_step()` (`vault_sync.py:138`) consumes the hash and skips the push. Local edits push via fire-and-forget daemon thread. Removing either side causes Mac↔server sync loops.
- Only `*.md` matching `DATE_FILE_PATTERN = ^(\d{1,2}-[A-Za-z]{3})\.md$` (`vault_sync.py:32`) syncs; other files ignored. `scan_initial_state()` creates the vault dir if missing; writes are atomic (`tempfile` + `os.replace`).
- Non-darwin fallbacks (no `set_mock_focus` needed for these paths): `get_current_focus()` returns `Desktop/com.apple.finder/Workspace`; `show_native_notification()` (`mac_daemon.py:51`) logs and returns `True`. Tests use `set_mock_focus()` (`focus_streamer.py:54`). Real window titles need Accessibility + Automation (System Events) grants.
- Notifications go through `osascript display notification ... sound name "Subtle"` with `"` escaping only; `subprocess.run(..., timeout=5)` failure logs a warning and returns `False` — never raises.
- plist ships with **no `WorkingDirectory` key**: `python3 -m mac_client.mac_daemon` only resolves when cwd (or PYTHONPATH) contains the repo root, so add `WorkingDirectory=/Users/rahman/Downloads/complete_intellect_ecosystem` (or a wrapper that `cd`s there) before relying on launchd auto-start.
