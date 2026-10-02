# AGENTS.md — complete_intellect_ecosystem

Polyglot workflow-sync system, no monorepo tooling, no CI, no lint/typecheck config. Five independent components; no shared lockfile.

## Layout (real entrypoints)

- `central_server/` — canonical 24/7 hub: FastAPI REST + WS on `:8765`, SQLite WAL, OpenRouter reasoning agent. Entrypoint `central_server/api.py:app` (`WebSocketHub`, `sync_vault_file`, embedded dashboard at `/`).
- `macos_workflow_mcp/` — standalone stdio MCP server (dual-mode: stdlib `StdioMcpServer` or FastMCP). Entrypoints `server.py:run_server()`, `__main__.py`, `daemon_runner.py`. Do not confuse its `api_server.py` (legacy/local sync API) with `central_server/api.py`.
- `mac_client/` — macOS bridge: `mac_daemon.py` (vault sync + focus streaming + native notifications), `vault_sync.py`, `focus_streamer.py`, `mcp_bridge.py` (proxies tools to central server).
- `android_app/` — native Kotlin (API 26–35), Gradle. `app/src/main/java/com/workflow/stream/`.
- `obsidian_plugin/` (`obsidian-mcp-workflow`) + `chrome_extension/` (MV3, host perms only `localhost:8765`) — thin clients, no build step.

## Commands (run from repo root unless noted)

```bash
# Central server (dev) — package-relative imports require repo root
python3 -m uvicorn central_server.api:app --host 0.0.0.0 --port 8765
# Docker/systemd — run from central_server/ (compose context is .):
cd central_server && docker compose up --build
sudo cp central_server/systemd/workflow-server.service /etc/systemd/system/ && sudo systemctl enable --now workflow-server

# MCP server + tests (macOS 12+, Python >=3.9)
pip install -e .                          # optional FastMCP: pip install -e ".[fastmcp]"
python3 -m macos_workflow_mcp server      # stdio server; also: daemon | focus | summary | tasks
python3 -m unittest discover -s macos_workflow_mcp -p "test_*.py"

# mac_client (needs SERVER_URL pointing at hub)
python3 -m mac_client.mac_daemon
python3 -m unittest mac_client.test_mac_client -v
cp mac_client/com.workflow.macclient.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.workflow.macclient.plist

# Android
cd android_app && ./gradlew assembleDebug   # APK: app/build/outputs/apk/debug/app-debug.apk

# Obsidian: copy obsidian_plugin/ -> <vault>/.obsidian/plugins/obsidian-mcp-workflow/, reload + enable
```

## Env (only config mechanism — no .env loader)

| Var | Default | Used by |
|---|---|---|
| `OPENROUTER_API_KEY` | "" (agent falls back to DAG heuristic, `mode=dag_topological_heuristic`) | `central_server/agent.py` |
| `SERVER_DATA_DIR` | `/tmp/workflow_server/data` (`/app/data` in Docker) | `central_server/db.py` |
| `SERVER_URL` | `http://localhost:8765` | `mac_client`, chrome ext |
| `OBSIDIAN_VAULT_DIR` / `DEFAULT_TASK_DIR` | hardcoded `/Users/rahman/Documents/Obsidian Vault/Task-List` — override on any other machine | `mac_client`, `api_server.py` |
| `DEFAULT_TASK_FILE` | `~/todo.md` then `~/tasks.md` | `macos_workflow_mcp` |
| `ENABLE_ACTIVITY_DAEMON` | enabled unless `0/false/no` | `macos_workflow_mcp/server.py` |

MCP SQLite lives at `~/.macos_workflow_mcp/activity.db`; central SQLite at `$SERVER_DATA_DIR/workflow_central.db` (WAL mode).

## Quirks agents miss

- Always run Python as `python3 -m <pkg>.<module>` from repo root — `central_server.*`, `mac_client.*`, `macos_workflow_mcp.*` use package-relative imports and break as bare scripts.
- macOS-only: focus/window code shells to `osascript`; on non-darwin it returns mock/empty via `set_mock_focus()` — use `--mock` / `force_mock=True` in tests and CI.
- macOS permissions required for real window titles: Privacy → Accessibility + Automation (System Events) for Terminal/Claude/Cursor; without them only app name is returned.
- `vault_sync.py` loop-suppression via `_suppressed_hashes`: `apply_remote_update()` writes + suppresses, `_poll_step()` consumes. Don't "simplify" this or Mac↔server sync loops.
- Task IDs are `task_{abs(hash(text + date_file))}` in `central_server/api.py` — unstable across processes for collision purposes; never assume globally unique, don't re-key.
- Vault merge (`POST /api/sync/vault`) is line-oriented on `- [ ]/[x]` + `## headers`; server-completed wins on conflict, remote-only tasks appended. Keep regexes `TASK_LINE_REGEX`/`HEADER_REGEX` in sync if editing either side.
- `central_server/api.py` uses deprecated `@app.on_event("startup")`; works but don't "fix" without testing agent `start/stop` loop (30s interval, broadcasts `task_reminder` only when top task changes).
- No test runner at root; suites are per-package `unittest`. `test_write.txt`/`test.txt` in `macos_workflow_mcp/` are task-manager fixtures, not docs.
