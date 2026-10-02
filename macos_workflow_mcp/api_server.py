"""
High-Performance Real-Time Synchronization API & WebSocket Server.
Provides bidirectional real-time state synchronization between macOS, Android, and Chrome Extension.
100% self-hosted: zero external notification services or third-party dependencies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .activity_tracker import get_current_focus
from .ai_engine import AITaskReasoningEngine
from .graph_engine import TaskGraphEngine
from .notifications import NotificationBridge
from .task_manager import MarkdownTaskManager

logger = logging.getLogger("macos_workflow_mcp.api_server")

app = FastAPI(title="Workflow Stream Real-Time Sync API", version="1.0.0")

# Enable wide-open CORS for local Web, Mobile Browser, and Chrome Extension access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services initialization
task_dir = os.environ.get("DEFAULT_TASK_DIR", "/Users/rahman/Documents/Obsidian Vault/Task-List")
task_manager = MarkdownTaskManager(task_dir=task_dir)
graph_engine = TaskGraphEngine()
ai_engine = AITaskReasoningEngine()
notifier = NotificationBridge()

# In-memory browser focus cache
current_browser_focus: Dict[str, str] = {"title": "", "url": ""}


class WebSocketConnectionManager:
    """Manages active WebSockets across macOS, Android mobile clients, and Chrome Extension."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self.active_connections)

        for connection in targets:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.debug(f"Failed to send to client ({e}), removing.")
                await self.disconnect(connection)


ws_manager = WebSocketConnectionManager()
# Link notifier directly to WebSocket broadcasting for instant in-system mobile & web alerts
notifier.set_ws_broadcast_callback(ws_manager.broadcast)


# --- Pydantic Request Models ---

class TaskCreateRequest(BaseModel):
    text: str
    file_path: Optional[str] = ""
    section: Optional[str] = ""


class TaskUpdateRequest(BaseModel):
    completed: bool = True
    file_path: Optional[str] = ""


class BrowserFocusRequest(BaseModel):
    title: str
    url: str


class ReminderRequest(BaseModel):
    task_identifier: str
    reason: Optional[str] = "Upcoming priority"
    channel: Optional[str] = "all"
    file_path: Optional[str] = ""


# --- REST API Endpoints ---

@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "online",
        "active_sync_clients": len(ws_manager.active_connections),
        "task_dir": task_dir,
    }


