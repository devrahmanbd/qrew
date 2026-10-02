# AGENTS.md — android_app ONLY

Scope: `/Users/rahman/Downloads/complete_intellect_ecosystem/android_app/`. Root AGENTS.md covers repo layout/build; not repeated here.

## Entrypoints (all under `app/src/main/java/com/workflow/stream/`)

- `MainActivity.kt` — sole launcher activity (`.MainActivity`, `adjustResize`). Owns `ApiClient` + `WebSocketClient` lifecycle, `ALL/OPEN/DONE` filter, add-task, server-config dialog, `● Live Sync` / `○ Offline` pill. WS events `task_updated/added/deleted` all just call `loadData()` (full REST re-fetch, no diff).
- `network/ApiClient.kt` — OkHttp REST; default `http://10.0.2.2:8765`. `updateBaseUrl()` trims trailing `/`. Timeouts 5s connect / 10s read. Task identity is `line_number` (int), used as `PATCH /api/tasks/{line_number}` path param.
- `network/WebSocketClient.kt` — OkHttp WS, 15s ping. URL built in `MainActivity.initWebSocket` by string-replacing `http→ws` and appending `/ws`. Sends `toggle_task` / `add_task`; handles `task_updated`, `task_added`, `task_deleted`, `task_reminder`, `focus_changed` (reads `browser_tab` object, not `focus`). Reconnects with doubling delay 1s→30s cap; `stop()` must be called (done in `onDestroy`) or handler keeps reconnecting.
- `sync/TaskSyncWorker.kt` — `CoroutineWorker`, work name `workflow_stream_sync_work`, 30-min periodic, `NetworkType.CONNECTED` + battery-not-low, `ExistingPeriodicWorkPolicy.KEEP`, exponential backoff 10 min. Only notifies when `immediate_focus` contains `(first)`; otherwise silent success. Failure → `Result.retry()`.
- `notifications/NotificationHelper.kt` — channel `workflow_stream_channel` (`IMPORTANCE_HIGH`, vibration `0,200,100,200`), single fixed `NOTIFICATION_ID = 1001` (new reminders overwrite the old one). `PendingIntent.FLAG_IMMUTABLE` required.
- `data/TaskItem.kt` — Gson models; `TasksResponse.summary` is `Map<String, Any>?` (untyped — cast, don't retype without checking server). `TaskAdapter.kt` — `ListAdapter` + `DiffUtil` on `(lineNumber, text)`; toggle is optimistic then `notifyDataSetChanged()` plus WS send plus REST PATCH fallback.

## Build/verify (run from `android_app/`)

```bash
./gradlew assembleDebug   # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew lint
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

- No tests exist here (no test deps in `app/build.gradle.kts` despite `testInstrumentationRunner` being set). Don't claim `./gradlew test` passes — there is nothing to run.
- Root `build.gradle.kts` holds only plugin versions (AGP 8.5.2, Kotlin 1.9.24); all config lives in `app/build.gradle.kts` (namespace `com.workflow.stream`, Java 17, `viewBinding = true`, release minify OFF). `settings.gradle.kts` uses `FAIL_ON_PROJECT_REPOS` — declare repos only in `settings`, never in module files.
- `gradlew` is already executable; `proguard-rules.pro` is empty.

## Quirks agents miss

- Server host pref key is `workflow_prefs` → `server_host`; `TaskSyncWorker` reads it independently from `MainActivity` — changing the dialog value affects the next worker run, no restart needed, but the worker constructs its own `ApiClient` (no shared instance).
- `usesCleartextTraffic="true"` is set — plain `http://` LAN IPs work; don't "fix" to HTTPS-only.
- Toggle path is dual-write (WS + REST PATCH) with no dedup; checkbox handler uses `setOnClickListener` + `isChecked`, so programmatic `bind()` re-checks don't refire it — keep that pattern or toggles loop on scroll.
- `focus_changed` payload key is `browser_tab`; `onFocusChanged` only toasts. `task_reminder` is the only event that posts a notification from WS.
- Theme is `Theme.MaterialComponents.DayNight.NoActionBar` (Material Components, not Compose/Material 3) with hardcoded dark colors in `colors.xml`; `viewBinding = true` is enabled in gradle but layouts are still accessed via `findViewById` — don't mix in view-binding refs without converting the activity.
- `POST_NOTIFICATIONS` is requested at runtime only on API 33+ (`checkNotificationPermission`); channel creation itself is API 26+ guarded.
