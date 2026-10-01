"""Tests for the MCP tools: the error wrapper, connection, analysis, manipulation.

Behaviour shared by every application (validation, the not-connected
error, navigation, what the bridge is asked to do) is tested here once,
against a ``FakeBridge`` behind the context a tool receives from the
server. A tool that cannot do what was asked raises ``ToolError``; an
application's refusal (``BridgeError``) reaches the model the same way.
Dorico- and Sibelius-specific behaviour lives in ``test_dorico_tools.py``
and ``test_sibelius_tools.py``.
"""

from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from mcp_score.bridge import BridgeError
from mcp_score.bridge.passage import PassageEvent
from mcp_score.bridge.results import (
    ApplicationReply,
    ArticulationSet,
    BarlineSet,
    BeatPosition,
    ChordSymbolAdded,
    ClefSet,
    CursorInfo,
    CursorPosition,
    Duration,
    DynamicAdded,
    GraceNotesAdded,
    KeySignatureSet,
    LineAdded,
    MeasuresAppended,
    NoteAdded,
    NoteheadSet,
    Part,
    RehearsalMarkAdded,
    RestAdded,
    ScoreInfo,
    SelectionProperties,
    StickingAdded,
    TempoSet,
    TextAdded,
    TimeSignature,
    TimeSignatureSet,
    Transposed,
    TremoloSet,
    TupletAdded,
)
from mcp_score.server import create_server
from mcp_score.tools import NOT_CONNECTED, ToolError, parse_beat, score_tool
from mcp_score.tools.analysis import (
    MeasureContent,
    get_measure_content,
    get_selection_properties,
    read_passage,
)
from mcp_score.tools.connection import (
    connect_to_musescore,
    disconnect_from_musescore,
    get_live_score_info,
    ping_score_app,
)
from mcp_score.tools.manipulation import (
    add_live_chord_symbol,
    add_live_dynamic,
    add_live_grace_notes,
    add_live_line,
    add_live_note,
    add_live_rehearsal_mark,
    add_live_rest,
    add_live_sticking,
    add_live_text,
    add_live_tuplet,
    append_live_measures,
    set_live_articulation,
    set_live_barline,
    set_live_clef,
    set_live_key_signature,
    set_live_notehead,
    set_live_tempo,
    set_live_time_signature,
    set_live_tremolo,
    transpose_passage,
    undo_last_action,
    write_live_passage,
)
from tests.fakes import WEBSOCKETS_CONNECT, BridgeCall, FakeBridge, fake_connection

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Concatenate

    from mcp_score.bridge import BridgeRegistry
    from mcp_score.context import ScoreContext

type ToolCall = Callable[[ScoreContext], Awaitable[BaseModel]]
"""A tool with its arguments bound, ready to run against a context."""


