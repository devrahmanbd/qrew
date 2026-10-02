"""
Active Desktop Window Poller and Context Streamer.
Monitors the frontmost macOS application and window title, streaming focus
transitions to the 24/7 central server.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger("mac_client.focus_streamer")


class DesktopFocusStreamer:
    """
    Monitors frontmost application and window title on macOS,
    streaming updates to the central server when focus shifts.
    """

    OSASCRIPT_QUERY = """tell application "System Events"
  set frontApp to first application process whose frontmost is true
  set appName to name of frontApp
  set bundleId to bundle identifier of frontApp
  set winTitle to ""
  try
    tell frontApp
      set winTitle to name of front window
    end tell
  end try
  return appName & "|||" & bundleId & "|||" & winTitle
end tell"""

    def __init__(
        self,
        server_url: Optional[str] = None,
        poll_interval: float = 2.5,
    ) -> None:
        self.server_url = (server_url or os.environ.get("SERVER_URL", "http://localhost:8765")).rstrip("/")
        self.poll_interval = poll_interval
        self._current_focus: Dict[str, str] = {"app_name": "", "bundle_id": "", "window_title": ""}
        self._mock_focus: Optional[Dict[str, str]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_mock_focus(self, app_name: str, window_title: str = "", bundle_id: str = "") -> None:
        """Set mock focus for testing or non-macOS environments."""
        self._mock_focus = {
            "app_name": app_name,
            "window_title": window_title,
            "bundle_id": bundle_id,
        }

    def get_current_focus(self) -> Dict[str, str]:
        """Fetch active application and window title via osascript."""
        if self._mock_focus is not None:
            return dict(self._mock_focus)

        if sys.platform != "darwin":
            return {"app_name": "Desktop", "bundle_id": "com.apple.finder", "window_title": "Workspace"}

        try:
            res = subprocess.run(
                ["osascript", "-e", self.OSASCRIPT_QUERY],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split("|||")
                app_name = parts[0] if len(parts) > 0 else "Unknown"
                bundle_id = parts[1] if len(parts) > 1 else ""
                win_title = parts[2] if len(parts) > 2 else ""
                return {
                    "app_name": app_name,
                    "bundle_id": bundle_id,
                    "window_title": win_title,
                }
        except Exception as e:
            logger.debug(f"Error querying active focus via osascript: {e}")

        return {"app_name": "Unknown", "bundle_id": "", "window_title": ""}

    def stream_focus_to_server(self, focus_data: Dict[str, str]) -> bool:
        """Send active focus snapshot to central server."""
        url = f"{self.server_url}/api/focus/browser_tab"
        payload = json.dumps({
            "title": f"[{focus_data.get('app_name')}] {focus_data.get('window_title')}".strip(),
            "url": f"app://{focus_data.get('bundle_id') or focus_data.get('app_name')}",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.debug(f"Failed to stream focus to server: {e}")
            return False

    def _poll_step(self) -> None:
        """Sample active focus and stream if changed."""
        focus = self.get_current_focus()
        app_name = focus.get("app_name", "")
        win_title = focus.get("window_title", "")

        if (
            app_name != self._current_focus.get("app_name")
            or win_title != self._current_focus.get("window_title")
        ):
            self._current_focus = focus
            logger.info(f"Focus transition: {app_name} — {win_title}")
            threading.Thread(
                target=self.stream_focus_to_server,
                args=(focus,),
                daemon=True,
            ).start()

    def start_streaming(self) -> None:
        """Start polling and streaming in a background thread."""
        if self._running:
            return
        self._running = True

        def _run():
            while self._running:
                try:
                    self._poll_step()
                except Exception as e:
                    logger.debug(f"Focus streamer poll error: {e}")
                time.sleep(self.poll_interval)

        self._thread = threading.Thread(target=_run, daemon=True, name="DesktopFocusStreamer")
        self._thread.start()
        logger.info("DesktopFocusStreamer started.")

    def stop(self) -> None:
        """Stop streamer thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("DesktopFocusStreamer stopped.")
