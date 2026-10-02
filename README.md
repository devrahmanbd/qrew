# Autonomous Intellect & Cross-Device Workflow Operating System

A 24/7 autonomous intelligence suite, workflow tracker, and task execution engine bridging a central Linux server, macOS workstations, native Android devices, and Obsidian vaults.

---

## 1. Executive Summary & Core Motivation

Personal computing setups are fragmented:
- Your **macOS workstation** cannot stay on 24/7.
- Your **Android device** is not continuously connected or awake.
- Third-party solutions like Google Tasks lack local-first privacy, offline resilience, and deep integration with developer workflows.

This operating system introduces a **24/7 Central Server with an OpenRouter Reasoning Agent** that acts as the persistent brain. It keeps state alive, reconciles tasks across devices, tracks macOS focus when active, receives updates from Android, and executes autonomous workflows with verifiable evidence.

---

## 2. Ideal Reference Projects on GitHub

Our architecture directly synthesizes the cognitive and execution breakthroughs of the leading open-source agent systems:

| Project | Core Paradigm | Architectural Application in Our Operating System |
| :--- | :--- | :--- |
| [**OpenHuman**](https://github.com/tinyhumansai/openhuman) | **Deterministic Memory Tree** | Memory lives as human-readable Markdown inside your Obsidian vault (`Knowledge/`), rolling up daily execution into entity dossiers. |
| [**LifeOS (PAI)**](https://github.com/danielmiessler/LifeOS) | **Goal Teleology & Ideal State** | Tasks are continuously evaluated and scheduled based on their unblocking power across core projects rather than arbitrary weights. |
| [**Bitterbot Desktop**](https://github.com/Bitterbot-AI/bitterbot-desktop) | **Dream Engine & Epistemic Decay** | Idle-hour memory consolidation that prunes ephemeral context, updates confidence on entities, and applies temporal half-lives. |
| [**Memmy Agent**](https://github.com/MemTensor/memmy-agent) | **4-Layer Memory Pyramid** | Distills execution traces: L1 Traces $\rightarrow$ L2 Policies $\rightarrow$ L3 World Model $\rightarrow$ Crystallized Skills (reusable CLI tools). |
| [**Aiden**](https://github.com/taracodlabs/aiden) | **Proof- & Evidence-Based Execution** | Strict lifecycle: `Job -> Attempt -> Tool Effect -> Evidence -> Verdict`. No task is marked complete without deterministic verification. |

---

## 3. Our End Goal

The objective is to establish an **autonomous engineering and research operating system**:

1. **24/7 Persistent Central Server (`central_server/`)**:
   - Runs continuously on your dedicated Linux server with SQLite WAL storage.
   - Embeds an autonomous reasoning agent powered by the **OpenRouter API** to prioritize tasks, unblock dependencies, and execute background operations even when your Mac and phone are disconnected.
   - Provides bi-directional REST and WebSocket synchronization for macOS and Android clients.
2. **Native Android Application (`android_app/`)**:
   - Native Kotlin app for Android (API 26-35) with Material 3 design.
   - Replaces Google Tasks with direct, secure synchronization against your personal server.
   - Uses Android Jetpack WorkManager for reliable background periodic sync and OkHttp WebSockets for real-time focus notifications.
3. **macOS Client Daemon (`mac_client/`)**:
   - Runs via `launchd` LaunchAgent (`com.workflow.macclient.plist`).
   - Streams frontmost application and active window titles to the Central Server.
   - Watches local Obsidian daily task files (`Task-List/*.md`) with `fsevents`/inotify to sync checkbox changes bi-directionally.
4. **Native Obsidian Integration Plugin (`obsidian_plugin/`)**:
   - Native community plugin (`obsidian-mcp-workflow`) providing a live status bar focus indicator, control dashboard modal, and one-click AI graph prioritization.
5. **Standard Model Context Protocol Server (`macos_workflow_mcp/`)**:
   - Standard-compliant MCP server for AI clients (Claude Desktop, Cursor, Zed) with 9 tools for activity queries and task mutations.

---

## 4. System Architecture & Topology

```
             ┌──────────────────────────────────────────────────────────┐
             │                 24/7 CENTRAL SERVER                      │
             │  • FastAPI REST & WebSocket Hub (Port 8765)              │
             │  • OpenRouter API Autonomous Reasoning Agent             │
             │  • SQLite WAL Activity & Task State Machine              │
             │  • Systemd Service / Docker Container                    │
             └─────────────▲──────────────────────────────▲─────────────┘
                           │                              │
         WebSocket / REST  │                              │  WebSocket / REST
         Sync Stream       │                              │  Sync Stream
                           ▼                              ▼
             ┌───────────────────────────┐  ┌───────────────────────────┐
             │      macOS WORKSTATION    │  │       ANDROID PHONE       │
             │  • mac_client Daemon      │  │  • Native Kotlin App      │
             │  • Native Obsidian Plugin │  │  • WorkManager Sync       │
             │  • Local MCP Server       │  │  • Live Focus Dashboard   │
             │  • Focus & Window Tracker │  │  • Offline Task Queue     │
             └───────────────────────────┘  └───────────────────────────┘
```

---

## 5. Ecosystem Components Included in the Archive

1. **`central_server/`**:
   - `api.py`: FastAPI server handling client sync, WebSocket broadcasts, focus updates, and task operations.
   - `agent.py`: 24/7 autonomous workflow agent integrating with the OpenRouter API.
   - `db.py`: SQLite schema and data access layer with WAL mode.
   - `models.py`: Pydantic schemas for tasks, focus events, and device states.
   - `systemd/workflow-server.service`: Production Linux service unit.
   - `Dockerfile` & `docker-compose.yml`: Containerized deployment configs.
2. **`android_app/`**:
   - `app/src/main/java/com/workflow/stream/`: Native Kotlin sources including `MainActivity.kt`, `TaskSyncWorker.kt`, `ApiClient.kt`, and `WebSocketClient.kt`.
   - `app/src/main/res/`: Layouts, drawables, and themes for Material 3.
   - `build.gradle.kts` & `settings.gradle.kts`: Complete Gradle build setup.
3. **`mac_client/`**:
   - `mac_daemon.py`: Unified background manager for macOS.
   - `focus_streamer.py`: Real-time macOS window/app focus streamer.
   - `vault_sync.py`: Obsidian task list file watcher and reconciler.
   - `com.workflow.macclient.plist`: macOS LaunchAgent daemon definition.
4. **`obsidian_plugin/`**:
   - `manifest.json`, `main.js`, `styles.css`: Community plugin providing real-time status bar telemetry, ribbon control modal, and AI prioritization.
5. **`macos_workflow_mcp/`**:
   - Core Python MCP server conforming to the Model Context Protocol specification with full test coverage (40/40 tests passing).
6. **`chrome_extension/`**:
   - Companion browser extension streaming active tab URLs and domains.

---

## 6. Quickstart & Deployment

### Step A: Deploy the Central Server (Linux Dedicated Server)
```bash
cd central_server
pip install -r requirements.txt
export OPENROUTER_API_KEY="your_openrouter_api_key_here"
python3 -m central_server.api --port 8765
```
Or with systemd:
```bash
sudo cp systemd/workflow-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now workflow-server
```

### Step B: Build and Install Android App
```bash
cd android_app
./gradlew assembleDebug
# APK is generated at app/build/outputs/apk/debug/app-debug.apk
```

### Step C: Start macOS Client Daemon
```bash
cd mac_client
pip install -r ../macos_workflow_mcp/requirements.txt
python3 mac_daemon.py --server http://<YOUR_SERVER_IP>:8765
```

### Step D: Install Obsidian Plugin
Copy the `obsidian_plugin/` folder into your Obsidian vault under `.obsidian/plugins/obsidian-mcp-workflow/`, then reload and enable community plugins in Obsidian settings.
