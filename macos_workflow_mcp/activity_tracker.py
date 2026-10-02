"""macOS Activity Tracker and Focus Detection Module."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .db import ActivityDB

logger = logging.getLogger("macos_workflow_mcp.activity_tracker")

_MOCK_FOCUS: Dict[str, str] = {
    "app_name": "Terminal",
    "window_title": "zsh",
    "bundle_id": "com.apple.Terminal",
}
_MOCK_RUNNING_APPS: List[str] = ["Finder", "Terminal", "Visual Studio Code", "Obsidian"]


def set_mock_focus(app_name: str, window_title: str, bundle_id: str = "") -> None:
    global _MOCK_FOCUS
    _MOCK_FOCUS = {
        "app_name": app_name,
        "window_title": window_title,
        "bundle_id": bundle_id,
    }


def set_mock_running_apps(apps: List[str]) -> None:
    global _MOCK_RUNNING_APPS
    _MOCK_RUNNING_APPS = list(apps)


def get_current_focus(force_mock: bool = False) -> Dict[str, str]:
    """Retrieve currently active application name, window title, and bundle ID on macOS."""
    if force_mock or sys.platform != "darwin":
        return dict(_MOCK_FOCUS)

    script = """
    try
        tell application "System Events"
            set frontProc to first application process whose frontmost is true
            set procName to name of frontProc
            set bundleId to bundle identifier of frontProc
            set winTitle to ""
            try
                set winTitle to name of front window of frontProc
            end try
            return procName & "|||" & winTitle & "|||" & bundleId
        end tell
    on error
        return "Unknown||||||"
    end try
    """
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split("|||")
            return {
                "app_name": parts[0] if len(parts) > 0 else "Unknown",
                "window_title": parts[1] if len(parts) > 1 else "",
                "bundle_id": parts[2] if len(parts) > 2 else "",
            }
    except Exception as e:
        logger.debug(f"Error querying focus via osascript: {e}")

    return {"app_name": "Unknown", "window_title": "", "bundle_id": ""}


def get_running_apps(force_mock: bool = False) -> List[str]:
    """List visible running applications on macOS."""
    if force_mock or sys.platform != "darwin":
        return list(_MOCK_RUNNING_APPS)

    script = """
    tell application "System Events"
        return name of every application process whose visible is true
    end tell
    """
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=4)
        if proc.returncode == 0:
            return [a.strip() for a in proc.stdout.split(",") if a.strip()]
    except Exception as e:
        logger.debug(f"Error getting running apps: {e}")

    return []


class ActivityMonitorDaemon:
    """Background polling loop recording app/window focus duration to SQLite."""

    def __init__(self, db: Optional[ActivityDB] = None, poll_interval: float = 3.0, min_duration_seconds: float = 0.5, focus_fn: Optional[Any] = None) -> None:
        self.focus_fn = focus_fn
        self.min_duration_seconds = min_duration_seconds
        self.db = db if db is not None else ActivityDB()
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_running = False

        self._current_focus: Optional[Dict[str, str]] = None
        self._focus_start_time: float = 0.0

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self.flush()
        self.is_running = False

    def poll_once(self) -> Optional[Dict[str, Any]]:
        new_focus = self.focus_fn() if self.focus_fn is not None else get_current_focus()
        now = time.time()

        if self._current_focus is None:
            self._current_focus = new_focus
            self._focus_start_time = now
            return None

        # Check if focus changed
        if (
            new_focus.get("app_name") != self._current_focus.get("app_name")
            or new_focus.get("window_title") != self._current_focus.get("window_title")
        ):
            duration = now - self._focus_start_time
            evt = None
            if duration >= self.min_duration_seconds:
                evt = {
                    "app_name": self._current_focus.get("app_name", "Unknown"),
                    "window_title": self._current_focus.get("window_title", ""),
                    "bundle_id": self._current_focus.get("bundle_id", ""),
                    "start_time": self._focus_start_time,
                    "end_time": now,
                    "duration_seconds": duration,
                }
                self.db.record_activity(
                    app_name=evt["app_name"],
                    window_title=evt["window_title"],
                    bundle_id=evt["bundle_id"],
                    start_time=evt["start_time"],
                    end_time=evt["end_time"],
                    duration_seconds=evt["duration_seconds"],
                )
            self._current_focus = new_focus
            self._focus_start_time = now
            return evt
        return None

    def flush(self) -> Optional[Dict[str, Any]]:
        if self._current_focus and self._focus_start_time > 0:
            now = time.time()
            duration = now - self._focus_start_time
            evt = None
            if duration >= self.min_duration_seconds:
                evt = {
                    "app_name": self._current_focus.get("app_name", "Unknown"),
                    "window_title": self._current_focus.get("window_title", ""),
                    "bundle_id": self._current_focus.get("bundle_id", ""),
                    "start_time": self._focus_start_time,
                    "end_time": now,
                    "duration_seconds": duration,
                }
                self.db.record_activity(
                    app_name=evt["app_name"],
                    window_title=evt["window_title"],
                    bundle_id=evt["bundle_id"],
                    start_time=evt["start_time"],
                    end_time=evt["end_time"],
                    duration_seconds=evt["duration_seconds"],
                )
            self._focus_start_time = now
            return evt
        return None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            self._stop_event.wait(self.poll_interval)
