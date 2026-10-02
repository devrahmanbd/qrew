# Autonomous Workflow & Intellect Sync (Obsidian Plugin)

Native Obsidian integration plugin connecting your vault directly to your 24/7 autonomous daemon.

## Features
- **Live Focus Status Bar**: Shows frontmost application and active window title in the Obsidian status bar.
- **Bi-directional Task Synchronization**: Automatically syncs `- [ ]` tasks with the server's state machine.
- **Control Dashboard Modal**: Open via ribbon icon or command palette to inspect server connection, active focus, and trigger immediate task reconciliation.
- **AI Task Prioritization**: Analyzes project and entity dependencies using graph prioritization directly on the active note.
- **WebSocket Streaming**: Instant notifications on verified attempts without manual polling.

## Installation
1. Locate your Obsidian vault directory (e.g. `/Users/rahman/Documents/Obsidian Vault/`).
2. Open `.obsidian/plugins/` (create the directory if it does not exist).
3. Create a folder named `obsidian-mcp-workflow`.
4. Copy `manifest.json`, `main.js`, and `styles.css` into that folder.
5. In Obsidian: Go to **Settings -> Community plugins -> Installed plugins** and enable **Autonomous Workflow & Intellect Sync**.
