# AGENTS.md — obsidian_plugin (`obsidian-mcp-workflow`)

Scope: `/Users/rahman/Downloads/complete_intellect_ecosystem/obsidian_plugin/` only.

## Files / roles

- `main.js` (319 lines, `module.exports = IntellectWorkflowPlugin`): `IntellectWorkflowPlugin` (status bar, ribbon, 3 commands, WS client, `fetchApi`), `IntellectDashboardModal` (connection + focus card, 3 action buttons), `IntellectSettingTab` (3 text fields only).
- `manifest.json`: `id: obsidian-mcp-workflow`, `name: Autonomous Workflow & Intellect Sync`, `minAppVersion 0.15.0`, `isDesktopOnly: false`.
- `styles.css`: `intellect-status-bar/dot/online/offline`, `intellect-card/title/meta-row/btn-row`, `intellect-modal-header`. Class names are referenced literally in `main.js`.
- `README.md`: user-facing install + settings reference. Keep in sync with `DEFAULT_SETTINGS` and endpoints below.

## Endpoints actually hit (all from `main.js`)

- `WS <wsUrl>` default `ws://localhost:8765/ws` (`initWebSocket`): inbound `focus_changed` (accepts `payload.type` or `payload.event`), `task_verified` / `notification` → `Notice`. Reconnect 5s when `autoReconnect` true.
- `GET <serverUrl>/tasks?file_path=<activeFile.path>` (`syncActiveFileTasks`, read-only pull, count-only `Notice`).
- `POST <serverUrl>/tasks/prioritize` body `{file_path}` (`prioritizeCurrentFile`, checks `res.status === 'ok'`).
- `GET <serverUrl>/focus` (dashboard `Refresh Focus` button only).
- `fetchApi` trims trailing `/` from `serverUrl` and sends `Content-Type: application/json`; any non-OK → `Notice`, returns `null`.

## Commands / UI ids

- Commands: `open-intellect-dashboard`, `sync-active-note-tasks`, `prioritize-current-tasks`. Ribbon icon `zap`. Status-bar click opens the same modal.
- Settings keys (`DEFAULT_SETTINGS`): `serverUrl`, `wsUrl`, `defaultTaskFolder: 'Task-List'`, `autoReconnect: true`, `enableStatusBar: true`.

## Install / reload / test

- Folder name under `<vault>/.obsidian/plugins/` must equal manifest `id` (`obsidian-mcp-workflow`), else Obsidian ignores it.
- After copy: enable community plugins, reload (or restart Obsidian), enable the plugin under Installed plugins.
- Smoke test: `Open Intellect Dashboard` with hub up → `Connected (Live WebSocket)`; with hub down → `Disconnected (Offline)`. Check `Ctrl/Cmd+Shift+I` console for WS errors.
- No unit tests in this folder; verify by reading code and reloading in Obsidian.

## Quirks

- Plain CommonJS (`require('obsidian')`), loaded directly by Obsidian — no bundler, no config to update.
- `defaultTaskFolder` is settings-UI-only; sync/prioritize use `workspace.getActiveFile().path`, never this value.
- `enableStatusBar` is read once in `onload`; toggling requires code edit + reload (no settings toggle). Same for `autoReconnect` (no toggle).
- `saveSettings()` closes and reopens the WS on every keystroke in a settings field; `wsUrl` empty string disables WS silently.
- Status bar shows only `app_name` (`Intellect: <app>`); `window_title` appears only inside the modal.
