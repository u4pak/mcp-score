"""Tests for SibeliusBridge: Sibelius Connect and the bridge plug-in's calls.

The plug-in itself runs inside Sibelius and is not exercised here. These
tests check what the bridge sends (the handshake, command IDs, plug-in
method calls with the cursor it tracks) and how it reads what comes back.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, get_args
from unittest.mock import AsyncMock, patch

import pytest

from mcp_score.bridge import BridgeError
from mcp_score.bridge.passage import PassageEvent
from mcp_score.bridge.remote_control import DEFAULT_CLIENT_NAME, HANDSHAKE_VERSION
from mcp_score.bridge.results import (
    Articulation,
    BeatPosition,
    Clef,
    Duration,
    Element,
    LineType,
    Note,
    Notehead,
    TextStyle,
)
from mcp_score.bridge.sibelius import (
    ARTICULATIONS,
    CLEFS,
    DEFAULT_PORT,
    INTERVAL_AUGMENTED,
    INTERVAL_MAJOR,
    INTERVAL_MINOR,
    INTERVAL_PERFECT,
    LINE_STYLES,
    NOTEHEADS,
    PLUGIN_NAME,
    TEXT_STYLES,
    PluginMethod,
    SibeliusBridge,
)
from tests.fakes import (
    SESSION_TOKEN,
    SIBELIUS_COMMANDS_RUN,
    SIBELIUS_HANDSHAKE,
    WEBSOCKETS_CONNECT,
    fake_connection,
    plugin_reply,
    sent_payloads,
)

if TYPE_CHECKING:
    from unittest.mock import AsyncMock as Connection

QUARTER_NOTE = Duration(numerator=1, denominator=4)


async def _connected_bridge(
    *replies: dict[str, Any],
) -> tuple[SibeliusBridge, Connection]:
    """A bridge past its handshake, whose next replies are *replies*."""
    bridge = SibeliusBridge()
    connection = fake_connection(*SIBELIUS_HANDSHAKE, *replies)
    with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
        assert await bridge.connect()
    return bridge, connection


def _plugin_calls(connection: Connection) -> list[tuple[str, list[Any]]]:
    """The plug-in methods called over *connection*, with their arguments."""
    return [
        (payload["method"], payload["args"])
        for payload in sent_payloads(connection)
        if payload["message"] == "invokePlugin"
    ]


def _at(measure: int, staff: int) -> dict[str, Any]:
    return plugin_reply({"measure": measure, "staff": staff})


# ── Defaults and handshake ───────────────────────────────────────────


class TestSibeliusBridgeDefaults:
    def test_default_bridge_targets_sibelius_connect_port(self) -> None:
        # Arrange / Act
        bridge = SibeliusBridge()

        # Assert
        assert bridge.application_name == "Sibelius"
        assert bridge.uri == f"ws://localhost:{DEFAULT_PORT}"
        assert bridge.client_name == DEFAULT_CLIENT_NAME


class TestSibeliusHandshake:
    @pytest.mark.anyio()
    async def test_first_connect_names_the_plugin_it_will_call(self) -> None:
        # Arrange / Act
        _, connection = await _connected_bridge()

        # Assert
        assert sent_payloads(connection) == [
            {
                "message": "connect",
                "clientName": DEFAULT_CLIENT_NAME,
                "handshakeVersion": HANDSHAKE_VERSION,
                "plugins": [PLUGIN_NAME],
            }
        ]

    @pytest.mark.anyio()
    async def test_reconnect_sends_the_session_token_instead(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge()
        await bridge.disconnect()
        connection = fake_connection(*SIBELIUS_HANDSHAKE)

        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
            # Act
            connected = await bridge.connect()

        # Assert: the user is not asked again
        assert connected is True
        connect_message = sent_payloads(connection)[0]
        assert connect_message["sessionToken"] == SESSION_TOKEN
        assert "plugins" not in connect_message

    @pytest.mark.anyio()
    async def test_reply_without_session_token_fails_and_forgets_token(
        self,
    ) -> None:
        # Arrange
        bridge, _ = await _connected_bridge()
        await bridge.disconnect()
        connection = fake_connection({"message": "refused"})

        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=connection)):
            # Act
            connected = await bridge.connect()

        # Assert: the next attempt starts a fresh handshake
        assert connected is False
        assert bridge.is_connected is False
        retry = fake_connection(*SIBELIUS_HANDSHAKE)
        with patch(WEBSOCKETS_CONNECT, AsyncMock(return_value=retry)):
            await bridge.connect()
        assert sent_payloads(retry)[0]["plugins"] == [PLUGIN_NAME]


# ── Messages ─────────────────────────────────────────────────────────


class TestSibeliusMessages:
    @pytest.mark.anyio()
    async def test_plugin_call_frames_method_and_arguments(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(_at(3, 1))

        # Act
        await bridge.go_to_measure(3)

        # Assert
        assert sent_payloads(connection)[-1] == {
            "message": "invokePlugin",
            "name": PLUGIN_NAME,
            "method": "GoTo",
            "args": [3, 0],
        }

    @pytest.mark.anyio()
    async def test_plugin_error_becomes_bridge_error(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            plugin_reply({"error": "Measure 99 out of range (1-8)"})
        )

        # Act / Assert
        with pytest.raises(BridgeError, match=r"^Measure 99 out of range \(1-8\)$"):
            await bridge.go_to_measure(99)

    @pytest.mark.anyio()
    async def test_uncallable_plugin_points_at_the_installer(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            {"message": "invokePluginResponse", "result": False, "return_value": ""}
        )

        # Act / Assert
        with pytest.raises(BridgeError, match="install-sibelius-plugin"):
            await bridge.get_score()

    @pytest.mark.anyio()
    async def test_return_value_spelled_in_camel_case_is_read(self) -> None:
        # Arrange: the guide's prose spells it returnValue
        bridge, _ = await _connected_bridge(
            {"message": "invokePluginResponse", "result": True, "returnValue": "pong"}
        )

        # Act / Assert
        assert await bridge.ping() is True

    @pytest.mark.anyio()
    async def test_reply_of_wrong_shape_names_the_method(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(plugin_reply({"measure": 1}))

        # Act / Assert
        with pytest.raises(BridgeError, match="answered GoTo with an unexpected"):
            await bridge.go_to_measure(1)

    @pytest.mark.anyio()
    async def test_send_command_runs_a_command_id(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(SIBELIUS_COMMANDS_RUN)

        # Act
        await bridge.send_command("select_all")

        # Assert
        assert sent_payloads(connection)[-1] == {
            "message": "invokeCommands",
            "commands": ["select_all"],
        }

    @pytest.mark.anyio()
    async def test_send_command_refuses_parameters(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="takes no parameters"):
            await bridge.send_command("goto_bar", {"bar": 3})
        assert len(sent_payloads(connection)) == 1  # only the handshake

    @pytest.mark.anyio()
    async def test_ping_failing_returns_false(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            {"message": "invokePluginResponse", "result": False}
        )

        # Act / Assert
        assert await bridge.ping() is False


# ── The cursor the bridge tracks ─────────────────────────────────────


class TestSibeliusCursor:
    @pytest.mark.anyio()
    async def test_notes_in_one_measure_follow_each_other(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            _at(2, 0),
            plugin_reply({"measure": 2, "staff": 0, "position": 256}),
            _at(2, 0),
            plugin_reply({"measure": 2, "staff": 0, "position": 512}),
        )

        # Act: navigate to the same measure before each note, as the tool does
        await bridge.go_to_measure(2)
        await bridge.add_note(60, QUARTER_NOTE)
        await bridge.go_to_measure(2)
        result = await bridge.add_note(62, QUARTER_NOTE)

        # Assert
        assert _plugin_calls(connection)[1::2] == [
            ("AddNote", [2, 0, 0, 60, 256]),
            ("AddNote", [2, 0, 256, 62, 256]),
        ]
        assert (result.measure, result.staff, result.pitch) == (2, 0, 62)

    @pytest.mark.anyio()
    async def test_moving_to_another_measure_starts_at_its_beginning(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "position": 512}),
            _at(4, 0),
            plugin_reply({"measure": 4, "staff": 0, "position": 256}),
        )
        await bridge.add_note(60, Duration(numerator=1, denominator=2))

        # Act
        await bridge.go_to_measure(4)
        await bridge.add_note(64, QUARTER_NOTE)

        # Assert
        assert _plugin_calls(connection)[-1] == ("AddNote", [4, 0, 0, 64, 256])

    @pytest.mark.anyio()
    async def test_note_filling_the_bar_moves_cursor_to_the_next(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            plugin_reply({"measure": 2, "staff": 0, "position": 0})
        )

        # Act
        result = await bridge.add_note(60, Duration(numerator=1, denominator=1))

        # Assert
        assert result.measure == 2

    @pytest.mark.anyio()
    async def test_note_without_advancing_keeps_cursor(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "position": 256}),
            plugin_reply({"measure": 1, "staff": 0, "position": 256}),
        )

        # Act
        await bridge.add_note(60, QUARTER_NOTE, advance_cursor=False)
        await bridge.add_note(64, QUARTER_NOTE)

        # Assert: the second note joins the first as a chord
        assert _plugin_calls(connection)[-1] == ("AddNote", [1, 0, 0, 64, 256])

    @pytest.mark.anyio()
    async def test_note_length_sibelius_cannot_write_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert: 1/3 of a whole note is not a whole number of units
        with pytest.raises(BridgeError, match="cannot write a note of 1/3"):
            await bridge.add_note(60, Duration(numerator=1, denominator=3))
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    async def test_changing_staff_passes_new_staff_with_current_measure(
        self,
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(_at(5, 0), _at(5, 2))
        await bridge.go_to_measure(5)

        # Act
        result = await bridge.go_to_staff(2)

        # Assert
        assert _plugin_calls(connection)[-1] == ("GoTo", [5, 2])
        assert (result.measure, result.staff) == (5, 2)

    @pytest.mark.anyio()
    async def test_undo_runs_the_undo_command_and_reports_cursor(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(_at(3, 1), SIBELIUS_COMMANDS_RUN)
        await bridge.go_to_measure(3)

        # Act
        result = await bridge.undo()

        # Assert
        assert sent_payloads(connection)[-1] == {
            "message": "invokeCommands",
            "commands": ["undo"],
        }
        assert (result.measure, result.staff) == (3, 1)


# ── Reading ──────────────────────────────────────────────────────────


class TestSibeliusReading:
    @pytest.mark.anyio()
    async def test_cursor_info_converts_sibelius_units(self) -> None:
        # Arrange: an F#4-A4 chord, an eighth note long, on beat 3 of a x/4 bar
        bridge, connection = await _connected_bridge(
            plugin_reply(
                {
                    "measure": 1,
                    "staff": 0,
                    "position": 512,
                    "time_signature_denominator": 4,
                    "element": {
                        "type": "NoteRest",
                        "position": 512,
                        "duration": 128,
                        "notes": [
                            {"pitch": 66, "diatonic_pitch": 38, "name": "F#4"},
                            {"pitch": 69, "diatonic_pitch": 40, "name": "A4"},
                        ],
                    },
                }
            )
        )

        # Act
        info = await bridge.get_cursor_info()

        # Assert
        assert _plugin_calls(connection) == [("GetCursorInfo", [1, 0, 0])]
        assert (info.beat, info.tick, info.voice) == (3, 512, 1)
        assert info.element == Element(
            type="NoteRest",
            notes=[
                Note(pitch=66, tpc=20, name="F#4"),
                Note(pitch=69, tpc=17, name="A4"),
            ],
            duration=Duration(numerator=1, denominator=8),
        )

    @pytest.mark.anyio()
    async def test_flat_spelling_gives_flat_pitch_class(self) -> None:
        # Arrange: Bb3 (diatonic B below middle C, one semitone down)
        bridge, _ = await _connected_bridge(
            plugin_reply(
                {
                    "measure": 1,
                    "staff": 0,
                    "position": 0,
                    "time_signature_denominator": 4,
                    "element": {
                        "type": "NoteRest",
                        "position": 0,
                        "duration": 256,
                        "notes": [{"pitch": 58, "diatonic_pitch": 34, "name": "Bb3"}],
                    },
                }
            )
        )

        # Act
        info = await bridge.get_cursor_info()

        # Assert
        assert info.element is not None
        assert info.element.notes == [Note(pitch=58, tpc=12, name="Bb3")]

    @pytest.mark.anyio()
    async def test_rest_and_empty_position_are_told_apart(self) -> None:
        # Arrange
        rest: dict[str, Any] = {
            "type": "NoteRest",
            "position": 0,
            "duration": 1024,
            "notes": [],
        }
        bridge, _ = await _connected_bridge(
            plugin_reply(
                {
                    "measure": 1,
                    "staff": 0,
                    "position": 0,
                    "time_signature_denominator": 8,
                    "element": rest,
                }
            ),
            plugin_reply(
                {
                    "measure": 1,
                    "staff": 0,
                    "position": 0,
                    "time_signature_denominator": 3,
                }
            ),
        )

        # Act
        rest_info = await bridge.get_cursor_info()
        empty_info = await bridge.get_cursor_info()

        # Assert
        assert rest_info.element == Element(
            type="NoteRest", notes=None, duration=Duration(numerator=1, denominator=1)
        )
        assert rest_info.beat == 1
        assert empty_info.element is None
        assert empty_info.beat is None  # no whole beat in a x/3 bar

    @pytest.mark.anyio()
    async def test_selection_properties_carry_the_cursor(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            plugin_reply(
                {
                    "measure": 1,
                    "staff": 0,
                    "position": 0,
                    "time_signature_denominator": 4,
                }
            )
        )

        # Act
        properties = await bridge.get_properties()

        # Assert
        assert properties.cursor is not None
        assert properties.properties is None

    @pytest.mark.anyio()
    async def test_score_info_is_read_as_the_plugin_reports_it(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            plugin_reply(
                {
                    "title": "Sonata",
                    "part_count": 1,
                    "parts": [{"name": "Piano", "start_staff": 0, "end_staff": 1}],
                    "measure_count": 32,
                    "key_signature": -3,
                    "time_signature": {"numerator": 3, "denominator": 4},
                }
            )
        )

        # Act
        score = await bridge.get_score()

        # Assert
        assert (score.title, score.measure_count, score.key_signature) == (
            "Sonata",
            32,
            -3,
        )
        assert score.parts[0].end_staff == 1


# ── Writing ──────────────────────────────────────────────────────────


class TestSibeliusWriting:
    @pytest.mark.anyio()
    async def test_barline_selects_the_bar_then_runs_its_command(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            _at(4, 0), _at(4, 0), SIBELIUS_COMMANDS_RUN
        )
        await bridge.go_to_measure(4)

        # Act
        result = await bridge.set_barline("endRepeat")

        # Assert
        assert sent_payloads(connection)[-2:] == [
            {
                "message": "invokePlugin",
                "name": PLUGIN_NAME,
                "method": "GoTo",
                "args": [4, 0],
            },
            {"message": "invokeCommands", "commands": ["barline_end_repeat"]},
        ]
        assert (result.barline_type, result.measure) == ("endRepeat", 4)

    @pytest.mark.anyio()
    async def test_barline_without_a_command_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="Unknown barline type 'dotted'"):
            await bridge.set_barline("dotted")
        assert len(sent_payloads(connection)) == 1

    @pytest.mark.anyio()
    async def test_rehearsal_letter_is_written_as_given(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"text": "B", "measure": 1})
        )

        # Act
        result = await bridge.add_rehearsal_mark("B")

        # Assert
        assert _plugin_calls(connection) == [("AddRehearsalMark", [1, "B"])]
        assert (result.text, result.warning) == ("B", None)

    @pytest.mark.anyio()
    async def test_rehearsal_word_falls_back_to_numbering_with_warning(
        self,
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"text": "C", "measure": 1})
        )

        # Act
        result = await bridge.add_rehearsal_mark("Intro")

        # Assert
        assert _plugin_calls(connection) == [("AddRehearsalMark", [1, ""])]
        assert result.text == "Intro"
        assert result.warning is not None
        assert "wrote 'C' instead of 'Intro'" in result.warning

    @pytest.mark.anyio()
    async def test_dynamic_with_letters_outside_the_music_font_is_refused(
        self,
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="'cresc.' is not one"):
            await bridge.add_dynamic("cresc.")
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    async def test_dynamic_is_added_at_the_cursor(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"dynamic": "sfz", "measure": 1})
        )

        # Act
        result = await bridge.add_dynamic("sfz")

        # Assert
        assert _plugin_calls(connection) == [("AddDynamic", [1, 0, 0, "sfz"])]
        assert result.dynamic == "sfz"

    @pytest.mark.anyio()
    async def test_key_signature_beyond_seven_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="between -7 and 7"):
            await bridge.set_key_signature(8)
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    async def test_tempo_reports_the_marking_as_written(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"bpm": 96, "measure": 1}),
            plugin_reply({"bpm": 120, "measure": 1}),
        )

        # Act
        with_text = await bridge.set_tempo(96, "Andante")
        without_text = await bridge.set_tempo(120)

        # Assert
        assert _plugin_calls(connection) == [
            ("SetTempo", [1, 96, "Andante"]),
            ("SetTempo", [1, 120, ""]),
        ]
        assert with_text.text == "Andante \N{QUARTER NOTE} = 96"
        assert without_text.text == "\N{QUARTER NOTE} = 120"


# ── Transposition ────────────────────────────────────────────────────


class TestSibeliusTranspose:
    @pytest.mark.anyio()
    async def test_transpose_without_a_selection_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="Select a range"):
            await bridge.transpose(2)
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("semitones", "degree", "interval_type"),
        [
            (1, 1, INTERVAL_MINOR),
            (5, 3, INTERVAL_PERFECT),
            (6, 3, INTERVAL_AUGMENTED),
            (-4, -2, INTERVAL_MAJOR),
            (14, 8, INTERVAL_MAJOR),
            (-12, -7, INTERVAL_PERFECT),
        ],
    )
    async def test_semitones_become_a_conventionally_spelled_interval(
        self, semitones: int, degree: int, interval_type: int
    ) -> None:
        # Arrange
        selected = {
            "start_measure": 2,
            "end_measure": 5,
            "start_staff": 1,
            "end_staff": 1,
        }
        bridge, connection = await _connected_bridge(
            plugin_reply(selected), plugin_reply({"notes": 12})
        )
        await bridge.select_range(2, 5, 1, 1)

        # Act
        result = await bridge.transpose(semitones)

        # Assert
        assert _plugin_calls(connection)[-1] == (
            PluginMethod.TRANSPOSE,
            [2, 5, 1, 1, degree, interval_type],
        )
        assert (result.semitones, result.notes) == (semitones, 12)


# ── Articulations, noteheads, lines, text and clefs ──────────────────


class TestSibeliusNotationVocabulary:
    @pytest.mark.parametrize(
        ("mapping", "names", "aliases"),
        [
            pytest.param(ARTICULATIONS, Articulation, 0, id="articulations"),
            pytest.param(NOTEHEADS, Notehead, 0, id="noteheads"),
            # decrescendo and diminuendo are the same hairpin
            pytest.param(LINE_STYLES, LineType, 1, id="lines"),
            pytest.param(TEXT_STYLES, TextStyle, 0, id="text-styles"),
            pytest.param(CLEFS, Clef, 0, id="clefs"),
        ],
    )
    def test_every_name_a_tool_accepts_has_a_sibelius_value(
        self, mapping: dict[str, object], names: Any, aliases: int
    ) -> None:
        # Act
        accepted = set(get_args(names.__value__))

        # Assert: no tool argument can reach the bridge without a mapping,
        # and no two names share a value unless one is a known alias
        assert set(mapping) == accepted
        assert len(set(mapping.values())) == len(mapping) - aliases


class TestSibeliusNotation:
    @pytest.mark.anyio()
    async def test_articulation_passes_manuscript_number_and_beat(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(plugin_reply({"notes": 3}))

        # Act
        result = await bridge.set_articulation(
            2, 4, 1, "fermata", BeatPosition(beat=3), False
        )

        # Assert: beat 3 starts 2 beats in; fermata is ManuScript's PauseArtic
        # (13); True turns it on
        assert _plugin_calls(connection) == [
            ("SetArticulation", [2, 4, 1, 2, 1, 13, True])
        ]
        assert (result.articulation, result.removed, result.notes) == (
            "fermata",
            False,
            3,
        )

    @pytest.mark.anyio()
    async def test_removing_articulation_on_every_beat(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(plugin_reply({"notes": 8}))

        # Act
        result = await bridge.set_articulation(1, 1, 0, "staccato", None, True)

        # Assert: a -1 offset means every note, False turns it off
        assert _plugin_calls(connection) == [
            ("SetArticulation", [1, 1, 0, -1, 1, 1, False])
        ]
        assert (result.removed, result.beat) == (True, None)

    @pytest.mark.anyio()
    async def test_notehead_passes_manuscript_style_index(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(plugin_reply({"notes": 12}))

        # Act
        result = await bridge.set_notehead(5, 8, 0, "slash", None)

        # Assert: Sibelius calls a slash notehead a beat notehead (4)
        assert _plugin_calls(connection) == [("SetNotehead", [5, 8, 0, -1, 1, 4])]
        assert result.notes == 12

    @pytest.mark.anyio()
    async def test_line_passes_sibelius_style_id(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"start_measure": 3, "end_measure": 6, "staff": 2})
        )

        # Act
        result = await bridge.add_line(3, 6, 2, "ottava_bassa")

        # Assert
        assert _plugin_calls(connection) == [
            ("AddLine", [3, 6, 2, -1, 1, -1, 1, "line.staff.octava.minus8"])
        ]
        assert (result.line, result.start_measure, result.end_measure) == (
            "ottava_bassa",
            3,
            6,
        )

    @pytest.mark.anyio()
    async def test_text_goes_at_the_cursor_with_backslashes_kept_literal(
        self,
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            _at(4, 1),
            plugin_reply({"measure": 4, "staff": 1}),
        )
        await bridge.go_to_measure(4)

        # Act
        result = await bridge.add_text("a\\b", "expression")

        # Assert
        assert _plugin_calls(connection)[-1] == (
            "AddStaffText",
            [4, 1, 0, "a\\\\b", "text.staff.expression"],
        )
        assert (result.text, result.measure, result.staff) == ("a\\b", 4, 1)

    @pytest.mark.anyio()
    async def test_clef_goes_at_the_cursor(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            _at(9, 2), plugin_reply({"measure": 9, "staff": 2})
        )
        await bridge.go_to_staff(2)

        # Act
        result = await bridge.set_clef("treble_8vb")

        # Assert
        assert _plugin_calls(connection)[-1] == (
            "SetClef",
            [9, 2, 0, "clef.treble.down.8"],
        )
        assert result.clef == "treble_8vb"

    @pytest.mark.anyio()
    async def test_plugin_refusal_of_a_passage_reaches_the_caller(self) -> None:
        # Arrange
        bridge, _ = await _connected_bridge(
            plugin_reply({"error": "Measure 40 out of range (1-32)"})
        )

        # Act / Assert
        with pytest.raises(BridgeError, match="Measure 40 out of range"):
            await bridge.add_line(38, 40, 0, "crescendo")


# ── Rhythm and percussion notation ───────────────────────────────────


class TestSibeliusPercussion:
    @pytest.mark.anyio()
    async def test_beat_moves_the_cursor_for_the_next_note(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            _at(2, 0),
            plugin_reply({"measure": 2, "staff": 0, "position": 512}),
            plugin_reply({"measure": 2, "staff": 0, "position": 576}),
        )
        await bridge.go_to_measure(2)

        # Act
        await bridge.go_to_beat(BeatPosition(beat=3))
        await bridge.add_note(38, Duration(numerator=1, denominator=16))

        # Assert
        assert _plugin_calls(connection)[1:] == [
            ("BeatToPosition", [2, 0, 2, 1]),
            ("AddNote", [2, 0, 512, 38, 64]),
        ]

    @pytest.mark.anyio()
    async def test_rest_advances_the_cursor_like_a_note(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "position": 128}),
            plugin_reply({"measure": 1, "staff": 0, "position": 256}),
        )

        # Act
        rest = await bridge.add_rest(Duration(numerator=1, denominator=8))
        await bridge.add_note(38, Duration(numerator=1, denominator=8))

        # Assert
        assert _plugin_calls(connection) == [
            ("AddRest", [1, 0, 0, 128]),
            ("AddNote", [1, 0, 128, 38, 128]),
        ]
        assert rest.duration == Duration(numerator=1, denominator=8)

    @pytest.mark.anyio()
    async def test_tuplet_sends_rests_as_negative_pitches(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "position": 256, "notes": 3})
        )

        # Act
        result = await bridge.add_tuplet(
            [60, None, 64], 3, 2, Duration(numerator=1, denominator=8)
        )

        # Assert
        assert _plugin_calls(connection) == [
            ("AddTuplet", [1, 0, 0, [60, -1, 64], 3, 2, 128])
        ]
        assert (result.measure, result.notes) == (1, 3)

    @pytest.mark.anyio()
    async def test_tuplet_with_wrong_number_of_pitches_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="needs 5 pitches or rests, not 4"):
            await bridge.add_tuplet(
                [60, 60, 60, 60], 5, 4, Duration(numerator=1, denominator=16)
            )
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("kind", "strokes", "between_notes", "sent_strokes"),
        [
            pytest.param("single", 3, False, 3, id="single"),
            pytest.param("double", 2, True, 2, id="double"),
            pytest.param("buzz", 3, False, -1, id="buzz-is-z-on-stem"),
            pytest.param("single", 0, False, 0, id="remove"),
        ],
    )
    async def test_tremolo_kinds(
        self, kind: Any, strokes: int, between_notes: bool, sent_strokes: int
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(plugin_reply({"notes": 4}))

        # Act
        result = await bridge.set_tremolo(1, 2, 0, kind, strokes, BeatPosition(beat=1))

        # Assert
        assert _plugin_calls(connection) == [
            ("SetTremolo", [1, 2, 0, 0, 1, between_notes, sent_strokes])
        ]
        assert (result.kind, result.strokes, result.notes) == (kind, sent_strokes, 4)

    @pytest.mark.anyio()
    async def test_tremolo_beyond_seven_strokes_is_refused(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match="0 to 7 tremolo strokes"):
            await bridge.set_tremolo(1, 1, 0, "single", 8, None)
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("ornament", "arguments"),
        [
            pytest.param("flam", [1, True, 128], id="flam"),
            pytest.param("drag", [2, False, 64], id="drag"),
            pytest.param("ruff", [3, False, 64], id="ruff"),
        ],
    )
    async def test_grace_note_ornaments(
        self, ornament: Any, arguments: list[Any]
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "notes": arguments[0]})
        )

        # Act
        result = await bridge.add_grace_notes(ornament)

        # Assert: count, slashed and length follow the cursor's position
        assert _plugin_calls(connection) == [("AddGraceNotes", [1, 0, 0, *arguments])]
        assert result.notes == arguments[0]

    @pytest.mark.anyio()
    async def test_sticking_reports_how_many_notes_got_a_letter(self) -> None:
        # Arrange: only three notes left for four letters
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "notes": 3})
        )

        # Act
        result = await bridge.add_sticking(["R", "L", "R", "R"])

        # Assert
        assert _plugin_calls(connection) == [
            ("AddSticking", [1, 0, 0, ["R", "L", "R", "R"]])
        ]
        assert (result.sticking, result.notes) == (["R", "L", "R", "R"], 3)

    @pytest.mark.anyio()
    async def test_hairpin_between_beats(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"start_measure": 4, "end_measure": 5, "staff": 0})
        )

        # Act
        result = await bridge.add_line(
            4, 5, 0, "decrescendo", BeatPosition(beat=3), BeatPosition(beat=1)
        )

        # Assert: from 2 beats into measure 4 to the end of beat 1 (1 beat into
        # measure 5), as Sibelius's diminuendo hairpin
        assert _plugin_calls(connection) == [
            ("AddLine", [4, 5, 0, 2, 1, 1, 1, "line.staff.hairpin.diminuendo"])
        ]
        assert (result.line, result.start_beat, result.end_beat) == (
            "decrescendo",
            BeatPosition(beat=3),
            BeatPosition(beat=1),
        )


class TestSibeliusSubBeatOffsets:
    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("position", "offset"),
        [
            pytest.param(BeatPosition(beat=1), [0, 1], id="downbeat"),
            pytest.param(
                BeatPosition(beat=2, subdivision=2, partial=2), [3, 2], id="and-of-2"
            ),
            pytest.param(
                BeatPosition(beat=3, subdivision=4, partial=4), [11, 4], id="a-of-3"
            ),
            pytest.param(
                BeatPosition(beat=1, subdivision=3, partial=3), [2, 3], id="let-of-1"
            ),
            pytest.param(
                BeatPosition(beat=4, subdivision=5, partial=3),
                [17, 5],
                id="quintuplet-3-of-4",
            ),
        ],
    )
    async def test_position_reaches_the_plugin_as_an_exact_fraction_of_beats(
        self, position: BeatPosition, offset: list[int]
    ) -> None:
        # Arrange: the plug-in turns beats into units with the bar's beat length
        bridge, connection = await _connected_bridge(
            plugin_reply({"measure": 1, "staff": 0, "position": 0})
        )

        # Act
        await bridge.go_to_beat(position)

        # Assert
        assert _plugin_calls(connection) == [("BeatToPosition", [1, 0, *offset])]

    @pytest.mark.anyio()
    async def test_line_ends_where_its_last_partial_ends(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            plugin_reply({"start_measure": 2, "end_measure": 2, "staff": 0})
        )

        # Act: from the e of 4 to the end of the a of 4
        await bridge.add_line(
            2,
            2,
            0,
            "crescendo",
            BeatPosition(beat=4, subdivision=4, partial=2),
            BeatPosition(beat=4, subdivision=4, partial=4),
        )

        # Assert: 3 1/4 beats in to 4 beats in
        assert _plugin_calls(connection) == [
            ("AddLine", [2, 2, 0, 13, 4, 4, 1, "line.staff.hairpin.crescendo"])
        ]


class TestSibeliusNoteheadNumbers:
    @pytest.mark.anyio()
    async def test_notehead_number_is_sent_as_is(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(plugin_reply({"notes": 1}))

        # Act: VDL's left-hand shot
        result = await bridge.set_notehead(2, 2, 0, 51, BeatPosition(beat=1))

        # Assert
        assert _plugin_calls(connection) == [("SetNotehead", [2, 2, 0, 0, 1, 51])]
        assert result.notehead == 51


# ── Passages ─────────────────────────────────────────────────────────


def _passage(*fields: dict[str, Any]) -> list[PassageEvent]:
    return [PassageEvent.model_validate(event) for event in fields]


SIXTEENTH_FIELDS: dict[str, int] = {"numerator": 1, "denominator": 16}
EIGHTH_FIELDS: dict[str, int] = {"numerator": 1, "denominator": 8}

PASSAGE_DONE = plugin_reply(
    {"measure": 2, "staff": 0, "position": 256, "events": 1, "notes": 1}
)


def _sent_events(connection: Connection) -> list[dict[str, Any]]:
    (method, arguments) = _plugin_calls(connection)[-1]
    assert method == "WritePassage"
    return arguments[3]


class TestSibeliusWritePassage:
    @pytest.mark.anyio()
    async def test_vdl_snare_figure_reaches_the_plugin_in_one_call(self) -> None:
        # Arrange: a left-hand flammed accent, a right-hand buzz, a rest
        bridge, connection = await _connected_bridge(PASSAGE_DONE)
        events = _passage(
            {
                "pitch": 72,
                "duration": SIXTEENTH_FIELDS,
                "notehead": 31,
                "articulations": ["accent"],
                "grace": "flam",
                "sticking": "L",
                "dynamic": "f",
            },
            {
                "pitch": 72,
                "duration": SIXTEENTH_FIELDS,
                "tremolo": "buzz",
                "sticking": "R",
            },
            {"pitch": None, "duration": EIGHTH_FIELDS},
        )

        # Act
        await bridge.write_passage(events)

        # Assert
        calls = _plugin_calls(connection)
        assert len(calls) == 1
        assert calls[0][1][:3] == [1, 0, 0]
        first, buzz, rest = _sent_events(connection)
        assert first == {
            "bar": 0,
            "offset_num": -1,
            "offset_den": 1,
            "pitches": [72],
            "duration": 64,
            "tuplet_actual": 0,
            "tuplet_normal": 0,
            "tuplet_index": -1,
            "notehead": 31,
            "articulations": [5],
            "single_tremolo": -2,
            "double_tremolo": -1,
            "grace_count": 1,
            "grace_slashed": True,
            "grace_duration": 128,
            "sticking": "L",
            "dynamic": "f",
        }
        assert (buzz["single_tremolo"], buzz["sticking"]) == (-1, "R")
        assert (rest["pitches"], rest["duration"]) == ([], 128)

    @pytest.mark.anyio()
    async def test_triplet_jump_chord_and_named_notehead(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(PASSAGE_DONE)
        triplet = {"duration": EIGHTH_FIELDS, "tuplet": {"actual": 3, "normal": 2}}
        events = _passage(
            {"pitch": 60, "measure": 4, "beat": "2&", **triplet},
            {"pitch": [60, 64], "notehead": "cross", **triplet},
            {"pitch": 62, "tremolo": "double", "tremolo_strokes": 2, **triplet},
        )

        # Act
        await bridge.write_passage(events)

        # Assert
        first, chord, last = _sent_events(connection)
        assert (first["bar"], first["offset_num"], first["offset_den"]) == (4, 3, 2)
        assert [event["tuplet_index"] for event in (first, chord, last)] == [0, 1, 2]
        assert (first["tuplet_actual"], first["tuplet_normal"]) == (3, 2)
        assert (chord["pitches"], chord["notehead"]) == ([60, 64], 1)
        assert (last["double_tremolo"], last["single_tremolo"]) == (2, -2)

    @pytest.mark.anyio()
    async def test_cursor_continues_after_the_passage(self) -> None:
        # Arrange
        bridge, connection = await _connected_bridge(
            PASSAGE_DONE, plugin_reply({"measure": 2, "staff": 0, "position": 320})
        )
        await bridge.write_passage(
            _passage({"pitch": 60, "duration": {"numerator": 5, "denominator": 4}})
        )

        # Act
        await bridge.add_note(60, Duration(numerator=1, denominator=16))

        # Assert
        assert _plugin_calls(connection)[-1] == ("AddNote", [2, 0, 256, 60, 64])

    @pytest.mark.anyio()
    @pytest.mark.parametrize(
        ("events", "message"),
        [
            pytest.param([], "at least one event", id="empty"),
            pytest.param(
                [{"pitch": None, "duration": EIGHTH_FIELDS, "sticking": "R"}],
                "Event 1: a rest takes no",
                id="rest-with-sticking",
            ),
            pytest.param(
                [{"pitch": 60, "duration": EIGHTH_FIELDS, "dynamic": "loud"}],
                "Event 1: Sibelius writes dynamics",
                id="unwritable-dynamic",
            ),
            pytest.param(
                [
                    {
                        "pitch": 60,
                        "duration": EIGHTH_FIELDS,
                        "tremolo": "single",
                        "tremolo_strokes": 9,
                    }
                ],
                "0 to 7 tremolo strokes",
                id="too-many-strokes",
            ),
            pytest.param(
                [{"pitch": 60, "duration": {"numerator": 1, "denominator": 12}}],
                "cannot write a note of 1/12",
                id="unwritable-length",
            ),
            pytest.param(
                [
                    {
                        "pitch": 60,
                        "duration": EIGHTH_FIELDS,
                        "tuplet": {"actual": 3, "normal": 2},
                    }
                ],
                "The last tuplet needs 3 notes",
                id="incomplete-tuplet",
            ),
        ],
    )
    async def test_unwritable_passage_is_refused_before_sending(
        self, events: list[dict[str, Any]], message: str
    ) -> None:
        # Arrange
        bridge, connection = await _connected_bridge()

        # Act / Assert
        with pytest.raises(BridgeError, match=re.escape(message)):
            await bridge.write_passage(_passage(*events))
        assert _plugin_calls(connection) == []

    @pytest.mark.anyio()
    async def test_plugin_failure_names_the_event(self) -> None:
        # Arrange
        failure = (
            "Event 3: it does not fit in what is left of measure 1. "
            "The events before it were written."
        )
        bridge, _ = await _connected_bridge(plugin_reply({"error": failure}))

        # Act / Assert
        with pytest.raises(BridgeError, match="^Event 3: it does not fit"):
            await bridge.write_passage(
                _passage({"pitch": 60, "duration": {"numerator": 1, "denominator": 1}})
            )
