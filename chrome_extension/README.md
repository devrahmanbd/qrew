# Workflow Stream — Chrome Extension (Manifest V3)

Real-time task synchronization, AI focus rezoning, and browser context tracking for the macOS & Android workflow system.

---

## Features

1. **Active Tab Focus Reporting:**
   * Automatically streams current active browser tab (`title` and `url`) to the local macOS workflow agent (`ws://localhost:8765/ws`).
   * Feeds your browser context into the Nemotron-3 thinking model for instant **work rezoning** recommendations.

2. **Live Task Badge:**
   * Dynamic extension icon badge displaying the count of open tasks (e.g. `5`).
   * When a task is checked off on your Android phone, Mac terminal, or Obsidian vault, the badge updates in real time without clicking.

3. **Linear / Raycast Dark Aesthetic (`popup.html`):**
   * **Top Focus Card:** Displays the highest topological priority item (e.g., `Account Recovery of Flynn, Shaheen(first)`) with a one-click "Complete Now" button.
   * **Animated Task Checkboxes:** Optimistic UI with instant state toggling and background synchronization.
   * **Filter Pills:** Switch between `All`, `Open`, and `Done` with dynamic task counts.
   * **Quick Add Input:** Press `Enter` to append a new task directly under today's Obsidian note (e.g. `## 17-Sep`).

---

## Installation (Load Unpacked)

1. Open Google Chrome (or any Chromium browser: Brave, Arc, Edge).
2. Navigate to `chrome://extensions/`.
3. Enable **Developer mode** toggle in the top-right corner.
4. Click **Load unpacked** in the top-left toolbar.
5. Select the `chrome_extension` folder.
6. The **Workflow Stream** icon will appear in your extensions toolbar. Click the puzzle icon to pin it.

---

## Local Server Communication (Port 8765)

The extension communicates with your local workflow daemon running on macOS:

* **WebSocket Endpoint:** `ws://localhost:8765/ws`
  * Client sends: `{"type": "browser_focus", "title": "GitHub PR", "url": "https://..."}`
  * Client sends: `{"type": "toggle_task", "task_identifier": "Framique", "completed": true}`
  * Client sends: `{"type": "add_task", "task_text": "New task", "file_path": "17-Sep"}`
  * Server sends: `{"type": "tasks_state", "tasks": [...], "immediate_focus": "..."}`
* **REST Fallback:** `http://localhost:8765/api/focus/browser_tab` and `http://localhost:8765/api/tasks`

---

## File Structure

```
chrome_extension/
├── manifest.json       # Manifest V3 configuration & permissions
├── background.js       # Service worker (tab tracking, WebSocket, badge sync)
├── popup.html          # Extension popup markup
├── popup.css           # Modern dark UI stylesheet
├── popup.js            # Frontend logic & optimistic state management
├── icons/              # Dynamic application icons
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md           # Documentation & usage guide
```
