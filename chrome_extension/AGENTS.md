# AGENTS.md — chrome_extension (scoped)

Thin companion popup + service worker for the hub on `:8765`. Edit files in place; reload in `chrome://extensions`.

## Files / roles

* `manifest.json` — MV3 config: `service_worker` = `background.js`, `action.default_popup` = `popup.html`, icons `16/48/128`.
* `background.js` — WS client + tab listeners + badge + `chrome.storage.local` cache + keepalive alarm. Constants: `WS_URL = ws://localhost:8765/ws`, `HTTP_URL = http://localhost:8765`.
* `popup.html` / `popup.js` / `popup.css` — popup UI (380×520 shell). Optimistic toggle/add, then persists to storage, then `chrome.runtime.sendMessage` to background.
* `icons/icon{16,48,128}.png` — action + store icons referenced by manifest.

## Load-and-test flow

* Hub must be up on `:8765` first; popup status pill shows **Live** / **Offline**.
* `chrome://extensions` → **Developer mode** → **Load unpacked** → select `chrome_extension/` → pin **Workflow Stream**.
* Debug background: same page → **Service Worker** link (console for `[Workflow Stream]` logs). Debug popup: open popup → right-click → **Inspect**.
* After any edit: `chrome://extensions` → reload icon on the extension entry, then reopen popup. Refresh button in popup sends `FORCE_SYNC`.

## Hub protocol (exact — verified against `background.js` / `popup.js`)

* Transport: WS `ws://localhost:8765/ws`; when WS is not `OPEN`, `sendSocketMessage` falls back to `POST http://localhost:8765/api/message` with the same JSON (failures silently ignored).
* Background → hub: `browser_focus` (`title`, `url`, `timestamp`), `get_tasks`, `toggle_task` (`task_identifier`, `completed`, `file_path`), `add_task` (`task_text`, `file_path`, `section`).
* Hub → background: `tasks_state` / `task_update` (`tasks`, `date`, `immediate_focus`, `rezoning_nudge`), `badge_update` (`count`), `focus_rezoning` (`immediate_focus`, `rezoning_nudge`).
* Popup ↔ background runtime messages: `TOGGLE_TASK`, `ADD_TASK`, `FORCE_SYNC` → `TASKS_UPDATED`, `FOCUS_UPDATED`, `CONNECTION_STATE`.
* Storage keys: `workflow_tasks`, `workflow_date`, `workflow_connected`, `workflow_immediate_focus`, `workflow_rezoning_nudge`, `workflow_last_sync`.

## Quirks agents miss

* MV3 worker suspends: `workflow_keepalive` alarm (1 min) reconnects the socket and resends the tab; reconnect backoff is `1.5^n` seconds capped at 30 s (`MAX_RECONNECT_DELAY`).
* Tab reporting fires on `tabs.onActivated` + `tabs.onUpdated` (`complete`/`title`), skips `chrome://` and `chrome-extension://`, and drops identical `url`+`title` via `lastSentTab`.
* Host access is exactly 3 entries (`http://localhost:8765/*`, `ws://localhost:8765/*`, `http://127.0.0.1:8765/*`): `https://` or remote-host fetches fail; add a host to `host_permissions` first.
* Badge: open-task count, `#1f6feb`; zero clears the text (`#238636`); disconnect turns it `#6e7681`. `setBadgeTextColor` is wrapped in `.catch` (missing on older Chrome).
* `popup.js` shows 6 hardcoded `DEFAULT_FALLBACK_TASKS` when storage is empty; `file_path` sent on toggle/add is the current date label (e.g. `17-Sep`) with `section: ## <date>` — the hub resolves it, don't re-key.
