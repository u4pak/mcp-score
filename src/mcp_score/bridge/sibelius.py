"""Bridge to Sibelius through Sibelius Connect (experimental).

Sibelius 2024.3 and later serve Sibelius Connect, a WebSocket API on port
1898 by default, enabled on the Input Devices page of Sibelius's
preferences. It takes two kinds of message: ``invokeCommands`` runs
command IDs (the menu commands, without parameters) on the current
selection, and ``invokePlugin`` calls a method of a ManuScript plug-in
with arguments. This bridge runs Sibelius's own commands where one does
the job (undo, barlines) and does everything that needs a bar, a staff or
a value through the ``McpScoreBridge`` plug-in (``sibelius/plugin/``),
which ``mcp-score install-sibelius-plugin`` installs.

The plug-in keeps no state: the bridge tracks the cursor (measure, staff
and position in the bar) and the last selected range, and passes them to
every call. Positions are in Sibelius's units, 1/256 of a quarter note.

Handshake: the client sends ``connect`` with ``clientName``,
``handshakeVersion`` and the ``plugins`` it will call; Sibelius asks the
user to allow the connection and answers ``{"sessionToken": ...}``. The
token can be sent with a later ``connect`` to skip the question while
Sibelius keeps running. Support is experimental: the bridge and plug-in
follow the ManuScript Language Guide but have not been run against a
real Sibelius.
"""

from __future__ import annotations

import re
from enum import StrEnum
from fractions import Fraction
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from mcp_score.bridge.base import BridgeError
from mcp_score.bridge.remote_control import (
    DEFAULT_CLIENT_NAME,
    HANDSHAKE_VERSION,
    HandshakeError,
)
from mcp_score.bridge.results import (
    BarlineSet,
    ChordSymbolAdded,
    CursorInfo,
    CursorPosition,
    Duration,
    DynamicAdded,
    Element,
    KeySignatureSet,
    MeasuresAppended,
    Note,
    NoteAdded,
    RehearsalMarkAdded,
    ScoreInfo,
    SelectedRange,
    SelectionProperties,
    TempoSet,
    TimeSignatureSet,
    Transposed,
)
from mcp_score.bridge.websocket import DEFAULT_HOST, WebSocketBridge

if TYPE_CHECKING:
    from mcp_score.bridge.base import CommandResult
    from mcp_score.bridge.websocket import WebSocketTransport

__all__ = ["DEFAULT_PORT", "PLUGIN_NAME", "PluginMethod", "SibeliusBridge"]

DEFAULT_PORT = 1898
"""Sibelius Connect's default port; configurable in Sibelius's preferences."""

APPLICATION_NAME = "Sibelius"

PLUGIN_NAME = "McpScoreBridge"
"""The bridge plug-in's file name without ``.plg``, which names it to Sibelius."""

PLUGIN_HINT = (
    f"Is the {PLUGIN_NAME} plug-in installed (mcp-score install-sibelius-plugin) "
    "and Sibelius restarted since?"
)

# Protocol vocabulary.
MESSAGE_CONNECT = "connect"
MESSAGE_INVOKE_COMMANDS = "invokeCommands"
MESSAGE_INVOKE_PLUGIN = "invokePlugin"

# Sibelius command IDs (ManuScript Language Guide, "Command IDs").
COMMAND_UNDO = "undo"
BARLINE_COMMANDS: dict[str, str] = {
    "normal": "barline_normal",
    "double": "barline_double",
    "final": "barline_final",
    "dashed": "barline_dashed",
    "tick": "barline_ticks",
    "short": "barline_short",
    "startRepeat": "barline_start_repeat",
    "endRepeat": "barline_end_repeat",
}

WHOLE_NOTE = 1024
"""A whole note in Sibelius's units (1/256 of a quarter note)."""

# ManuScript interval types, for Selection.Transpose.
INTERVAL_MINOR = 4
INTERVAL_MAJOR = 5
INTERVAL_PERFECT = 5
INTERVAL_AUGMENTED = 6

# The conventionally spelled interval for each number of semitones in an
# octave, as a 0-based degree and an interval type.
SEMITONE_INTERVALS: tuple[tuple[int, int], ...] = (
    (0, INTERVAL_PERFECT),
    (1, INTERVAL_MINOR),
    (1, INTERVAL_MAJOR),
    (2, INTERVAL_MINOR),
    (2, INTERVAL_MAJOR),
    (3, INTERVAL_PERFECT),
    (3, INTERVAL_AUGMENTED),
    (4, INTERVAL_PERFECT),
    (5, INTERVAL_MINOR),
    (5, INTERVAL_MAJOR),
    (6, INTERVAL_MINOR),
    (6, INTERVAL_MAJOR),
)

