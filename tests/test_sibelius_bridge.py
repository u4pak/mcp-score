"""Tests for SibeliusBridge: only the defaults it adds to RemoteControlBridge.

The protocol itself is tested in ``test_remote_control_bridge.py``.
"""

from __future__ import annotations

from mcp_score.bridge.remote_control import DEFAULT_CLIENT_NAME
from mcp_score.bridge.sibelius import DEFAULT_PORT, SibeliusBridge


class TestSibeliusBridgeDefaults:
    def test_default_bridge_targets_sibelius_connect_port(self) -> None:
        # Arrange / Act
        bridge = SibeliusBridge()

        # Assert
        assert bridge.application_name == "Sibelius"
        assert bridge.uri == f"ws://localhost:{DEFAULT_PORT}"
        assert bridge.client_name == DEFAULT_CLIENT_NAME

    def test_custom_address_and_client_name_are_used(self) -> None:
        # Arrange / Act
        bridge = SibeliusBridge(host="192.168.1.10", port=9999, client_name="my-tool")

        # Assert
        assert bridge.uri == "ws://192.168.1.10:9999"
        assert bridge.client_name == "my-tool"