def bind_arguments[**P, R: BaseModel](
    tool: Callable[Concatenate[ScoreContext, P], Awaitable[R]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> ToolCall:
    """Bind a tool's arguments, leaving the context for the test to supply."""

    def call(context: ScoreContext) -> Awaitable[R]:
        return tool(context, *args, **kwargs)

    return call


NAVIGATION_ERROR = "Measure 99 is beyond the end of the score"
LIMITATION = "Only the selection's properties are available."

QUARTER = Duration(numerator=1, denominator=4)

CURSOR_AT_C4 = CursorInfo(measure=2, staff=0, voice=0, beat=1, tick=1920, element=None)
"""A cursor reading the fake application could report for measure 2."""


# ── score_tool ────────────────────────────────────────────────────────


class TestScoreTool:
    @pytest.mark.anyio()
    async def test_bridge_error_becomes_tool_error_with_same_message(self) -> None:
        # Arrange
        refusal = BridgeError("Measure 99 out of range", measure=99)

        @score_tool
        async def refused() -> CursorPosition:
            raise refusal

        # Act
        with pytest.raises(ToolError) as exc_info:
            await refused()

        # Assert
        assert str(exc_info.value) == "Measure 99 out of range"
        assert exc_info.value.__cause__ is refusal

    @pytest.mark.anyio()
    async def test_result_passes_through(self) -> None:
        # Arrange
        position = CursorPosition(measure=4, staff=1)

        @score_tool
        async def succeeding() -> CursorPosition:
            return position

        # Act
        result = await succeeding()

        # Assert
        assert result is position

    def test_wrapper_keeps_parameters(self) -> None:
        # Arrange
        async def original(measure: int, text: str = "A") -> CursorPosition:
            return CursorPosition(measure=measure, staff=0)

        # Act
        wrapped = score_tool(original)

        # Assert
        assert (
            inspect.signature(wrapped).parameters
            == inspect.signature(original).parameters
        )
        assert wrapped.__name__ == "original"


# ── Not connected ────────────────────────────────────────────────────


class TestToolsWithoutConnection:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(get_live_score_info, id="get_live_score_info"),
            pytest.param(ping_score_app, id="ping_score_app"),
            pytest.param(bind_arguments(read_passage, 1, 4), id="read_passage"),
            pytest.param(
                bind_arguments(get_measure_content, 1),
                id="get_measure_content",
            ),
            pytest.param(get_selection_properties, id="get_selection_properties"),
            pytest.param(bind_arguments(add_live_note, 1, 60), id="add_live_note"),
            pytest.param(
                bind_arguments(add_live_rehearsal_mark, 1, "A"),
                id="add_live_rehearsal_mark",
            ),
            pytest.param(
                bind_arguments(add_live_chord_symbol, 1, "Cmaj7"),
                id="add_live_chord_symbol",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 1, "mf"),
                id="add_live_dynamic",
            ),
            pytest.param(
                bind_arguments(set_live_barline, 1, "double"),
                id="set_live_barline",
            ),
            pytest.param(
                bind_arguments(set_live_key_signature, 1, 2),
                id="set_live_key_signature",
            ),
            pytest.param(
                bind_arguments(set_live_time_signature, 1, 3, 4),
                id="set_live_time_signature",
            ),
            pytest.param(bind_arguments(set_live_tempo, 1, 120), id="set_live_tempo"),
            pytest.param(
                bind_arguments(append_live_measures, 2),
                id="append_live_measures",
            ),
            pytest.param(
                bind_arguments(transpose_passage, 1, 4, 0, 2),
                id="transpose_passage",
            ),
            pytest.param(undo_last_action, id="undo_last_action"),
            pytest.param(
                bind_arguments(set_live_articulation, 1, 2, "accent"),
                id="set_live_articulation",
            ),
            pytest.param(
                bind_arguments(set_live_notehead, 1, 2, "slash"),
                id="set_live_notehead",
            ),
            pytest.param(
                bind_arguments(add_live_line, 1, 2, "crescendo"),
                id="add_live_line",
            ),
            pytest.param(bind_arguments(add_live_text, 1, "pizz."), id="add_live_text"),
            pytest.param(bind_arguments(set_live_clef, 1, "bass"), id="set_live_clef"),
            pytest.param(bind_arguments(add_live_rest, 1), id="add_live_rest"),
            pytest.param(
                bind_arguments(add_live_tuplet, 1, [60, 62, 64]),
                id="add_live_tuplet",
            ),
            pytest.param(bind_arguments(set_live_tremolo, 1, 2), id="set_live_tremolo"),
            pytest.param(
                bind_arguments(add_live_grace_notes, 1, "flam"),
                id="add_live_grace_notes",
            ),
            pytest.param(
                bind_arguments(add_live_sticking, 1, "RL"), id="add_live_sticking"
            ),
        ],
    )
    async def test_tool_without_connection_raises_not_connected(
        self, context: ScoreContext, call: ToolCall
    ) -> None:
        # Arrange: the fresh registry behind the context has nothing active.
        # Act / Assert
        with pytest.raises(ToolError, match=re.escape(NOT_CONNECTED)):
            await call(context)

    @pytest.mark.anyio()
    async def test_tool_with_disconnected_active_bridge_raises_not_connected(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        registry.active = FakeBridge(is_connected=False)

        # Act / Assert
        with pytest.raises(ToolError, match=re.escape(NOT_CONNECTED)):
            await undo_last_action(context)


# ── Connection tools ─────────────────────────────────────────────────


class TestConnectToMusescore:
    @pytest.mark.anyio()
    async def test_connect_activates_musescore_at_given_address(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connect = AsyncMock(return_value=fake_connection())

        with patch(WEBSOCKETS_CONNECT, connect):
            # Act
            result = await connect_to_musescore(context, host="10.0.0.5", port=9000)

        # Assert
        assert result.application == "MuseScore"
        assert result.uri == "ws://10.0.0.5:9000"
        assert registry.active is registry.musescore
        assert registry.musescore.is_connected is True
        connect.assert_awaited_once_with("ws://10.0.0.5:9000")

    @pytest.mark.anyio()
    async def test_connect_failure_raises_with_plugin_hint(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        with (
            patch(WEBSOCKETS_CONNECT, AsyncMock(side_effect=OSError("refused"))),
            pytest.raises(
                ToolError, match="Could not connect to MuseScore"
            ) as exc_info,
        ):
            # Act
            await connect_to_musescore(context)

        # Assert
        assert "plugin" in str(exc_info.value)
        assert registry.active is None

    @pytest.mark.anyio()
    async def test_disconnect_closes_connection_and_deactivates(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        connection = fake_connection()
        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
            await connect_to_musescore(context)

        # Act
        result = await disconnect_from_musescore(context)

        # Assert
        assert result.application == "MuseScore"
        assert registry.active is None
        connection.close.assert_awaited_once()


class TestGetLiveScoreInfo:
    @pytest.mark.anyio()
    async def test_get_info_returns_bridge_score(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        score = ScoreInfo(
            title="Test Score",
            part_count=2,
            parts=[
                Part(name="Flute", start_staff=0, end_staff=0),
                Part(name="Piano", start_staff=1, end_staff=2),
            ],
            measure_count=32,
            key_signature=-3,
            time_signature=TimeSignature(numerator=3, denominator=4),
        )
        connected_bridge.reply("get_score", score)

        # Act
        result = await get_live_score_info(context)

        # Assert
        assert result is score


class TestPingScoreApp:
    @pytest.mark.anyio()
    async def test_ping_responsive_app_returns_success(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.ping_succeeds = True

        # Act
        result = await ping_score_app(context)

        # Assert
        assert result.application == "FakeApp"

    @pytest.mark.anyio()
    async def test_ping_unresponsive_app_raises(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.ping_succeeds = False

        # Act / Assert
        with pytest.raises(ToolError, match="FakeApp is not responding"):
            await ping_score_app(context)


# ── Analysis tools ───────────────────────────────────────────────────


class TestReadPassage:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("start_measure", "end_measure", "expected_error"),
        [
            pytest.param(0, 4, "start_measure must be >= 1.", id="start-below-one"),
            pytest.param(5, 3, "end_measure must be >= start_measure.", id="empty"),
        ],
    )
    async def test_read_passage_with_invalid_range_raises_without_reading(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        start_measure: int,
        end_measure: int,
        expected_error: str,
    ) -> None:
        # Act
        with pytest.raises(ToolError, match=re.escape(expected_error)):
            await read_passage(context, start_measure, end_measure)

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    async def test_read_passage_reads_cursor_in_every_measure(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.reply("get_cursor_info", CURSOR_AT_C4)

        # Act
        result = await read_passage(context, 2, 3)

        # Assert
        assert (result.start_measure, result.end_measure) == (2, 3)
        assert result.staff is None
        assert result.elements == [
            MeasureContent(measure=2, content=CURSOR_AT_C4),
            MeasureContent(measure=3, content=CURSOR_AT_C4),
        ]
        assert connected_bridge.calls == [
            BridgeCall("go_to_measure", (2,)),
            BridgeCall("get_cursor_info", ()),
            BridgeCall("go_to_measure", (3,)),
            BridgeCall("get_cursor_info", ()),
        ]

    @pytest.mark.anyio()
    async def test_read_passage_with_staff_moves_to_staff_in_every_measure(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        await read_passage(context, 1, 2, staff=3)

        # Assert
        assert connected_bridge.calls_to("go_to_staff") == [
            BridgeCall("go_to_staff", (3,)),
            BridgeCall("go_to_staff", (3,)),
        ]

    @pytest.mark.anyio()
    async def test_read_passage_with_navigation_error_stops_reading(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("go_to_measure", NAVIGATION_ERROR)

        # Act
        with pytest.raises(ToolError, match=NAVIGATION_ERROR):
            await read_passage(context, 99, 100)

        # Assert
        assert connected_bridge.calls == [BridgeCall("go_to_measure", (99,))]

    @pytest.mark.anyio()
    async def test_read_passage_attaches_content_reading_limitation(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        registry.active = FakeBridge(content_reading_limitation=LIMITATION)

        # Act
        result = await read_passage(context, 1, 1)

        # Assert
        assert result.warning == LIMITATION

    @pytest.mark.anyio()
    async def test_read_passage_without_limitation_has_no_warning(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        result = await read_passage(context, 1, 1)

        # Assert
        assert result.warning is None


class TestGetMeasureContent:
    @pytest.mark.anyio()
    async def test_get_measure_with_invalid_number_raises_without_navigating(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        with pytest.raises(ToolError, match="measure must be >= 1"):
            await get_measure_content(context, 0)

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    async def test_get_measure_navigates_then_selects(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.reply("select_measure", CursorPosition(measure=3, staff=1))

        # Act
        result = await get_measure_content(context, 3, staff=1)

        # Assert
        assert (result.measure, result.staff) == (3, 1)
        assert result.warning is None
        assert connected_bridge.calls == [
            BridgeCall("go_to_measure", (3,)),
            BridgeCall("go_to_staff", (1,)),
            BridgeCall("select_measure", ()),
        ]

    @pytest.mark.anyio()
    async def test_get_measure_with_staff_error_does_not_select(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("go_to_staff", "No staff 7")

        # Act
        with pytest.raises(ToolError, match="No staff 7"):
            await get_measure_content(context, 1, staff=7)

        # Assert
        assert connected_bridge.calls_to("select_measure") == []

    @pytest.mark.anyio()
    async def test_get_measure_attaches_content_reading_limitation(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        registry.active = FakeBridge(content_reading_limitation=LIMITATION)

        # Act
        result = await get_measure_content(context, 1)

        # Assert
        assert result.warning == LIMITATION


class TestGetSelectionProperties:
    @pytest.mark.anyio()
    async def test_get_properties_returns_bridge_properties_without_warning(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.reply(
            "get_properties", SelectionProperties(cursor=CURSOR_AT_C4)
        )

        # Act
        result = await get_selection_properties(context)

        # Assert
        assert result.cursor == CURSOR_AT_C4
        assert result.properties is None
        assert result.warning is None

    @pytest.mark.anyio()
    async def test_get_properties_attaches_content_reading_limitation(
        self, registry: BridgeRegistry, context: ScoreContext
    ) -> None:
        # Arrange
        bridge = FakeBridge(content_reading_limitation=LIMITATION)
        registry.active = bridge
        reply = ApplicationReply.model_validate(
            {"Properties": [{"Name": "kNoteHideStem"}]}
        )
        bridge.reply("get_properties", SelectionProperties(properties=reply))

        # Act
        result = await get_selection_properties(context)

        # Assert
        assert result.properties is reply
        assert result.warning == LIMITATION


# ── Manipulation tools ───────────────────────────────────────────────


class TestManipulationValidation:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("call", "expected_error"),
        [
            pytest.param(
                bind_arguments(add_live_note, 0, 60),
                "measure must be >= 1.",
                id="note-measure-zero",
            ),
            pytest.param(
                bind_arguments(add_live_note, 1, 128),
                "pitch must be between 0 and 127.",
                id="note-pitch-too-high",
            ),
            pytest.param(
                bind_arguments(add_live_note, 1, -1),
                "pitch must be between 0 and 127.",
                id="note-pitch-negative",
            ),
            pytest.param(
                bind_arguments(add_live_note, 1, 60, numerator=0),
                "numerator and denominator must be >= 1.",
                id="note-zero-numerator",
            ),
            pytest.param(
                bind_arguments(add_live_note, 1, 60, denominator=0),
                "numerator and denominator must be >= 1.",
                id="note-zero-denominator",
            ),
            pytest.param(
                bind_arguments(add_live_rehearsal_mark, 0, "A"),
                "measure must be >= 1.",
                id="rehearsal-mark-measure-zero",
            ),
            pytest.param(
                bind_arguments(add_live_chord_symbol, -1, "Cmaj7"),
                "measure must be >= 1.",
                id="chord-symbol-negative-measure",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 0, "mf"),
                "measure must be >= 1.",
                id="dynamic-measure-zero",
            ),
            pytest.param(
                bind_arguments(set_live_barline, 0, "double"),
                "measure must be >= 1.",
                id="barline-measure-zero",
            ),
            pytest.param(
                bind_arguments(set_live_key_signature, 0, 2),
                "measure must be >= 1.",
                id="key-signature-measure-zero",
            ),
            pytest.param(
                bind_arguments(set_live_time_signature, 1, 3, 0),
                "numerator and denominator must be >= 1.",
                id="time-signature-zero-denominator",
            ),
            pytest.param(
                bind_arguments(set_live_tempo, 1, 0),
                "bpm must be >= 1.",
                id="tempo-zero-bpm",
            ),
            pytest.param(
                bind_arguments(append_live_measures, 0),
                "count must be >= 1.",
                id="append-zero-measures",
            ),
            pytest.param(
                bind_arguments(transpose_passage, 5, 3, 0, 2),
                "end_measure must be >= start_measure.",
                id="transpose-empty-range",
            ),
            pytest.param(
                bind_arguments(transpose_passage, 0, 3, 0, 2),
                "start_measure must be >= 1.",
                id="transpose-start-zero",
            ),
            pytest.param(
                bind_arguments(set_live_articulation, 4, 2, "staccato"),
                "end_measure must be >= start_measure.",
                id="articulation-empty-range",
            ),
            pytest.param(
                bind_arguments(set_live_articulation, 1, 2, "staccato", beat=0),
                "beat must be >= 1.",
                id="articulation-beat-zero",
            ),
            pytest.param(
                bind_arguments(set_live_notehead, 1, 1, "cross", beat=-1),
                "beat must be >= 1.",
                id="notehead-negative-beat",
            ),
            pytest.param(
                bind_arguments(add_live_line, 0, 2, "slur"),
                "start_measure must be >= 1.",
                id="line-start-zero",
            ),
            pytest.param(
                bind_arguments(add_live_text, 1, "  "),
                "text must not be empty.",
                id="text-blank",
            ),
            pytest.param(
                bind_arguments(set_live_clef, 0, "alto"),
                "measure must be >= 1.",
                id="clef-measure-zero",
            ),
        ],
    )
    async def test_tool_with_invalid_argument_raises_without_touching_score(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        call: ToolCall,
        expected_error: str,
    ) -> None:
        # Act
        with pytest.raises(ToolError, match=re.escape(expected_error)):
            await call(context)

        # Assert
        assert connected_bridge.calls == []


class TestManipulationHappyPaths:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("call", "expected_calls", "reply"),
        [
            pytest.param(
                bind_arguments(add_live_note, 5, 60, 1, 8, staff=1),
                [
                    BridgeCall("go_to_measure", (5,)),
                    BridgeCall("go_to_staff", (1,)),
                    BridgeCall(
                        "add_note", (60, Duration(numerator=1, denominator=8), True)
                    ),
                ],
                NoteAdded(
                    measure=5,
                    staff=1,
                    pitch=60,
                    duration=Duration(numerator=1, denominator=8),
                ),
                id="add_live_note",
            ),
            pytest.param(
                bind_arguments(add_live_rehearsal_mark, 5, "B"),
                [
                    BridgeCall("go_to_measure", (5,)),
                    BridgeCall("add_rehearsal_mark", ("B",)),
                ],
                RehearsalMarkAdded(text="B", measure=5),
                id="add_live_rehearsal_mark",
            ),
            pytest.param(
                bind_arguments(add_live_chord_symbol, 2, "Dm7"),
                [
                    BridgeCall("go_to_measure", (2,)),
                    BridgeCall("add_chord_symbol", ("Dm7",)),
                ],
                ChordSymbolAdded(text="Dm7", measure=2),
                id="add_live_chord_symbol",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 4, "ff", staff=2),
                [
                    BridgeCall("go_to_measure", (4,)),
                    BridgeCall("go_to_staff", (2,)),
                    BridgeCall("add_dynamic", ("ff",)),
                ],
                DynamicAdded(dynamic="ff", measure=4),
                id="add_live_dynamic",
            ),
            pytest.param(
                bind_arguments(set_live_barline, 3, "double"),
                [
                    BridgeCall("go_to_measure", (3,)),
                    BridgeCall("set_barline", ("double",)),
                ],
                BarlineSet(barline_type="double", measure=3),
                id="set_live_barline",
            ),
            pytest.param(
                bind_arguments(set_live_key_signature, 1, -3),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("set_key_signature", (-3,)),
                ],
                KeySignatureSet(fifths=-3, measure=1),
                id="set_live_key_signature",
            ),
            pytest.param(
                bind_arguments(set_live_time_signature, 9, 6, 8),
                [
                    BridgeCall("go_to_measure", (9,)),
                    BridgeCall("set_time_signature", (6, 8)),
                ],
                TimeSignatureSet(numerator=6, denominator=8, measure=9),
                id="set_live_time_signature",
            ),
            pytest.param(
                bind_arguments(set_live_tempo, 1, 66, "Slow Blues"),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("set_tempo", (66, "Slow Blues")),
                ],
                TempoSet(bpm=66, text="Slow Blues", measure=1),
                id="set_live_tempo-with-text",
            ),
            pytest.param(
                bind_arguments(set_live_tempo, 1, 120),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("set_tempo", (120, None)),
                ],
                TempoSet(bpm=120, text="Quarter = 120", measure=1),
                id="set_live_tempo-without-text",
            ),
            pytest.param(
                bind_arguments(append_live_measures, 4),
                [BridgeCall("append_measures", (4,))],
                MeasuresAppended(count=4, total_measures=12),
                id="append_live_measures",
            ),
            pytest.param(
                bind_arguments(transpose_passage, 1, 8, 2, 5),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("go_to_staff", (2,)),
                    BridgeCall("select_range", (1, 8, 2, 2)),
                    BridgeCall("transpose", (5,)),
                ],
                Transposed(semitones=5, notes=16),
                id="transpose_passage",
            ),
            pytest.param(
                undo_last_action,
                [BridgeCall("undo", ())],
                CursorPosition(measure=7, staff=0),
                id="undo_last_action",
            ),
            pytest.param(
                bind_arguments(
                    set_live_articulation, 3, 4, "fermata", staff=1, beat=3, remove=True
                ),
                [
                    BridgeCall(
                        "set_articulation",
                        (3, 4, 1, "fermata", BeatPosition(beat=3), True),
                    )
                ],
                ArticulationSet(
                    articulation="fermata",
                    removed=True,
                    start_measure=3,
                    end_measure=4,
                    staff=1,
                    beat=BeatPosition(beat=3),
                    notes=2,
                ),
                id="set_live_articulation",
            ),
            pytest.param(
                bind_arguments(set_live_notehead, 5, 8, "slash"),
                [BridgeCall("set_notehead", (5, 8, 0, "slash", None))],
                NoteheadSet(
                    notehead="slash",
                    start_measure=5,
                    end_measure=8,
                    staff=0,
                    beat=None,
                    notes=16,
                ),
                id="set_live_notehead",
            ),
            pytest.param(
                bind_arguments(add_live_line, 2, 3, "diminuendo", staff=2),
                [BridgeCall("add_line", (2, 3, 2, "diminuendo", None, None))],
                LineAdded(line="diminuendo", start_measure=2, end_measure=3, staff=2),
                id="add_live_line",
            ),
            pytest.param(
                bind_arguments(add_live_text, 6, "con sord.", staff=1),
                [
                    BridgeCall("go_to_measure", (6,)),
                    BridgeCall("go_to_staff", (1,)),
                    BridgeCall("add_text", ("con sord.", "technique")),
                ],
                TextAdded(text="con sord.", style="technique", measure=6, staff=1),
                id="add_live_text",
            ),
            pytest.param(
                bind_arguments(set_live_clef, 9, "treble_8vb", staff=3),
                [
                    BridgeCall("go_to_measure", (9,)),
                    BridgeCall("go_to_staff", (3,)),
                    BridgeCall("set_clef", ("treble_8vb",)),
                ],
                ClefSet(clef="treble_8vb", measure=9, staff=3),
                id="set_live_clef",
            ),
        ],
    )
    async def test_tool_asks_bridge_in_order_and_returns_its_reply(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        call: ToolCall,
        expected_calls: list[BridgeCall],
        reply: BaseModel,
    ) -> None:
        # Arrange
        connected_bridge.reply(expected_calls[-1].method, reply)

        # Act
        result = await call(context)

        # Assert
        assert result is reply
        assert connected_bridge.calls == expected_calls

    @pytest.mark.anyio()
    async def test_append_measures_defaults_to_one(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        await append_live_measures(context)

        # Assert
        assert connected_bridge.calls == [BridgeCall("append_measures", (1,))]


class TestManipulationNavigationErrors:
    """A tool that cannot reach its measure must not change anything."""

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(bind_arguments(add_live_note, 99, 60), id="add_live_note"),
            pytest.param(
                bind_arguments(add_live_rehearsal_mark, 99, "A"),
                id="add_live_rehearsal_mark",
            ),
            pytest.param(
                bind_arguments(add_live_chord_symbol, 99, "C7"),
                id="add_live_chord_symbol",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 99, "p"),
                id="add_live_dynamic",
            ),
            pytest.param(
                bind_arguments(set_live_barline, 99, "final"),
                id="set_live_barline",
            ),
            pytest.param(
                bind_arguments(set_live_key_signature, 99, 1),
                id="set_live_key_signature",
            ),
            pytest.param(
                bind_arguments(set_live_time_signature, 99, 3, 4),
                id="set_live_time_signature",
            ),
            pytest.param(bind_arguments(set_live_tempo, 99, 100), id="set_live_tempo"),
            pytest.param(
                bind_arguments(transpose_passage, 99, 100, 0, 2),
                id="transpose_passage",
            ),
        ],
    )
    async def test_tool_with_measure_error_raises_it_and_writes_nothing(
        self, connected_bridge: FakeBridge, context: ScoreContext, call: ToolCall
    ) -> None:
        # Arrange
        connected_bridge.fail("go_to_measure", NAVIGATION_ERROR)

        # Act
        with pytest.raises(ToolError, match=NAVIGATION_ERROR):
            await call(context)

        # Assert
        assert connected_bridge.calls == [BridgeCall("go_to_measure", (99,))]

    @pytest.mark.anyio()
    async def test_tool_with_staff_error_raises_it_and_writes_nothing(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("go_to_staff", "No staff 7")

        # Act
        with pytest.raises(ToolError, match="No staff 7"):
            await add_live_dynamic(context, 1, "mf", staff=7)

        # Assert
        assert connected_bridge.calls == [
            BridgeCall("go_to_measure", (1,)),
            BridgeCall("go_to_staff", (7,)),
        ]


class TestTransposePassage:
    @pytest.mark.anyio()
    async def test_transpose_with_failed_selection_raises_without_transposing(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("select_range", "Invalid range")

        # Act
        with pytest.raises(ToolError, match="Invalid range"):
            await transpose_passage(context, 1, 4, 0, 5)

        # Assert
        assert connected_bridge.calls_to("transpose") == []

    @pytest.mark.anyio()
    async def test_transpose_single_measure_selects_that_measure(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        await transpose_passage(context, 5, 5, 0, 2)

        # Assert
        assert connected_bridge.calls_to("select_range") == [
            BridgeCall("select_range", (5, 5, 0, 0))
        ]


# ── Rhythm, percussion and beat placement ────────────────────────────

EIGHTH = Duration(numerator=1, denominator=8)
SIXTEENTH = Duration(numerator=1, denominator=16)


class TestPercussionTools:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("call", "expected_calls", "reply"),
        [
            pytest.param(
                bind_arguments(add_live_rest, 2, 1, 8, staff=1, beat=2),
                [
                    BridgeCall("go_to_measure", (2,)),
                    BridgeCall("go_to_staff", (1,)),
                    BridgeCall("go_to_beat", (BeatPosition(beat=2),)),
                    BridgeCall("add_rest", (EIGHTH, True)),
                ],
                RestAdded(measure=2, staff=1, duration=EIGHTH),
                id="add_live_rest",
            ),
            pytest.param(
                bind_arguments(
                    add_live_tuplet, 3, [60, None, 62, 64, 65, 67], 6, 4, 1, 16
                ),
                [
                    BridgeCall("go_to_measure", (3,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall(
                        "add_tuplet",
                        ([60, None, 62, 64, 65, 67], 6, 4, SIXTEENTH),
                    ),
                ],
                TupletAdded(
                    measure=3, staff=0, actual=6, normal=4, unit=SIXTEENTH, notes=6
                ),
                id="add_live_tuplet-sextuplet",
            ),
            pytest.param(
                bind_arguments(set_live_tremolo, 1, 4, "buzz", staff=2),
                [BridgeCall("set_tremolo", (1, 4, 2, "buzz", 3, None))],
                TremoloSet(
                    kind="buzz",
                    strokes=-1,
                    start_measure=1,
                    end_measure=4,
                    staff=2,
                    beat=None,
                    notes=16,
                ),
                id="set_live_tremolo",
            ),
            pytest.param(
                bind_arguments(add_live_grace_notes, 5, "drag", beat=3),
                [
                    BridgeCall("go_to_measure", (5,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall("go_to_beat", (BeatPosition(beat=3),)),
                    BridgeCall("add_grace_notes", ("drag",)),
                ],
                GraceNotesAdded(ornament="drag", measure=5, staff=0, notes=2),
                id="add_live_grace_notes",
            ),
            pytest.param(
                bind_arguments(add_live_sticking, 1, "RLRRLRLL"),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall(
                        "add_sticking", (["R", "L", "R", "R", "L", "R", "L", "L"],)
                    ),
                ],
                StickingAdded(sticking=["R", "L"], measure=1, staff=0, notes=8),
                id="add_live_sticking-characters",
            ),
            pytest.param(
                bind_arguments(add_live_sticking, 1, " RH LH  RH "),
                [
                    BridgeCall("go_to_measure", (1,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall("add_sticking", (["RH", "LH", "RH"],)),
                ],
                StickingAdded(sticking=["RH"], measure=1, staff=0, notes=3),
                id="add_live_sticking-groups",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 7, "fp", beat=4),
                [
                    BridgeCall("go_to_measure", (7,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall("go_to_beat", (BeatPosition(beat=4),)),
                    BridgeCall("add_dynamic", ("fp",)),
                ],
                DynamicAdded(dynamic="fp", measure=7),
                id="add_live_dynamic-on-beat",
            ),
            pytest.param(
                bind_arguments(
                    add_live_line, 4, 4, "crescendo", start_beat=3, end_beat=4
                ),
                [
                    BridgeCall(
                        "add_line",
                        (
                            4,
                            4,
                            0,
                            "crescendo",
                            BeatPosition(beat=3),
                            BeatPosition(beat=4),
                        ),
                    )
                ],
                LineAdded(
                    line="crescendo",
                    start_measure=4,
                    end_measure=4,
                    staff=0,
                    start_beat=BeatPosition(beat=3),
                    end_beat=BeatPosition(beat=4),
                ),
                id="add_live_line-over-beats",
            ),
            pytest.param(
                bind_arguments(add_live_note, 2, 38, 1, 16, beat=2),
                [
                    BridgeCall("go_to_measure", (2,)),
                    BridgeCall("go_to_staff", (0,)),
                    BridgeCall("go_to_beat", (BeatPosition(beat=2),)),
                    BridgeCall("add_note", (38, SIXTEENTH, True)),
                ],
                NoteAdded(measure=2, staff=0, pitch=38, duration=SIXTEENTH),
                id="add_live_note-on-beat",
            ),
        ],
    )
    async def test_tool_asks_bridge_in_order_and_returns_its_reply(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        call: ToolCall,
        expected_calls: list[BridgeCall],
        reply: BaseModel,
    ) -> None:
        # Arrange
        connected_bridge.reply(expected_calls[-1].method, reply)

        # Act
        result = await call(context)

        # Assert
        assert result is reply
        assert connected_bridge.calls == expected_calls

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("call", "expected_error"),
        [
            pytest.param(
                bind_arguments(add_live_tuplet, 1, [60, 62]),
                "pitches must hold 3 pitches or nulls, one per note.",
                id="tuplet-too-few-pitches",
            ),
            pytest.param(
                bind_arguments(add_live_tuplet, 1, [60, 62, 200]),
                "pitch must be between 0 and 127.",
                id="tuplet-pitch-out-of-range",
            ),
            pytest.param(
                bind_arguments(add_live_tuplet, 1, [], actual=0),
                "actual and normal must be >= 1.",
                id="tuplet-zero-actual",
            ),
            pytest.param(
                bind_arguments(add_live_rest, 1, 0),
                "numerator and denominator must be >= 1.",
                id="rest-zero-numerator",
            ),
            pytest.param(
                bind_arguments(set_live_tremolo, 1, 2, strokes=-2),
                "strokes must be >= 0.",
                id="tremolo-negative-strokes",
            ),
            pytest.param(
                bind_arguments(add_live_grace_notes, 1, "flam", beat=0),
                "beat must be >= 1.",
                id="grace-beat-zero",
            ),
            pytest.param(
                bind_arguments(add_live_sticking, 1, "   "),
                "sticking must not be empty.",
                id="sticking-blank",
            ),
            pytest.param(
                bind_arguments(add_live_dynamic, 1, "p", beat=0),
                "beat must be >= 1.",
                id="dynamic-beat-zero",
            ),
            pytest.param(
                bind_arguments(add_live_line, 1, 1, "crescendo", end_beat=0),
                "end_beat must be >= 1.",
                id="line-end-beat-zero",
            ),
            pytest.param(
                bind_arguments(
                    add_live_line, 2, 2, "diminuendo", start_beat=3, end_beat=2
                ),
                "end_beat must come after start_beat within one measure.",
                id="line-beats-backwards",
            ),
        ],
    )
    async def test_tool_with_invalid_argument_raises_without_touching_score(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        call: ToolCall,
        expected_error: str,
    ) -> None:
        # Act
        with pytest.raises(ToolError, match=re.escape(expected_error)):
            await call(context)

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    async def test_beat_the_application_cannot_reach_stops_the_edit(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("go_to_beat", "Measure 3 has no beat 5")

        # Act
        with pytest.raises(ToolError, match="has no beat 5"):
            await add_live_dynamic(context, 3, "ff", beat=5)

        # Assert
        assert connected_bridge.calls_to("add_dynamic") == []

    @pytest.mark.anyio()
    async def test_without_beat_tools_do_not_move_to_one(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act: MuseScore cannot move to a beat, so beat-less calls must not try
        await add_live_dynamic(context, 3, "ff")
        await add_live_note(context, 3, 60)

        # Assert
        assert connected_bridge.calls_to("go_to_beat") == []


# ── Positions inside a measure ───────────────────────────────────────


class TestParseBeat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(3, BeatPosition(beat=3), id="int"),
            pytest.param("3", BeatPosition(beat=3), id="digits"),
            pytest.param(
                "2&", BeatPosition(beat=2, subdivision=2, partial=2), id="and"
            ),
            pytest.param(
                "2+", BeatPosition(beat=2, subdivision=2, partial=2), id="plus"
            ),
            pytest.param(
                " 2 AND ", BeatPosition(beat=2, subdivision=2, partial=2), id="word"
            ),
            pytest.param("4e", BeatPosition(beat=4, subdivision=4, partial=2), id="e"),
            pytest.param("4a", BeatPosition(beat=4, subdivision=4, partial=4), id="a"),
            pytest.param(
                "1trip", BeatPosition(beat=1, subdivision=3, partial=2), id="trip"
            ),
            pytest.param(
                "1Let", BeatPosition(beat=1, subdivision=3, partial=3), id="let"
            ),
            pytest.param(
                "4:3/5",
                BeatPosition(beat=4, subdivision=5, partial=3),
                id="quintuplet",
            ),
            pytest.param(
                "2 : 6 / 6",
                BeatPosition(beat=2, subdivision=6, partial=6),
                id="spaced-sextuplet",
            ),
            pytest.param(None, None, id="none"),
        ],
    )
    def test_reads_counts_and_fractions(
        self, value: int | str | None, expected: BeatPosition | None
    ) -> None:
        # Act / Assert
        assert parse_beat(value) == expected

    @pytest.mark.parametrize(
        ("value", "error"),
        [
            pytest.param(0, "beat must be >= 1.", id="zero"),
            pytest.param("0&", "beat must be >= 1.", id="zero-and"),
            pytest.param("2:4/3", "partial must be between 1", id="partial-too-big"),
            pytest.param("2:0/3", "partial must be between 1", id="partial-zero"),
            pytest.param("2x", "beat must be a beat number", id="unknown-syllable"),
            pytest.param("&2", "beat must be a beat number", id="backwards"),
        ],
    )
    def test_refuses_what_is_not_a_position(self, value: int | str, error: str) -> None:
        # Act / Assert
        with pytest.raises(ToolError, match=re.escape(error)):
            parse_beat(value)

    def test_partials_of_a_beat_order_by_where_they_start(self) -> None:
        # Arrange: 1, 1e, 1trip, 1&, 1let, 1a, 2
        names = ["1", "1e", "1trip", "1&", "1let", "1a", "2"]

        # Act
        starts = [position.start() for name in names if (position := parse_beat(name))]

        # Assert
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)


class TestSubBeatPositions:
    @pytest.mark.anyio()
    async def test_note_on_the_and_of_two(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        await add_live_note(context, 3, 38, 1, 8, beat="2&")

        # Assert
        assert connected_bridge.calls_to("go_to_beat") == [
            BridgeCall("go_to_beat", (BeatPosition(beat=2, subdivision=2, partial=2),))
        ]

    @pytest.mark.anyio()
    async def test_accent_on_the_last_triplet_partial_of_every_measure(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        await set_live_articulation(context, 1, 8, "accent", beat="4let")

        # Assert
        assert connected_bridge.calls == [
            BridgeCall(
                "set_articulation",
                (
                    1,
                    8,
                    0,
                    "accent",
                    BeatPosition(beat=4, subdivision=3, partial=3),
                    False,
                ),
            )
        ]

    @pytest.mark.anyio()
    async def test_hairpin_within_one_beat_is_allowed(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act: from the e of 4 to the end of the a of 4
        await add_live_line(context, 2, 2, "crescendo", start_beat="4e", end_beat="4a")

        # Assert
        assert connected_bridge.calls_to("add_line") == [
            BridgeCall(
                "add_line",
                (
                    2,
                    2,
                    0,
                    "crescendo",
                    BeatPosition(beat=4, subdivision=4, partial=2),
                    BeatPosition(beat=4, subdivision=4, partial=4),
                ),
            )
        ]

    @pytest.mark.anyio()
    async def test_hairpin_ending_where_it_starts_is_refused(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act: ends with the e of 4, which ends where the & of 4 starts
        with pytest.raises(ToolError, match="end_beat must come after start_beat"):
            await add_live_line(
                context, 2, 2, "crescendo", start_beat="4&", end_beat="4e"
            )

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    async def test_unreadable_position_touches_nothing(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act
        with pytest.raises(ToolError, match="got 'two'"):
            await add_live_dynamic(context, 1, "f", beat="two")

        # Assert
        assert connected_bridge.calls == []


class TestNoteheadNumbers:
    @pytest.mark.anyio()
    async def test_notehead_number_reaches_the_bridge(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Act: VDL's left-hand hit on the a of 3 in every measure
        await set_live_notehead(context, 1, 4, 31, beat="3a")

        # Assert
        assert connected_bridge.calls == [
            BridgeCall(
                "set_notehead",
                (1, 4, 0, 31, BeatPosition(beat=3, subdivision=4, partial=4)),
            )
        ]

    @pytest.mark.anyio()
    @pytest.mark.parametrize("number", [-1, 128])
    async def test_notehead_number_out_of_range_touches_nothing(
        self, connected_bridge: FakeBridge, context: ScoreContext, number: int
    ) -> None:
        # Act
        with pytest.raises(ToolError, match="between 0 and 127"):
            await set_live_notehead(context, 1, 1, number)

        # Assert
        assert connected_bridge.calls == []


class TestWriteLivePassage:
    @pytest.mark.anyio()
    async def test_passage_from_json_reaches_the_bridge_in_one_call(
        self,
        registry: BridgeRegistry,
        connected_bridge: FakeBridge,
        context: ScoreContext,
    ) -> None:
        # Arrange: a flam accent, a triplet starting on the & of 2 and a rest
        server = create_server(registry)
        sixteenth = {"numerator": 1, "denominator": 16}
        eighth = {"numerator": 1, "denominator": 8}
        triplet = {"duration": eighth, "tuplet": {"actual": 3, "normal": 2}}
        arguments = {
            "measure": 2,
            "events": [
                {
                    "pitch": 72,
                    "duration": sixteenth,
                    "notehead": 31,
                    "articulations": ["accent"],
                    "grace": "flam",
                    "sticking": "L",
                },
                {"pitch": 72, **triplet, "beat": "2&"},
                {"pitch": 72, **triplet},
                {"pitch": [60, 64], **triplet, "tremolo": "buzz"},
                {"pitch": None, "duration": eighth, "measure": 3, "beat": 1},
            ],
        }

        # Act
        await server.call_tool("write_live_passage", arguments, context=context)

        # Assert
        assert connected_bridge.calls[0] == BridgeCall("go_to_measure", (2,))
        (passage,) = connected_bridge.calls_to("write_passage")
        events: list[PassageEvent] = passage.arguments[0]
        assert [event.beat for event in events] == [
            None,
            BeatPosition(beat=2, subdivision=2, partial=2),
            None,
            None,
            BeatPosition(beat=1),
        ]
        assert events[0].notehead == 31
        assert events[3].pitch == [60, 64]
        assert events[4].pitch is None

    @pytest.mark.anyio()
    async def test_unreadable_beat_touches_nothing(
        self,
        registry: BridgeRegistry,
        connected_bridge: FakeBridge,
        context: ScoreContext,
    ) -> None:
        # Arrange
        server = create_server(registry)
        event = {"pitch": 60, "duration": {"numerator": 1, "denominator": 4}}

        # Act
        with pytest.raises(ToolError, match="got 'two'"):
            await server.call_tool(
                "write_live_passage",
                {"measure": 1, "events": [{**event, "beat": "two"}]},
                context=context,
            )

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("events", "error"),
        [
            pytest.param([], "events must not be empty.", id="empty"),
            pytest.param(
                [PassageEvent(pitch=[], duration=QUARTER)],
                "Event 1: a chord needs at least one pitch.",
                id="empty-chord",
            ),
            pytest.param(
                [
                    PassageEvent(pitch=60, duration=QUARTER),
                    PassageEvent(pitch=128, duration=QUARTER),
                ],
                "Event 2: pitch must be between 0 and 127.",
                id="pitch",
            ),
            pytest.param(
                [PassageEvent(duration=Duration(numerator=0, denominator=4))],
                "Event 1: duration must be a positive fraction.",
                id="duration",
            ),
            pytest.param(
                [PassageEvent(pitch=60, duration=QUARTER, measure=0)],
                "Event 1: measure must be >= 1.",
                id="measure",
            ),
            pytest.param(
                [PassageEvent(pitch=60, duration=QUARTER, notehead=128)],
                "Event 1: notehead number must be between 0 and 127.",
                id="notehead",
            ),
            pytest.param(
                [
                    PassageEvent(
                        pitch=60, duration=QUARTER, tremolo="single", tremolo_strokes=-1
                    )
                ],
                "Event 1: tremolo_strokes must be >= 0.",
                id="strokes",
            ),
            pytest.param(
                [PassageEvent(pitch=60, duration=QUARTER, sticking=" ")],
                "Event 1: sticking must not be blank.",
                id="sticking",
            ),
        ],
    )
    async def test_invalid_event_touches_nothing(
        self,
        connected_bridge: FakeBridge,
        context: ScoreContext,
        events: list[PassageEvent],
        error: str,
    ) -> None:
        # Act
        with pytest.raises(ToolError, match=f"^{re.escape(error)}$"):
            await write_live_passage(context, 1, events)

        # Assert
        assert connected_bridge.calls == []

    @pytest.mark.anyio()
    async def test_application_refusal_reaches_the_model(
        self, connected_bridge: FakeBridge, context: ScoreContext
    ) -> None:
        # Arrange
        connected_bridge.fail("write_passage", "mcp-score cannot write passages.")

        # Act / Assert
        with pytest.raises(ToolError, match="cannot write passages"):
            await write_live_passage(
                context, 1, [PassageEvent(pitch=60, duration=QUARTER)]
            )
