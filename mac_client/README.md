# macOS Client Agent & Local MCP Bridge

The macOS client agent bridges your local Mac desktop environment (Obsidian Vault, active application focus, native Notification Center) with the 24/7 central workflow server.

---

## Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │                         macOS Client                        │
  │                                                             │
  │  ┌──────────────────────┐        ┌───────────────────────┐  │
  │  │  ObsidianVaultSync   │        │ DesktopFocusStreamer  │  │
  │  │(Loop-safe file watch)│        │(osascript window poll)│  │
  │  └──────────┬───────────┘        └───────────┬───────────┘  │
  │             │ Bidirectional                  │ Context      │
  │             ▼                                ▼ Stream       │
  │  ┌───────────────────────────────────────────────────────┐  │
  │  │            MacClientDaemon (mac_daemon.py)            │  │
  │  │   • Manages Vault Sync & Focus Poller                 │  │
  │  │   • Triggers Native macOS Notification Center Banners │  │
  │  └──────────────────────────┬────────────────────────────┘  │
  │                             │                               │
  │                             ▼ HTTP REST / WebSockets        │
  └─────────────────────────────┼───────────────────────────────┘
                                ▼
         [24/7 Central Server: http://localhost:8765]
                                ▲
  ┌─────────────────────────────┼───────────────────────────────┐
  │  ┌──────────────────────────┴────────────────────────────┐  │
  │  │            StdioMcpBridge (mcp_bridge.py)             │  │
  │  │  Proxies tools to 24/7 server over stdio for Claude   │  │
  │  └──────────────────────────▲────────────────────────────┘  │
  │                             │ stdio JSON-RPC 2.0            │
  │  ┌──────────────────────────┴────────────────────────────┐  │
  │  │               Claude Desktop / Cursor                 │  │
  │  └───────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────┘
```

---

## Components

1. **`vault_sync.py` (`ObsidianVaultSync`):**
   * Monitors `/Users/rahman/Documents/Obsidian Vault/Task-List/` for changes in `DD-MMM.md` files (e.g. `17-Sep.md`).
   * When local edits occur, syncs changes to the central server.
   * When remote changes arrive (e.g., checking off a task on Android), applies them atomically without triggering a cyclic sync loop.

2. **`focus_streamer.py` (`DesktopFocusStreamer`):**
   * Detects the frontmost application and window title using native macOS `osascript`.
   * Automatically streams context shifts to the central server so the AI model knows your active focus.

3. **`mac_daemon.py` (`MacClientDaemon`):**
   * Unified background service that coordinates vault synchronization and focus streaming.
   * Dispatches native macOS notifications via AppleScript when the server alerts for a priority task.

4. **`mcp_bridge.py` (`StdioMcpBridge`):**
   * Lightweight stdio MCP server for Claude Desktop and Cursor.
   * Transparently proxies tool calls (`list_tasks`, `add_task`, `update_task_status`, `prioritize_tasks`, etc.) to the central server.

5. **`com.workflow.macclient.plist`:**
   * macOS `launchd` configuration to automatically start `mac_daemon.py` on login.

---

## Configuration & Setup

### 1. Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `SERVER_URL` | `http://localhost:8765` | URL of the central FastAPI workflow server |
| `OBSIDIAN_VAULT_DIR` | `/Users/rahman/Documents/Obsidian Vault/Task-List` | Path to your Obsidian task list vault |

### 2. Configure Claude Desktop / Cursor

Add the MCP bridge to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "workflow-bridge": {
      "command": "python3",
      "args": ["-m", "mac_client.mcp_bridge"],
      "env": {
        "SERVER_URL": "http://localhost:8765"
      }
    }
  }
}
```

### 3. Running the Background Daemon

**Manual Start:**
```bash
python3 -m mac_client.mac_daemon
```

**Auto-Start on Login via `launchd`:**
```bash
cp mac_client/com.workflow.macclient.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.workflow.macclient.plist
```
