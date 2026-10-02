# Autonomous Workflow & Intellect Sync (Obsidian Plugin)

Native Obsidian integration plugin connecting your vault directly to your 24/7 autonomous daemon.

## Features
- **Live Focus Status Bar**: Shows frontmost application in the Obsidian status bar (`Intellect: <app>` or `Intellect: Offline`). Click it to open the dashboard.
- **Pull Task State for the Active Note**: Manual command fetches `GET /tasks?file_path=<active-file-path>` and shows the task count. It does not push local edits.
- **Control Dashboard Modal**: Open via the `zap` ribbon icon, status-bar click, or command palette to inspect server connection, frontmost app, and window title, with buttons for `Reconcile Active Tasks`, `AI Prioritize Graph`, and `Refresh Focus` (`GET /focus`).
- **AI Task Prioritization**: Analyzes project and entity dependencies using graph prioritization directly on the active note.
- **WebSocket Streaming**: Instant notifications on verified attempts without manual polling.

## Sync tasks and prioritize from the active note

Run `Sync Active File Tasks with Server` to pull the task list for the open file, or `AI Prioritize Tasks in Current File` to rank it. Both act only on the active markdown file and report results with a `Notice`.

## Install the plugin from these files

1. In Obsidian, turn on community plugins under **Settings -> Community plugins** (turn off Safe mode on older versions).
2. Open `<vault>/.obsidian/plugins/` (create it if missing).
3. Create a folder named `obsidian-mcp-workflow` (must match `id` in `manifest.json`).
4. Copy `manifest.json`, `main.js`, and `styles.css` into that folder.
5. In Obsidian, go to **Settings -> Community plugins -> Installed plugins**, reload if needed, and enable **Autonomous Workflow & Intellect Sync**.

## Configure endpoints in plugin settings

Open **Settings -> Autonomous Intellect Settings** after enabling:

- `REST API Server URL` (default `http://localhost:8765`) — base URL for `GET /tasks?file_path=...`, `POST /tasks/prioritize`, `GET /focus`.
- `WebSocket Stream URL` (default `ws://localhost:8765/ws`) — live stream for `focus_changed`, `task_verified`, and `notification` events. Reconnects after 5 seconds when `autoReconnect` is true.
- `Task Folder` (default `Task-List`) — display-only today; sync and prioritize use the active file path, not this folder.

There is no UI toggle for `autoReconnect` (default true) or `enableStatusBar` (default true); both live in `DEFAULT_SETTINGS` in `main.js`.
