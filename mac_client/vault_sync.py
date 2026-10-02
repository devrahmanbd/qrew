"""
Obsidian Vault Synchronizer with Infinite Loop Prevention.
Monitors local Markdown daily notes (DD-MMM.md) and synchronizes bidirectionally
with the 24/7 central server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger("mac_client.vault_sync")


class ObsidianVaultSync:
    """
    Watches the local Obsidian Task-List folder, synchronizing file changes
    to the central server, and applying incoming remote updates atomically
    without triggering cyclic sync loops.
    """

    DATE_FILE_PATTERN = re.compile(r"^(\d{1,2}-[A-Za-z]{3})\.md$")

    def __init__(
        self,
        vault_dir: Optional[str] = None,
        server_url: Optional[str] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self.vault_dir = Path(
            os.path.expanduser(
                vault_dir
                or os.environ.get("OBSIDIAN_VAULT_DIR", "/Users/rahman/Documents/Obsidian Vault/Task-List")
            )
        )
        self.server_url = (server_url or os.environ.get("SERVER_URL", "http://localhost:8765")).rstrip("/")
        self.poll_interval = poll_interval

        self._file_hashes: Dict[str, str] = {}
        self._suppressed_hashes: Set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_file_safe(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Error reading {path}: {e}")
            return None

    def _atomic_write(self, path: Path, content: str) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as tf:
                tf.write(content)
                temp_name = tf.name
            os.replace(temp_name, path)
            return True
        except Exception as e:
            logger.error(f"Atomic write error for {path}: {e}")
            return False

    def scan_initial_state(self) -> None:
        """Cache initial hashes of all daily notes in the vault."""
        if not self.vault_dir.exists():
            logger.info(f"Vault directory {self.vault_dir} does not exist yet. Creating...")
            self.vault_dir.mkdir(parents=True, exist_ok=True)

        for p in self.vault_dir.glob("*.md"):
            if self.DATE_FILE_PATTERN.match(p.name):
                content = self._read_file_safe(p)
                if content is not None:
                    h = self._compute_hash(content)
                    self._file_hashes[p.name] = h
        logger.info(f"Initialized vault watcher with {len(self._file_hashes)} daily notes.")

    def push_file_to_server(self, file_name: str, content: str) -> bool:
        """Send local file content to central server."""
        url = f"{self.server_url}/api/sync/vault"
        payload = json.dumps({"file_name": file_name, "content": content}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 201)
        except urllib.error.HTTPError as e:
            # If server endpoint does not have /api/sync/vault, fallback gracefully
            logger.debug(f"Server sync push returned HTTP {e.code}")
            return False
        except Exception as e:
            logger.debug(f"Could not push vault update to server: {e}")
            return False

    def apply_remote_update(self, file_name: str, content: str) -> bool:
        """
        Apply incoming remote update from server (e.g. checked on Android)
        atomically to local Obsidian note without triggering an upload loop.
        """
        if not self.DATE_FILE_PATTERN.match(file_name):
            return False

        target_path = self.vault_dir / file_name
        new_hash = self._compute_hash(content)

        with self._lock:
            # Check if identical to current local file
            if self._file_hashes.get(file_name) == new_hash:
                return True

            # Register hash suppression to prevent local watcher from re-uploading
            self._suppressed_hashes.add(new_hash)
            self._file_hashes[file_name] = new_hash

        success = self._atomic_write(target_path, content)
        if success:
            logger.info(f"Applied remote update to {file_name} (hash: {new_hash[:8]}).")
        return success

    def _poll_step(self) -> None:
        """Check for local file modifications."""
        if not self.vault_dir.exists():
            return

        for p in self.vault_dir.glob("*.md"):
            if not self.DATE_FILE_PATTERN.match(p.name):
                continue

            content = self._read_file_safe(p)
            if content is None:
                continue

            current_hash = self._compute_hash(content)

            with self._lock:
                # Check if this change was triggered by our own remote apply
                if current_hash in self._suppressed_hashes:
                    self._suppressed_hashes.remove(current_hash)
                    self._file_hashes[p.name] = current_hash
                    continue

                previous_hash = self._file_hashes.get(p.name)
                if previous_hash != current_hash:
                    logger.info(f"Local edit detected in {p.name}. Syncing to server...")
                    self._file_hashes[p.name] = current_hash
                    # Push outside of lock
                    threading.Thread(
                        target=self.push_file_to_server,
                        args=(p.name, content),
                        daemon=True,
                    ).start()

    def start_watching(self) -> None:
        """Start background polling thread."""
        if self._running:
            return
        self._running = True
        self.scan_initial_state()

        def _run():
            while self._running:
                try:
                    self._poll_step()
                except Exception as e:
                    logger.warning(f"Error during vault poll step: {e}")
                time.sleep(self.poll_interval)

        self._thread = threading.Thread(target=_run, daemon=True, name="ObsidianVaultSync")
        self._thread.start()
        logger.info("ObsidianVaultSync started.")

    def stop(self) -> None:
        """Stop watcher thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("ObsidianVaultSync stopped.")
