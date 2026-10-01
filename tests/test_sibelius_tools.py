"""Tests for what the tools do differently when Sibelius is connected.

Everything the tools share between applications is tested in
``test_tools.py``. These tests connect the ``SibeliusBridge`` in the
context's registry to a mock Sibelius Connect and check that Sibelius's
defaults, the bridge plug-in's replies and its warnings reach the model
through the tools.
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
    get_live_score_info,
)
from mcp_score.tools.manipulation import add_live_rehearsal_mark, transpose_passage
from tests.fakes import (
    REMOTE_CONTROL_HANDSHAKE,
    SIBELIUS_HANDSHAKE,
    WEBSOCKETS_CONNECT,
    fake_connection,
    plugin_reply,
    sent_payloads,
)

if TYPE_CHECKING:
    from mcp_score.bridge import BridgeRegistry
    from mcp_score.context import ScoreContext


async def _connect_sibelius(
    context: ScoreContext, *replies: dict[str, Any]
) -> AsyncMock:
    """Connect the Sibelius bridge behind *context* to a mock Sibelius Connect.

    The mock completes the handshake and then answers each message with
    the next of *replies*.
    """
    connection = fake_connection(*SIBELIUS_HANDSHAKE, *replies)
    with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
        await connect_to_sibelius(context)
    return connection


def _cursor(measure: int, element: dict[str, Any] | None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "measure": measure,
        "staff": 0,
        "position": 0,
        "time_signature_denominator": 4,
    }
    if element is not None:
        info["element"] = element
    return plugin_reply(info)


class TestConnectToSibelius:
    @pytest.mark.anyio()
    async def test_connect_activates_sibelius_on_its_default_port(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connect = AsyncMock(return_value=fake_connection(*SIBELIUS_HANDSHAKE))

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
        connect = AsyncMock(return_value=fake_connection(*SIBELIUS_HANDSHAKE))

        with patch(WEBSOCKETS_CONNECT, connect):
            # Act
            result = await connect_to_sibelius(context, port=5555)

        # Assert
        assert result.uri == "ws://localhost:5555"
        assert registry.sibelius.port == 5555

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
        # Arrange
        sibelius_connection = await _connect_sibelius(context)
        dorico_connection = fake_connection(*REMOTE_CONTROL_HANDSHAKE)

        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=dorico_connection)):
            # Act
            await connect_to_dorico(context)

        # Assert
        assert registry.active is registry.dorico
        assert registry.sibelius.is_connected is False
        sibelius_connection.close.assert_awaited_once()

    @pytest.mark.anyio()
    async def test_disconnect_deactivates(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connection = await _connect_sibelius(context)

        # Act
        result = await disconnect_from_sibelius(context)

        # Assert
        assert result.application == "Sibelius"
        connection.close.assert_awaited_once()
        assert registry.active is None


class TestSibeliusThroughTools:
    @pytest.mark.anyio()
    async def test_read_passage_reads_each_measure_without_warning(
        self, context: ScoreContext
    ) -> None:
        # Arrange
        quarter_c = {
            "type": "NoteRest",
            "position": 0,
            "duration": 256,
            "notes": [{"pitch": 60, "diatonic_pitch": 35, "name": "C4"}],
        }
        connection = await _connect_sibelius(
            context,
            plugin_reply({"measure": 1, "staff": 0}),
            _cursor(1, quarter_c),
            plugin_reply({"measure": 2, "staff": 0}),
            _cursor(2, None),
        )

        # Act
        passage = await read_passage(context, 1, 2)

        # Assert
        assert passage.warning is None
        first, second = passage.elements
        assert first.content.element is not None
        assert first.content.element.notes is not None
        assert first.content.element.notes[0].tpc == 14
        assert second.content.element is None
        assert [payload["method"] for payload in sent_payloads(connection)[1:]] == [
            "GoTo",
            "GetCursorInfo",
            "GoTo",
            "GetCursorInfo",
        ]

    @pytest.mark.anyio()
    async def test_score_info_comes_from_the_plugin(
        self, context: ScoreContext
    ) -> None:
        # Arrange
        await _connect_sibelius(
            context,
            plugin_reply(
                {
                    "title": "",
                    "part_count": 0,
                    "parts": [],
                    "measure_count": 4,
                    "key_signature": 0,
                    "time_signature": {"numerator": 4, "denominator": 4},
                }
            ),
        )

        # Act
        score = await get_live_score_info(context)

        # Assert
        assert score.measure_count == 4

    @pytest.mark.anyio()
    async def test_plugin_refusal_reaches_the_model_as_tool_error(
        self, context: ScoreContext
    ) -> None:
        # Arrange
        await _connect_sibelius(
            context, plugin_reply({"error": "Measure 40 out of range (1-32)"})
        )

        # Act / Assert
        with pytest.raises(ToolError, match=r"Measure 40 out of range"):
            await add_live_rehearsal_mark(context, 40, "A")

    @pytest.mark.anyio()
    async def test_transpose_passage_selects_then_transposes(
        self, context: ScoreContext
    ) -> None:
        # Arrange
        connection = await _connect_sibelius(
            context,
            plugin_reply({"measure": 3, "staff": 0}),
            plugin_reply({"measure": 3, "staff": 1}),
            plugin_reply(
                {
                    "start_measure": 3,
                    "end_measure": 4,
                    "start_staff": 1,
                    "end_staff": 1,
                }
            ),
            plugin_reply({"notes": 7}),
        )

        # Act
        result = await transpose_passage(context, 3, 4, 1, 7)

        # Assert
        assert result.notes == 7
        assert sent_payloads(connection)[-1]["args"] == [3, 4, 1, 1, 4, 5]