# Semitones above C, and MuseScore's tonal pitch class, of each natural
# note from C to B.
NATURAL_SEMITONES = (0, 2, 4, 5, 7, 9, 11)
NATURAL_TONAL_PITCH_CLASSES = (14, 16, 18, 13, 15, 17, 19)

REHEARSAL_MARK = re.compile(r"[A-Za-z]{1,2}|\d+")
"""Rehearsal marks Sibelius can write as given: letters or a number."""

DYNAMIC = re.compile(r"[pmfrszn]+")
"""Dynamics spelled with the letters the Music text font draws as dynamics."""


class PluginMethod(StrEnum):
    """Methods of the McpScoreBridge plug-in."""

    PING = "Ping"
    GET_SCORE = "GetScore"
    GET_CURSOR_INFO = "GetCursorInfo"
    GO_TO = "GoTo"
    SELECT_RANGE = "SelectRange"
    ADD_NOTE = "AddNote"
    ADD_REHEARSAL_MARK = "AddRehearsalMark"
    ADD_CHORD_SYMBOL = "AddChordSymbol"
    ADD_DYNAMIC = "AddDynamic"
    SET_KEY_SIGNATURE = "SetKeySignature"
    SET_TIME_SIGNATURE = "SetTimeSignature"
    SET_TEMPO = "SetTempo"
    APPEND_BARS = "AppendBars"
    TRANSPOSE = "Transpose"


# ── What the plug-in returns where no result model fits ───────────────


