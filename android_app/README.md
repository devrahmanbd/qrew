# Workflow Stream • Native Android Application

Native Android client for the distributed real-time workflow and task monitoring system.
Targets **Android 13 through Android 16** (API 33 to 35+).

---

### Features
1. **Real-Time Bidirectional Sync:** Powered by OkHttp WebSockets (`/ws`), synchronizing checkbox state, additions, and deletions with macOS and the local Obsidian vault sub-millisecond.
2. **Topological AI Priority Banner:** Displays the highest priority recommendation derived from graph topology and the Nemotron AI reasoning engine.
3. **Android 13-16 Notification Engine:** Implements high-priority Notification Channels (`workflow_stream_channel`) compatible with Android 13+ `POST_NOTIFICATIONS` runtime permissions.
4. **Battery-Efficient Background Sync (Jetpack WorkManager):** Periodically wakes via `TaskSyncWorker` without draining battery, respecting Android Doze mode.
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
