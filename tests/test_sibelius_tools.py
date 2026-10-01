"""Tests for what the tools do differently when Sibelius is connected.

Everything the tools share between applications is tested in
``test_tools.py``, and the Remote Control limitations they share with
Dorico in ``test_dorico_tools.py``. These tests connect the
``SibeliusBridge`` in the context's registry to a mock WebSocket and check
that Sibelius's defaults reach the model through the tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from mcp_score.bridge.sibelius import DEFAULT_PORT
from mcp_score.tools import ToolError
from mcp_score.tools.analysis import read_passage
from mcp_score.tools.connection import (
    connect_to_dorico,
    connect_to_sibelius,
    disconnect_from_sibelius,
)
from tests.fakes import (
    REMOTE_CONTROL_HANDSHAKE,
    WEBSOCKETS_CONNECT,
    fake_connection,
    sent_payloads,
)

if TYPE_CHECKING:
    from mcp_score.bridge import BridgeRegistry
    from mcp_score.context import ScoreContext

COMMAND_ACCEPTED: dict[str, Any] = {"message": "response", "code": "kOK"}


async def _connect_sibelius(
    context: ScoreContext, *command_replies: dict[str, Any]
) -> AsyncMock:
    """Connect the Sibelius bridge behind *context* to a mock server.

    The mock completes the handshake and then answers each command with
    the next of *command_replies*.
    """
    connection = fake_connection(*REMOTE_CONTROL_HANDSHAKE, *command_replies)
    with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
        await connect_to_sibelius(context)
    return connection


class TestConnectToSibelius:
    @pytest.mark.anyio()
    async def test_connect_activates_sibelius_on_its_default_port(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connect = AsyncMock(return_value=fake_connection(*REMOTE_CONTROL_HANDSHAKE))

        with patch(WEBSOCKETS_CONNECT, connect):
            # Act
            result = await connect_to_sibelius(context)

        # Assert
        assert result.application == "Sibelius"
        assert result.uri == f"ws://localhost:{DEFAULT_PORT}"
        assert registry.active is registry.sibelius
        connect.assert_awaited_once_with(f"ws://localhost:{DEFAULT_PORT}")

    @pytest.mark.anyio()
    async def test_connect_with_custom_port_uses_it(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connect = AsyncMock(return_value=fake_connection(*REMOTE_CONTROL_HANDSHAKE))

        with patch(WEBSOCKETS_CONNECT, connect):
            # Act
            result = await connect_to_sibelius(context, port=5555)

        # Assert
        assert result.uri == "ws://localhost:5555"
        assert registry.sibelius.port == 5555
        connect.assert_awaited_once_with("ws://localhost:5555")

    @pytest.mark.anyio()
    async def test_connect_failure_raises_with_sibelius_connect_hint(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        with (
            patch(WEBSOCKETS_CONNECT, AsyncMock(side_effect=OSError("refused"))),
            pytest.raises(ToolError, match="Could not connect to Sibelius") as exc_info,
        ):
            # Act
            await connect_to_sibelius(context)

        # Assert
        assert "Sibelius Connect" in str(exc_info.value)
        assert registry.active is None

    @pytest.mark.anyio()
    async def test_connect_dorico_disconnects_sibelius(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange: both Remote Control bridges share the protocol, so the
        # registry must still tell them apart.
        sibelius_connection = await _connect_sibelius(context)
        dorico_connection = fake_connection(*REMOTE_CONTROL_HANDSHAKE)

        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=dorico_connection)):
            # Act
            await connect_to_dorico(context)

        # Assert
        assert registry.active is registry.dorico
        assert registry.sibelius.is_connected is False
        assert sent_payloads(sibelius_connection)[-1] == {"message": "disconnect"}

    @pytest.mark.anyio()
    async def test_disconnect_says_goodbye_and_deactivates(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connection = await _connect_sibelius(context)

        # Act
        result = await disconnect_from_sibelius(context)

        # Assert
        assert result.application == "Sibelius"
        assert sent_payloads(connection)[-1] == {"message": "disconnect"}
        assert registry.active is None


class TestSibeliusLimitationsThroughTools:
    @pytest.mark.anyio()
    async def test_read_passage_names_sibelius_in_reading_limitation(
        self, context: ScoreContext
    ) -> None:
        # Arrange
        await _connect_sibelius(context, COMMAND_ACCEPTED)

        # Act / Assert
        with pytest.raises(
            ToolError, match="^Sibelius's Remote Control API cannot report the cursor"
        ):
            await read_passage(context, 1, 1)
