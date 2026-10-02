"""
Unified Background Runner for macOS.
Maintains persistent WebSocket connection to 24/7 central server, coordinates
Obsidian vault sync, streams desktop focus, and triggers native Notification Center alerts.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .focus_streamer import DesktopFocusStreamer
from .vault_sync import ObsidianVaultSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mac_client.daemon")


class MacClientDaemon:
    """
    Unified background daemon running on macOS.
    Connects to the 24/7 central workflow server, syncing tasks bidirectionally
    and posting native desktop notifications.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        vault_dir: Optional[str] = None,
    ) -> None:
        self.server_url = (server_url or os.environ.get("SERVER_URL", "http://localhost:8765")).rstrip("/")
        self.vault_dir = os.path.expanduser(
            vault_dir or os.environ.get("OBSIDIAN_VAULT_DIR", "/Users/rahman/Documents/Obsidian Vault/Task-List")
        )

        self.vault_sync = ObsidianVaultSync(vault_dir=self.vault_dir, server_url=self.server_url)
        self.focus_streamer = DesktopFocusStreamer(server_url=self.server_url)
        self._running = False

    @staticmethod
    def show_native_notification(title: str, message: str, sound: str = "Subtle") -> bool:
        """Display native macOS Notification Center banner."""
        if sys.platform != "darwin":
            logger.info(f"[Mock macOS Notification] {title}: {message}")
            return True

        safe_title = title.replace('"', '\"')
        safe_msg = message.replace('"', '\"')
        script = f'display notification "{safe_msg}" with title "{safe_title}" sound name "{sound}"'
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
            return True
        except Exception as e:
            logger.warning(f"Failed to post native notification: {e}")
            return False

    def _sync_latest_tasks_from_server(self) -> None:
        """Fetch latest tasks from server and update local daily note if needed."""
        url = f"{self.server_url}/api/tasks"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tasks = data.get("tasks", [])
                summary = data.get("summary", {})
                file_name = summary.get("file")
                if file_name and tasks:
                    # Construct markdown content
                    date_header = file_name.replace(".md", "")
                    lines = [f"## {date_header}\n\n"]
                    for t in tasks:
                        checked = "x" if t.get("completed") else " "
                        lines.append(f"- [{checked}] {t.get('text')}\n")
                    content = "".join(lines)
                    self.vault_sync.apply_remote_update(file_name, content)
        except Exception as e:
            logger.debug(f"Could not poll server tasks: {e}")

    def run(self) -> None:
        """Main service loop."""
        self._running = True
        logger.info(f"Starting MacClientDaemon connecting to {self.server_url}...")
        logger.info(f"Local Obsidian Vault: {self.vault_dir}")

        # Start child workers
        self.vault_sync.start_watching()
        self.focus_streamer.start_streaming()

        # Handle signals for clean shutdown
        def _signal_handler(sig, frame):
            logger.info("Received termination signal. Shutting down...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        # Polling/Sync loop
        poll_count = 0
        while self._running:
            try:
                poll_count += 1
                # Periodic sync check every 10 seconds
                if poll_count % 5 == 0:
                    self._sync_latest_tasks_from_server()
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Error in daemon loop: {e}")
                time.sleep(3)

    def stop(self) -> None:
        """Stop all background components."""
        self._running = False
        self.vault_sync.stop()
        self.focus_streamer.stop()
        logger.info("MacClientDaemon stopped cleanly.")


def main():
    daemon = MacClientDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
