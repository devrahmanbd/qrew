# macOS Workflow & Task Monitoring MCP Server

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that monitors active macOS window/application focus, logs historical productivity data to a local SQLite database, and provides full inspection and editing capabilities for local Markdown-based task lists (`todo.md` / `tasks.md`).

Designed for AI clients such as **Claude Desktop**, **Cursor**, **Zed**, and custom MCP agent environments.

---

## Architecture Overview

```
                        ┌──────────────────────────────────────────────┐
                        │                  macOS Host                  │
                        │                                              │
                        │  ┌───────────────────────┐                   │
                        │  │   Background Daemon   │                   │
                        │  │  (launchd / thread)   │                   │
                        │  └──────────┬────────────┘                   │
                        │             │ writes                         │
                        │             ▼                                │
                        │      [SQLite Database]                       │
                        │      ~/.macos_workflow_mcp/activity.db       │
                        │             ▲                                │
                        │             │ reads                          │
                        │  ┌──────────┴───────────────┐                │
                        │  │        MCP Server        │                │
                        │  │   (Stdio / FastMCP)      │                │
                        │  └──────────┬───────────────┘                │
                        │             │ reads/writes                   │
                        │             ▼                                │
                        │     [Markdown Tasks]                         │
                        │     ~/todo.md, tasks.md                      │
                        └─────────────┼────────────────────────────────┘
                                      │ stdio JSON-RPC 2.0
                                      ▼
                               [AI MCP Client]
                       (Claude Desktop, Cursor, Agent)
```

### Key Components

1. **Activity Tracker (`macos_workflow_mcp.activity_tracker`)**:
   - Queries macOS frontmost application, active window title, and bundle identifier via native AppleScript (`osascript`, `System Events`).
   - Graceful fallback and mock support for non-Darwin environments.
   - Includes `ActivityMonitorDaemon` for background polling (default every 3 seconds) and automatic session flushing.
2. **Activity Database (`macos_workflow_mcp.db`)**:
   - Local SQLite database stored in `~/.macos_workflow_mcp/activity.db`.
   - Aggregates focus time, percentages, event counts, and sample window titles across configurable lookback windows.
3. **Markdown Task Manager (`macos_workflow_mcp.task_manager`)**:
   - Parses, lists, filters, appends, updates (`[ ]` <-> `[x]`), and deletes markdown tasks while preserving indentation, bullet styling, and section headers.
   - Supports tags (`#urgent`, `@work`) and section categorization (`## Inbox`, `## Sprint`).
4. **MCP Server Core (`macos_workflow_mcp.server`)**:
   - Standards-compliant MCP server communicating via JSON-RPC 2.0 on standard I/O (`stdio`).
   - Seamless dual-mode execution: runs natively with standard Python library (`StdioMcpServer`) or automatically harnesses `FastMCP` when `mcp` is installed.
   - Optionally spawns the background monitoring daemon automatically when the server starts.
5. **CLI Runner & Entrypoints (`macos_workflow_mcp.__main__`, `daemon_runner`)**:
   - Command-line utilities for running the MCP server, starting the background daemon, checking active focus in the terminal, inspecting productivity summaries, or managing tasks.

---

## Exposed MCP Tools

The server registers 10 tools conforming to the MCP tool specification:

| Tool | Parameters | Description |
|---|---|---|
| `get_current_focus` | None | Returns active app name, frontmost window title, and bundle ID. |
| `get_running_apps` | None | Returns list of names of all visible running GUI applications. |
| `get_activity_summary` | `since_minutes` (int, default 60), `limit` (int, default 15) | Returns time spent per application, time percentage share, and sample window titles. |
| `get_recent_activity` | `limit` (int, default 30) | Chronological log of recent focus changes (most recent first). |
| `list_task_files` | None | Lists markdown filenames in the configured task directory (empty list when no `DEFAULT_TASK_DIR`). |
| `list_tasks` | `file_path` (str, optional), `status` ('all'/'open'/'completed'), `section` (str, optional), `tag` (str, optional) | Lists parsed markdown tasks matching criteria. |
| `add_task` | `task_text` (str, required), `file_path` (str, optional), `section` (str, default '') | Appends task under specified section or end of file. |
| `update_task_status` | `task_identifier` (str, line number or substring, required), `completed` (bool, default True), `file_path` (str, optional) | Toggles completion checkbox (`- [x]` or `- [ ]`). |
| `delete_task` | `task_identifier` (str, required), `file_path` (str, optional) | Deletes matching task line. |
| `get_task_summary` | `file_path` (str, optional) | Returns task statistics, section breakdown, and top open tasks. |