@app.get("/api/tasks")
async def get_tasks(
    file_path: str = "",
    status: str = "all",
    section: str = "",
    tag: str = "",
) -> Dict[str, Any]:
    try:
        tasks = task_manager.list_tasks(
            file_path=file_path or None,
            status=status,
            section=section or None,
            tag=tag or None,
        )
        summary = task_manager.get_task_summary(file_path=file_path or None)
        return {"tasks": tasks, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks/files")
async def get_task_files() -> List[str]:
    return task_manager.list_task_files()


@app.post("/api/tasks")
async def add_task(req: TaskCreateRequest) -> Dict[str, Any]:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Task text cannot be empty.")
    try:
        task = task_manager.add_task(
            file_path=req.file_path or None,
            task_text=req.text,
            section=req.section or None,
        )
        # Broadcast real-time update to Android & Chrome Extension
        await ws_manager.broadcast({"event": "task_added", "task": task})
        return task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/tasks/{task_identifier}")
async def update_task_status(task_identifier: str, req: TaskUpdateRequest) -> Dict[str, Any]:
    try:
        updated = task_manager.update_task_status(
            file_path=req.file_path or None,
            task_identifier=task_identifier,
            completed=req.completed,
        )
        # Broadcast real-time update
        await ws_manager.broadcast({"event": "task_updated", "task": updated})
        return updated
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/tasks/{task_identifier}")
async def delete_task(task_identifier: str, file_path: str = "") -> Dict[str, Any]:
    try:
        deleted = task_manager.delete_task(
            file_path=file_path or None,
            task_identifier=task_identifier,
        )
        await ws_manager.broadcast({"event": "task_deleted", "task": deleted})
        return deleted
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/tasks/prioritize")
async def prioritize_tasks(file_path: str = "") -> Dict[str, Any]:
    try:
        tasks = task_manager.list_tasks(file_path=file_path or None)
        sys_focus = get_current_focus()
        combined_focus = {
            "app_name": sys_focus.get("app_name", "Desktop"),
            "window_title": current_browser_focus.get("title") or sys_focus.get("window_title", ""),
            "url": current_browser_focus.get("url", ""),
        }

        rezoning = ai_engine.reason_next_action(tasks, combined_focus)
        suggested = rezoning.get("suggested_task") or {}
        immediate = suggested.get("text") if isinstance(suggested, dict) else str(suggested)
        return {
            "immediate_focus": immediate,
            "rezoning_suggestion": rezoning.get("reasoning", "Topological priority"),
            "ranked_tasks": rezoning.get("actionable_tasks", []),
            "clusters": rezoning.get("clusters", {}),
            "mode": rezoning.get("mode", "fallback"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/remind")
async def trigger_reminder(req: ReminderRequest) -> Dict[str, Any]:
    try:
        tasks = task_manager.list_tasks(file_path=req.file_path or None)
        matching = [t for t in tasks if req.task_identifier.lower() in t.get("text", "").lower()]
        target_task = matching[0] if matching else {"text": req.task_identifier, "section": "Obsidian Tasks"}
        
        result = notifier.remind_task(
            task=target_task,
            reason=req.reason or "Upcoming focus item",
            channel=req.channel or "all",
        )
        return {"status": "dispatched", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/focus/current")
async def get_focus() -> Dict[str, Any]:
    sys_focus = get_current_focus()
    return {
        "macos": sys_focus,
        "browser": current_browser_focus,
    }


@app.post("/api/focus/browser_tab")
async def update_browser_tab(req: BrowserFocusRequest) -> Dict[str, Any]:
    current_browser_focus["title"] = req.title
    current_browser_focus["url"] = req.url

    # Broadcast focus update to other connected clients
    await ws_manager.broadcast({
        "event": "focus_changed",
        "browser_tab": current_browser_focus,
    })
    return {"status": "updated", "browser_focus": current_browser_focus}


# --- Real-Time WebSocket Channel ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)

    # Send initial snapshot upon connection
    try:
        tasks = task_manager.list_tasks()
        await websocket.send_text(json.dumps({
            "event": "initial_state",
            "tasks": tasks,
            "browser_focus": current_browser_focus,
        }))
    except Exception:
        pass

    try:
        while True:
            raw = await websocket.receive_text()
            if not raw:
                continue
            data = json.loads(raw)
            action = data.get("action")

            if action == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))

            elif action == "toggle_task":
                task_id = data.get("task_identifier")
                completed = bool(data.get("completed", True))
                f_path = data.get("file_path") or None
                updated = task_manager.update_task_status(f_path, task_id, completed)
                await ws_manager.broadcast({"event": "task_updated", "task": updated})

            elif action == "add_task":
                text = data.get("text", "")
                f_path = data.get("file_path") or None
                sec = data.get("section") or None
                if text.strip():
                    task = task_manager.add_task(f_path, text, sec)
                    await ws_manager.broadcast({"event": "task_added", "task": task})

            elif action == "report_focus":
                current_browser_focus["title"] = data.get("title", "")
                current_browser_focus["url"] = data.get("url", "")
                await ws_manager.broadcast({"event": "focus_changed", "browser_tab": current_browser_focus})

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        await ws_manager.disconnect(websocket)


# --- Embedded Web App for Mobile (Android) & Desktop Browser ---

@app.get("/", response_class=HTMLResponse)
async def web_dashboard() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="theme-color" content="#0d1117">
  <title>Workflow Stream • Real-Time Sync</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #f0f6fc;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --green: #238636;
      --green-glow: #2ea043;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
      padding: 16px;
      max-width: 680px;
      margin: 0 auto;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 16px;
    }
    h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.5px; }
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .status-pill {
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(46, 160, 67, 0.15);
      color: #3fb950;
      border: 1px solid rgba(46, 160, 67, 0.3);
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #3fb950; }
    .status-pill.offline {
      background: rgba(248, 81, 73, 0.15);
      color: #f85149;
      border-color: rgba(248, 81, 73, 0.3);
    }
    .status-pill.offline .status-dot { background: #f85149; }
    .bell-btn {
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text-muted);
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 0.75rem;
      cursor: pointer;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .bell-btn.enabled { color: var(--accent); border-color: rgba(88, 166, 255, 0.4); }
    .focus-card {
      background: linear-gradient(135deg, rgba(88, 166, 255, 0.08), rgba(35, 134, 54, 0.05));
      border: 1px solid rgba(88, 166, 255, 0.25);
      border-radius: 12px;
      padding: 14px 16px;
      margin-bottom: 18px;
    }
    .focus-label { font-size: 0.75rem; text-transform: uppercase; color: var(--accent); font-weight: 700; letter-spacing: 0.5px; }
    .focus-title { font-size: 1.05rem; font-weight: 600; margin-top: 4px; }
    .focus-desc { font-size: 0.8rem; color: var(--text-muted); margin-top: 4px; }
    .section-title { font-size: 0.9rem; color: var(--text-muted); font-weight: 600; margin-bottom: 10px; }
    .task-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
    .task-item {
      display: flex;
      align-items: center;
      gap: 12px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      transition: all 0.15s ease;
    }
    .task-item.completed { opacity: 0.55; }
    .task-item.completed .task-text { text-decoration: line-through; color: var(--text-muted); }
    .checkbox {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      border: 2px solid var(--border);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s ease;
      flex-shrink: 0;
    }
    .checkbox.checked {
      background: var(--green);
      border-color: var(--green);
    }
    .checkbox.checked::after {
      content: '✓';
      color: white;
      font-size: 14px;
      font-weight: 800;
    }
    .task-text { flex: 1; font-size: 0.95rem; font-weight: 500; }
    .task-tag { font-size: 0.7rem; padding: 2px 6px; background: rgba(139, 148, 158, 0.2); border-radius: 4px; color: var(--text-muted); }
    .input-bar {
      margin-top: 20px;
      display: flex;
      gap: 8px;
    }
    input[type="text"] {
      flex: 1;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 16px;
      color: var(--text);
      font-size: 0.95rem;
      outline: none;
    }
    input[type="text"]:focus { border-color: var(--accent); }
    button.add-btn {
      background: var(--green);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 0 18px;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.95rem;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Workflow Stream</h1>
      <span style="font-size: 0.78rem; color: var(--text-muted);" id="dateHeader">Syncing with Obsidian...</span>
    </div>
    <div class="header-actions">
      <button class="bell-btn" id="notifBtn">🔔 Alerts Off</button>
      <div class="status-pill" id="statusPill">
        <span class="status-dot"></span>
        <span id="statusText">Connecting</span>
      </div>
    </div>
  </header>

  <div class="focus-card">
    <div class="focus-label">Top Topological Priority (AI Directed)</div>
    <div class="focus-title" id="focusTitle">Loading priority roadmap...</div>
    <div class="focus-desc" id="focusDesc">Evaluating task dependencies...</div>
  </div>

  <div class="section-title">ACTIVE TASKS</div>
  <ul class="task-list" id="taskList"></ul>

  <div class="input-bar">
    <input type="text" id="newTaskInput" placeholder="Add task to today's note (e.g. Framique test)..." />
    <button class="add-btn" id="addBtn">Add</button>
  </div>

  <script>
    let ws;
    const taskList = document.getElementById('taskList');
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');
    const focusTitle = document.getElementById('focusTitle');
    const focusDesc = document.getElementById('focusDesc');
    const newTaskInput = document.getElementById('newTaskInput');
    const addBtn = document.getElementById('addBtn');
    const dateHeader = document.getElementById('dateHeader');
    const notifBtn = document.getElementById('notifBtn');

    // Self-hosted HTML5 notification setup
    function updateNotifBtn() {
      if ('Notification' in window && Notification.permission === 'granted') {
        notifBtn.textContent = '🔔 Alerts Live';
        notifBtn.className = 'bell-btn enabled';
      } else {
        notifBtn.textContent = '🔔 Enable Alerts';
        notifBtn.className = 'bell-btn';
      }
    }
    notifBtn.onclick = async () => {
      if ('Notification' in window) {
        const perm = await Notification.requestPermission();
        updateNotifBtn();
        if (perm === 'granted') {
          new Notification('Workflow Stream', { body: 'Local native notifications enabled!' });
        }
      }
    };
    updateNotifBtn();

    function playAlertChime() {
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
        osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.15); // A5
        gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.25);
      } catch (e) {}
    }

    function triggerNativeAlert(title, message) {
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
      playAlertChime();
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
          body: message,
          tag: 'workflow-reminder',
        });
      }
    }

    function connectWs() {
      const loc = window.location;
      const wsUri = (loc.protocol === 'https:' ? 'wss://' : 'ws://') + loc.host + '/ws';
      ws = new WebSocket(wsUri);

      ws.onopen = () => {
        statusPill.className = 'status-pill';
        statusText.textContent = 'Live Sync';
        fetchPriorities();
      };

      ws.onclose = () => {
        statusPill.className = 'status-pill offline';
        statusText.textContent = 'Offline';
        setTimeout(connectWs, 2000);
      };

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.event === 'initial_state') {
          renderTasks(data.tasks);
        } else if (data.event === 'task_updated' || data.event === 'task_added' || data.event === 'task_deleted') {
          fetchTasks();
          fetchPriorities();
        } else if (data.event === 'task_reminder') {
          triggerNativeAlert(data.title, data.message);
        }
      };
    }

    async function fetchTasks() {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      renderTasks(data.tasks);
      if (data.summary && data.summary.file) {
        dateHeader.textContent = 'Obsidian Vault • ' + data.summary.file;
      }
    }

    async function fetchPriorities() {
      try {
        const res = await fetch('/api/tasks/prioritize');
        const data = await res.json();
        if (data.immediate_focus) {
          focusTitle.textContent = data.immediate_focus;
          focusDesc.textContent = data.rezoning_suggestion;
        }
      } catch (err) {
        console.log('Priority fetch error', err);
      }
    }

    function renderTasks(tasks) {
      taskList.innerHTML = '';
      tasks.forEach(t => {
        const li = document.createElement('li');
        li.className = 'task-item' + (t.completed ? ' completed' : '');

        const cb = document.createElement('div');
        cb.className = 'checkbox' + (t.completed ? ' checked' : '');
        cb.onclick = () => toggleTask(t.line_number, !t.completed);

        const txt = document.createElement('div');
        txt.className = 'task-text';
        txt.textContent = t.text;

        li.appendChild(cb);
        li.appendChild(txt);
        if (t.section) {
          const sec = document.createElement('span');
          sec.className = 'task-tag';
          sec.textContent = t.section.replace(/^#+\\s*/, '');
          li.appendChild(sec);
        }
        taskList.appendChild(li);
      });
    }

    function toggleTask(lineNo, completed) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          action: 'toggle_task',
          task_identifier: lineNo,
          completed: completed
        }));
      }
    }

    function addTask() {
      const text = newTaskInput.value.trim();
      if (!text) return;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          action: 'add_task',
          text: text
        }));
        newTaskInput.value = '';
      }
    }

    addBtn.onclick = addTask;
    newTaskInput.onkeydown = (e) => { if (e.key === 'Enter') addTask(); };

    connectWs();
    fetchTasks();
  </script>
</body>
</html>
"""
