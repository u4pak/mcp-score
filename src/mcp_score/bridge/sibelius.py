"""Bridge to Sibelius Connect (experimental).

Sibelius 2024.3 and later serve the Remote Control protocol through
Sibelius Connect on port 1898 by default; no plugin is needed, but it
requires Sibelius Ultimate. Support is experimental: the API is
command-only, like Dorico's, and this bridge has not been verified
against a running Sibelius.
"""

from mcp_score.bridge.remote_control import DEFAULT_CLIENT_NAME, RemoteControlBridge
from mcp_score.bridge.websocket import DEFAULT_HOST

__all__ = ["DEFAULT_PORT", "SibeliusBridge"]

DEFAULT_PORT = 1898
"""Sibelius Connect's default port; configurable in its preferences."""

APPLICATION_NAME = "Sibelius"


class SibeliusBridge(RemoteControlBridge):
    """Remote Control bridge with Sibelius Connect's defaults."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_name: str = DEFAULT_CLIENT_NAME,
    ) -> None:
        super().__init__(APPLICATION_NAME, host, port, client_name)