---

## Installation & Setup

### Requirements
- macOS 12+ (Monterey, Ventura, Sonoma, Sequoia)
- Python 3.9 or higher

### Local Installation

Clone or copy the repository to your local directory:
```bash
git clone <repo-url> macos_workflow_mcp
cd macos_workflow_mcp
pip install -e .
```

*Optional*: If you wish to use the official FastMCP library:
```bash
pip install -e ".[fastmcp]"
```

---

## macOS Permissions Configuration

To capture the active window title and frontmost process name, macOS requires security permissions for the terminal, application, or IDE that runs the server.

1. Open **System Settings** on your Mac.
2. Navigate to **Privacy & Security** > **Accessibility**.
3. Enable your terminal or host application:
   - If using **Claude Desktop**: add `Claude.app` or `Terminal`/`iTerm2` (depending on how Claude was launched).
   - If using **Cursor**: enable `Cursor.app`.
   - If using from terminal: enable `Terminal.app` or `iTerm.app`.
4. Navigate to **Privacy & Security** > **Automation**:
   - Ensure the calling app (e.g. `Terminal`, `Claude`, `Cursor`) is allowed to control **System Events**.

> **Note**: If permissions are missing, `get_current_focus` will still return the frontmost application name, but window titles will be empty or default to the app name.

---

## AI Client Configuration

### Claude Desktop
Edit your Claude Desktop configuration file at:
`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "macos-workflow": {
      "command": "python3",
      "args": [
        "-m",
        "macos_workflow_mcp",
        "server"
      ],
      "env": {
        "DEFAULT_TASK_FILE": "/Users/yourusername/todo.md",
        "ENABLE_ACTIVITY_DAEMON": "1"
      }
    }
  }
}
```

### Cursor
Add to your project root `.cursor/mcp.json` or your global Cursor Settings:

```json
{
  "mcpServers": {
    "macos-workflow": {
      "command": "python3",
      "args": [
        "-m",
        "macos_workflow_mcp",
        "server"
      ],
      "env": {
        "DEFAULT_TASK_FILE": "/Users/yourusername/tasks.md"
      }
    }
  }
}
```

---

## Running the Background Activity Daemon

The activity daemon polls active focus every 3 seconds (configurable) and records switches and duration to SQLite.

### 1. Manual Terminal Run
```bash
python3 -m macos_workflow_mcp daemon --poll-interval 3.0 -v
```

### 2. Standalone launchd Agent (Auto-start on Login)
To have macOS automatically run the activity monitor in the background upon login, create a launch agent file at `~/Library/LaunchAgents/com.user.macos-workflow-daemon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.macos-workflow-daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>macos_workflow_mcp.daemon_runner</string>
        <string>--poll-interval</string>
        <string>3.0</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/macos_workflow_daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/macos_workflow_daemon.err</string>
</dict>
</plist>
```

Load and start the agent:
```bash
launchctl load ~/Library/LaunchAgents/com.user.macos-workflow-daemon.plist
launchctl start com.user.macos-workflow-daemon
```

To stop or unload:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.macos-workflow-daemon.plist
```

---

## CLI Utilities

You can use the CLI directly for quick terminal lookups and task management:

```bash
# Print current frontmost app and window title
macos-workflow-mcp focus

# Print output as JSON
macos-workflow-mcp focus --json

# View activity summary for the past 2 hours
macos-workflow-mcp summary --minutes 120 --limit 10

# List all open tasks in ~/todo.md
macos-workflow-mcp tasks --status open

# List tasks matching a specific tag or section
macos-workflow-mcp tasks --tag "#urgent" --section "Sprint"
```

---

## Testing

Run the full automated test suite:
```bash
python3 -m unittest discover -s macos_workflow_mcp -p "test_*.py"
```