class _PluginReply(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _NoteReply(_PluginReply):
    pitch: int
    diatonic_pitch: int
    name: str


class _NoteRestReply(_PluginReply):
    type: str
    position: int
    duration: int
    notes: list[_NoteReply]


class _CursorReply(_PluginReply):
    measure: int
    staff: int
    position: int
    time_signature_denominator: int
    element: _NoteRestReply | None = None


class _NotePlaced(_PluginReply):
    """Where the next note goes after the one just added."""

    measure: int
    staff: int
    position: int


class _RehearsalMarkReply(_PluginReply):
    text: str
    measure: int


class _TempoReply(_PluginReply):
    bpm: int
    measure: int


class _TransposeReply(_PluginReply):
    notes: int


class SibeliusBridge(WebSocketBridge):
    """Sibelius Connect client driving Sibelius commands and the bridge plug-in."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_name: str = DEFAULT_CLIENT_NAME,
    ) -> None:
        super().__init__(APPLICATION_NAME, host, port)
        self.client_name = client_name
        self._session_token: str | None = None
        self._measure = 1
        self._staff = 0
        self._position = 0
        """Where the next note goes, in 1/256 quarter notes from the bar start."""
        self._selection: SelectedRange | None = None

    # ── Handshake ───────────────────────────────────────────────────

    async def _on_connected(self, transport: WebSocketTransport) -> None:
        connect_message: dict[str, Any] = {
            "message": MESSAGE_CONNECT,
            "clientName": self.client_name,
            "handshakeVersion": HANDSHAKE_VERSION,
        }
        if self._session_token is None:
            connect_message["plugins"] = [PLUGIN_NAME]
        else:
            connect_message["sessionToken"] = self._session_token
        reply = await transport.request(connect_message)
        session_token = reply.get("sessionToken")
        if not isinstance(session_token, str) or not session_token:
            self._session_token = None
            raise HandshakeError(f"unexpected reply to connect: {reply}")
        self._session_token = session_token

    # ── Messages ────────────────────────────────────────────────────

    async def send_command(
        self, action: str, params: dict[str, Any] | None = None
    ) -> CommandResult:
        """Run one Sibelius command ID; Sibelius commands take no parameters."""
        if params:
            raise BridgeError(f"Sibelius command {action!r} takes no parameters.")
        return await self.invoke_commands(action)

    async def invoke_commands(self, *command_ids: str) -> CommandResult:
        """Run Sibelius command IDs, in order, on the current selection."""
        reply = await self._exchange(
            {"message": MESSAGE_INVOKE_COMMANDS, "commands": list(command_ids)}
        )
        if not reply.get("result"):
            raise BridgeError(f"Sibelius did not run {', '.join(command_ids)}.")
        return reply

    async def invoke_plugin(self, method: str, *args: Any) -> object:
        """Call a method of the bridge plug-in and return what it returned.

        Raises:
            BridgeError: When Sibelius cannot call the method, or the
                plug-in reports that it cannot do what was asked.
        """
        reply = await self._exchange(
            {
                "message": MESSAGE_INVOKE_PLUGIN,
                "name": PLUGIN_NAME,
                "method": method,
                "args": list(args),
            }
        )
        if not reply.get("result"):
            raise BridgeError(
                f"Sibelius could not call {PLUGIN_NAME}.{method}. {PLUGIN_HINT}"
            )
        # The guide's example reply spells it return_value, its prose returnValue.
        value: object = reply.get("return_value", reply.get("returnValue"))
        if not isinstance(value, dict):
            return value
        fields = cast("dict[str, object]", value)
        if "error" in fields:
            raise BridgeError(str(fields["error"]))
        return fields

    async def _run[R: BaseModel](
        self, reply_type: type[R], method: PluginMethod, *args: Any
    ) -> R:
        """Call a plug-in method and read its return value as *reply_type*.

        Raises:
            BridgeError: When the value does not have the expected shape,
                which means the plug-in and this bridge disagree.
        """
        value = await self.invoke_plugin(method, *args)
        try:
            return reply_type.model_validate(value)
        except ValidationError as error:
            raise BridgeError(
                f"The {PLUGIN_NAME} plug-in answered {method} with an "
                f"unexpected reply: {error}"
            ) from error

    async def ping(self) -> bool:
        try:
            return await self.invoke_plugin(PluginMethod.PING) == "pong"
        except BridgeError:
            return False

    # ── Reading ─────────────────────────────────────────────────────

    async def get_score(self) -> ScoreInfo:
        return await self._run(ScoreInfo, PluginMethod.GET_SCORE)

    async def get_cursor_info(self) -> CursorInfo:
        reply = await self._run(
            _CursorReply,
            PluginMethod.GET_CURSOR_INFO,
            self._measure,
            self._staff,
            self._position,
        )
        return CursorInfo(
            measure=reply.measure,
            staff=reply.staff,
            voice=1,
            beat=_beat(reply.position, reply.time_signature_denominator),
            tick=reply.position,
            element=None if reply.element is None else _element(reply.element),
        )

    async def get_properties(self) -> SelectionProperties:
        """What is at the cursor, as with MuseScore."""
        return SelectionProperties(cursor=await self.get_cursor_info())

    # ── Navigation and selection ────────────────────────────────────

    async def go_to_measure(self, measure: int) -> CursorPosition:
        return await self._go_to(measure, self._staff)

    async def go_to_staff(self, staff: int) -> CursorPosition:
        return await self._go_to(self._measure, staff)

    async def _go_to(self, measure: int, staff: int) -> CursorPosition:
        """Select the bar in Sibelius and move the cursor there.

        The position in the bar is kept when the bar and staff do not
        change, so consecutive notes in one measure follow each other.
        """
        position = await self._run(CursorPosition, PluginMethod.GO_TO, measure, staff)
        if (position.measure, position.staff) != (self._measure, self._staff):
            self._position = 0
        self._measure = position.measure
        self._staff = position.staff
        return position

    async def select_measure(self) -> CursorPosition:
        position = await self._run(
            CursorPosition, PluginMethod.GO_TO, self._measure, self._staff
        )
        self._selection = SelectedRange(
            start_measure=position.measure,
            end_measure=position.measure,
            start_staff=position.staff,
            end_staff=position.staff,
        )
        return position

    async def select_range(
        self, start_measure: int, end_measure: int, start_staff: int, end_staff: int
    ) -> SelectedRange:
        self._selection = await self._run(
            SelectedRange,
            PluginMethod.SELECT_RANGE,
            start_measure,
            end_measure,
            start_staff,
            end_staff,
        )
        return self._selection

    # ── Writing ─────────────────────────────────────────────────────

    async def add_note(
        self, pitch: int, duration: Duration, advance_cursor: bool = True
    ) -> NoteAdded:
        length = Fraction(duration.numerator, duration.denominator) * WHOLE_NOTE
        if length.denominator != 1 or length <= 0:
            raise BridgeError(
                f"Sibelius cannot write a note of {duration.numerator}/"
                f"{duration.denominator} of a whole note."
            )
        placed = await self._run(
            _NotePlaced,
            PluginMethod.ADD_NOTE,
            self._measure,
            self._staff,
            self._position,
            pitch,
            length.numerator,
        )
        if advance_cursor:
            self._measure = placed.measure
            self._position = placed.position
        return NoteAdded(
            measure=self._measure, staff=self._staff, pitch=pitch, duration=duration
        )

    async def add_rehearsal_mark(self, text: str) -> RehearsalMarkAdded:
        mark = text if REHEARSAL_MARK.fullmatch(text) else ""
        reply = await self._run(
            _RehearsalMarkReply,
            PluginMethod.ADD_REHEARSAL_MARK,
            self._measure,
            mark,
        )
        warning = None
        if reply.text.casefold() != text.casefold():
            warning = (
                "Sibelius rehearsal marks are letters or numbers; it wrote "
                f"{reply.text!r} instead of {text!r}."
            )
        return RehearsalMarkAdded(text=text, measure=reply.measure, warning=warning)

    async def add_chord_symbol(self, text: str) -> ChordSymbolAdded:
        return await self._run(
            ChordSymbolAdded,
            PluginMethod.ADD_CHORD_SYMBOL,
            self._measure,
            self._staff,
            self._position,
            text,
        )

    async def add_dynamic(self, dynamic: str) -> DynamicAdded:
        if not DYNAMIC.fullmatch(dynamic):
            raise BridgeError(
                f"Sibelius writes dynamics with the letters p, m, f, r, s, z "
                f"and n; {dynamic!r} is not one."
            )
        return await self._run(
            DynamicAdded,
            PluginMethod.ADD_DYNAMIC,
            self._measure,
            self._staff,
            self._position,
            dynamic,
        )

    async def set_barline(self, barline_type: str) -> BarlineSet:
        command = BARLINE_COMMANDS.get(barline_type)
        if command is None:
            raise BridgeError(
                f"Unknown barline type {barline_type!r}. "
                f"Supported: {', '.join(BARLINE_COMMANDS)}"
            )
        # The command acts on the selection, so select the cursor's bar.
        position = await self.select_measure()
        await self.invoke_commands(command)
        return BarlineSet(barline_type=barline_type, measure=position.measure)

    async def set_key_signature(self, fifths: int) -> KeySignatureSet:
        if not -7 <= fifths <= 7:
            raise BridgeError("fifths must be between -7 and 7.")
        return await self._run(
            KeySignatureSet,
            PluginMethod.SET_KEY_SIGNATURE,
            self._measure,
            self._staff,
            fifths,
        )

    async def set_time_signature(
        self, numerator: int, denominator: int
    ) -> TimeSignatureSet:
        return await self._run(
            TimeSignatureSet,
            PluginMethod.SET_TIME_SIGNATURE,
            self._measure,
            self._staff,
            numerator,
            denominator,
        )

    async def set_tempo(self, bpm: int, text: str | None = None) -> TempoSet:
        reply = await self._run(
            _TempoReply, PluginMethod.SET_TEMPO, self._measure, bpm, text or ""
        )
        metronome_mark = f"\N{QUARTER NOTE} = {reply.bpm}"
        written = f"{text} {metronome_mark}" if text else metronome_mark
        return TempoSet(bpm=reply.bpm, text=written, measure=reply.measure)

    async def append_measures(self, count: int) -> MeasuresAppended:
        return await self._run(MeasuresAppended, PluginMethod.APPEND_BARS, count)

    async def transpose(self, semitones: int) -> Transposed:
        selection = self._selection
        if selection is None:
            raise BridgeError("Select a range before transposing.")
        degree, interval_type = _interval(semitones)
        reply = await self._run(
            _TransposeReply,
            PluginMethod.TRANSPOSE,
            selection.start_measure,
            selection.end_measure,
            selection.start_staff,
            selection.end_staff,
            degree,
            interval_type,
        )
        return Transposed(semitones=semitones, notes=reply.notes)

    async def undo(self) -> CursorPosition:
        await self.invoke_commands(COMMAND_UNDO)
        return CursorPosition(measure=self._measure, staff=self._staff)


def _interval(semitones: int) -> tuple[int, int]:
    """The 0-based degree (negative is down) and interval type for *semitones*."""
    octaves, step = divmod(abs(semitones), 12)
    degree, interval_type = SEMITONE_INTERVALS[step]
    degree += 7 * octaves
    return (-degree if semitones < 0 else degree), interval_type


def _beat(position: int, denominator: int) -> int | None:
    """The 1-indexed beat *position* falls on, when the beat is a whole unit."""
    if denominator < 1 or WHOLE_NOTE % denominator:
        return None
    return position // (WHOLE_NOTE // denominator) + 1


def _tonal_pitch_class(pitch: int, diatonic_pitch: int) -> int:
    """MuseScore's tonal pitch class for a Sibelius note.

    Sibelius numbers note names 7 per octave (35 is middle C); the
    difference between the MIDI pitch and that natural note is the
    accidental, and each sharp moves the pitch class 7 up the circle.
    """
    octave, letter = divmod(diatonic_pitch, 7)
    natural = 12 * octave + NATURAL_SEMITONES[letter]
    return NATURAL_TONAL_PITCH_CLASSES[letter] + 7 * (pitch - natural)


def _element(note_rest: _NoteRestReply) -> Element:
    length = Fraction(note_rest.duration, WHOLE_NOTE)
    notes = [
        Note(
            pitch=note.pitch,
            tpc=_tonal_pitch_class(note.pitch, note.diatonic_pitch),
            name=note.name,
        )
        for note in note_rest.notes
    ]
    return Element(
        type=note_rest.type,
        notes=notes or None,
        duration=Duration(numerator=length.numerator, denominator=length.denominator),
    )
