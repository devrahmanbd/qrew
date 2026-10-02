"""
Self-Hosted Multi-Device Real-Time Notification Engine.
Dispatches native system alerts with zero external third-party services:
- macOS: Native Notification Center via AppleScript (osascript)
- Android / Mobile Browser: Native HTML5 Web Notifications & Vibration API via WebSockets
- Chrome Extension: Native chrome.notifications API
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("macos_workflow_mcp.notifications")


class NotificationBridge:
    """
    Delivers notifications across macOS (native System Notification Center)
    and connected local devices (Android / Browser) via self-hosted WebSocket event dispatching.
    Zero external dependencies or third-party apps required.
    """

    def __init__(
        self,
        ws_broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
        default_channel: str = "all",
        ntfy_topic: Optional[str] = None,
    ) -> None:
        self.ntfy_topic = ntfy_topic
        self.ws_broadcast_callback = ws_broadcast_callback
        self.default_channel = default_channel.lower()

    def set_ws_broadcast_callback(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Register the WebSocket broadcast callback to push alerts to connected Web/Mobile/Extension clients."""
        self.ws_broadcast_callback = callback

    def notify_macos(
        self,
        title: str,
        message: str,
        subtitle: str = "",
        sound: bool = True,
    ) -> bool:
        """
        Deliver a native macOS notification via AppleScript osascript.
        Safe fallback in non-macOS environments.
        """
        safe_title = title.replace('"', '\\"')
        safe_msg = message.replace('"', '\\"')
        safe_sub = subtitle.replace('"', '\\"')

        sound_clause = ' sound name "default"' if sound else ""
        sub_clause = f' subtitle "{safe_sub}"' if safe_sub else ""

        script = f'display notification "{safe_msg}" with title "{safe_title}"{sub_clause}{sound_clause}'

        if sys.platform == "darwin":
            try:
                proc = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    return True
                logger.warning(f"osascript error: {proc.stderr.strip()}")
                return False
            except Exception as e:
                logger.error(f"Failed to execute osascript notification: {e}")
                return False
        else:
            logger.info(f"[macOS Notification Simulated] Title: {title} | {message}")
            return True

    def notify_websocket(
        self,
        title: str,
        message: str,
        priority: str = "high",
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Dispatch notification event directly to connected Android PWA, Web UI, and Chrome Extension.
        This triggers native browser/extension notifications locally on the receiving device.
        """
        if not self.ws_broadcast_callback:
            logger.debug("No WebSocket broadcast callback registered.")
            return False

        event_data = {
            "event": "task_reminder",
            "title": title,
            "message": message,
            "priority": priority,
            "payload": payload or {},
        }

        try:
            res = self.ws_broadcast_callback(event_data)
            # If callback is a coroutine, fire and forget or schedule
            if hasattr(res, "__await__"):
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(res)
                else:
                    loop.run_until_complete(res)
            return True
        except Exception as e:
            logger.warning(f"Failed to broadcast WebSocket notification: {e}")
            return False

    def notify(
        self,
        title: str,
        message: str,
        subtitle: str = "",
        channel: Optional[str] = None,
        priority: str = "high",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Route notification to requested channel: 'macos', 'client' (Android/Web/Chrome via WS), or 'all'.
        """
        target_channel = (channel or self.default_channel).lower()
        results: Dict[str, Any] = {"channel": target_channel, "macos": False, "client": False}

        if target_channel in ("macos", "all", "desktop"):
            results["macos"] = self.notify_macos(
                title=title,
                message=message,
                subtitle=subtitle,
            )

        if target_channel in ("client", "android", "mobile", "web", "extension", "all"):
            results["client"] = self.notify_websocket(
                title=title,
                message=message,
                priority=priority,
                payload=payload,
            )

        results["delivered"] = results["macos"] or results["client"]
        return results

    def remind_task(
        self,
        task: Union[Dict[str, Any], Any, str],
        reason: str = "Upcoming focus item",
        channel: str = "all",
        priority: str = "high",
    ) -> Dict[str, Any]:
        """
        Delivers a rich task reminder across desktop and connected mobile/browser clients.
        """
        if isinstance(task, str):
            task_text = task
            section = "Tasks"
        elif hasattr(task, "text"):
            task_text = task.text
            section = getattr(task, "section", "Tasks")
        elif isinstance(task, dict):
            task_text = task.get("text", str(task))
            section = task.get("section", "Tasks")
        else:
            task_text = str(task)
            section = "Tasks"

        title = f"Task Priority: {section}"
        message = f"{task_text}\nReason: {reason}"
        subtitle = reason

        return self.notify(
            title=title,
            message=message,
            subtitle=subtitle,
            channel=channel,
            priority=priority,
            payload={"task_text": task_text, "section": section, "reason": reason},
        )
