# Workflow Stream • Native Android Application

Native Android client for the distributed real-time workflow and task monitoring system.
Supports **API 26 through 35** (`minSdk = 26`, `targetSdk = 35`, `compileSdk = 35` per `app/build.gradle.kts`).
`POST_NOTIFICATIONS` runtime permission applies on API 33+ only.

---

### Features
1. **Real-Time Bidirectional Sync:** Powered by OkHttp WebSockets (`/ws`), synchronizing checkbox state, additions, and deletions with macOS and the local Obsidian vault sub-millisecond.
2. **Topological AI Priority Banner:** Displays the highest priority recommendation derived from graph topology and the Nemotron AI reasoning engine.
3. **Android Notification Engine:** High-priority Notification Channel (`workflow_stream_channel`, `NotificationHelper.kt`) with `POST_NOTIFICATIONS` runtime permission on Android 13+ (API 33+).
4. **Battery-Efficient Background Sync (Jetpack WorkManager):** `TaskSyncWorker` runs every 30 min (requires network, battery-not-low), respecting Android Doze mode.
5. **Modern Minimalist Dark UI:** Engineered with Material Components and optimized touch targets.

---

### Build & Installation

#### Option 1: Using Android Studio
1. Open Android Studio.
2. Select **File > Open** and choose this `android_app` directory.
3. Wait for Gradle sync to complete.
4. Select your connected device or emulator and click **Run (Shift + F10)**.

#### Option 2: Using Command Line (Gradle)
```bash
cd android_app
./gradlew assembleDebug
```
The APK will be generated at:
`app/build/outputs/apk/debug/app-debug.apk`

Install on connected Android device via ADB:
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

### Server Connection Configuration
By default, the app connects to `http://10.0.2.2:8765` (standard Android Emulator loopback to host Mac).
When testing on a physical Android phone:
1. Tap the **Settings gear icon (⚙)** in the top right corner.
2. Enter your Mac's local Wi-Fi IP or Tailscale IP (e.g. `http://192.168.1.50:8765`).
3. Tap **Save & Reconnect**.

The host is stored in `SharedPreferences` (`workflow_prefs` → `server_host`) and applied to both REST and WebSocket (scheme rewritten `http→ws` + `/ws` suffix in `MainActivity.initWebSocket`).

| Method | Endpoint | Used by |
|---|---|---|
| `GET` | `/api/tasks` | task list (`ApiClient.getTasks`) |
| `GET` | `/api/tasks/prioritize` | AI priority banner (`ApiClient.getPriorities`) |
| `POST` | `/api/tasks` | add task (`ApiClient.addTask`) |
| `PATCH` | `/api/tasks/{line_number}` | toggle complete (`ApiClient.updateTaskStatus`) |
| WS | `/ws` | live sync (`WebSocketClient`: `toggle_task`, `add_task` sends; `task_updated/added/deleted`, `task_reminder`, `focus_changed` receives) |

---

### Prerequisites

- JDK 17 (required: `sourceCompatibility/targetCompatibility = VERSION_17`, `kotlinOptions.jvmTarget = "17"`)
- Android SDK with API 35 platform installed; `gradlew` is executable in this directory
- Central server reachable (default `http://10.0.2.2:8765` on emulator; LAN/Tailscale IP on device — cleartext HTTP allowed via `android:usesCleartextTraffic="true"` in `AndroidManifest.xml`)

### Project structure

```
app/src/main/
  AndroidManifest.xml                      # INTERNET, POST_NOTIFICATIONS, VIBRATE, WAKE_LOCK
  java/com/workflow/stream/
    MainActivity.kt                        # launcher activity, task list + filter + add + server dialog
    TaskAdapter.kt                         # RecyclerView ListAdapter (optimistic toggle, strikethrough)
    data/TaskItem.kt                       # Gson models: TaskItem, TasksResponse, PrioritizeResponse
    network/ApiClient.kt                   # OkHttp REST client (5s connect / 10s read timeouts)
    network/WebSocketClient.kt             # OkHttp WS, 15s ping, exponential reconnect 1s→30s
    sync/TaskSyncWorker.kt                 # WorkManager periodic sync, notifies on "(first)" focus tasks
    notifications/NotificationHelper.kt    # channel workflow_stream_channel, IMPORTANCE_HIGH
  res/layout/activity_main.xml · item_task.xml
  res/values/themes.xml · colors.xml · strings.xml
build.gradle.kts        # AGP 8.5.2 + Kotlin 1.9.24 (plugin versions only)
app/build.gradle.kts    # namespace com.workflow.stream, deps: OkHttp 4.12.0, Gson 2.11.0, WorkManager 2.9.1, coroutines 1.8.1, lifecycle 2.8.4, material 1.12.0
settings.gradle.kts     # rootProject.name = "WorkflowStream"
```

### Verify

```bash
cd android_app
./gradlew assembleDebug   # also: ./gradlew lint
```

No unit/instrumented tests exist in this module (`app/build.gradle.kts` has no test dependencies).
