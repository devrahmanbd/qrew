"""macOS Client Agent and Local MCP Bridge Package."""

from .vault_sync import ObsidianVaultSync
from .focus_streamer import DesktopFocusStreamer
from .mac_daemon import MacClientDaemon
from .mcp_bridge import StdioMcpBridge, McpServerProxy, TOOLS_SCHEMA

__all__ = [
    "ObsidianVaultSync",
    "DesktopFocusStreamer",
    "MacClientDaemon",
    "StdioMcpBridge",
    "McpServerProxy",
    "TOOLS_SCHEMA",
]
