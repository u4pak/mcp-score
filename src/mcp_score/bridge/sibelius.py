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
from mcp_score.bridge.passage import PassageWritten, tuplet_indexes
from mcp_score.bridge.remote_control import (
    DEFAULT_CLIENT_NAME,
    HANDSHAKE_VERSION,
    HandshakeError,
)
from mcp_score.bridge.results import (
    ArticulationSet,
    BarlineSet,
    BeatPosition,
    ChordSymbolAdded,
    ClefSet,
    CursorInfo,
    CursorPosition,
    Duration,
    DynamicAdded,
    Element,
    GraceNotesAdded,
    KeySignatureSet,
    LineAdded,
    MeasuresAppended,
    Note,
    NoteAdded,
    NoteheadSet,
    RehearsalMarkAdded,
    RestAdded,
    ScoreInfo,
    SelectedRange,
    SelectionProperties,
    StickingAdded,
    TempoSet,
    TextAdded,
    TimeSignatureSet,
    Transposed,
    TremoloSet,
    TupletAdded,
)
from mcp_score.bridge.websocket import DEFAULT_HOST, WebSocketBridge

if TYPE_CHECKING:
    from mcp_score.bridge.base import CommandResult
    from mcp_score.bridge.passage import PassageEvent
    from mcp_score.bridge.results import (
        Articulation,
        Clef,
        GraceOrnament,
        LineType,
        Notehead,
        TextStyle,
        TremoloKind,
    )
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

BUZZ_ROLL = -1
"""ManuScript's SingleTremolos value for a z on the stem."""

MAX_TREMOLO_STROKES = 7

# Grace notes for each ornament: how many, whether slashed (acciaccatura)
# and their length: a flam is one eighth-note acciaccatura, a drag two and
# a ruff three sixteenth-note grace notes.
GRACE_ORNAMENTS: dict[GraceOrnament, tuple[int, bool, int]] = {
    "flam": (1, True, 128),
    "drag": (2, False, 64),
    "ruff": (3, False, 64),
}

REHEARSAL_MARK = re.compile(r"[A-Za-z]{1,2}|\d+")
"""Rehearsal marks Sibelius can write as given: letters or a number."""

DYNAMIC = re.compile(r"[pmfrszn]+")

# ManuScript's articulation numbers ("Articulations" in the guide's Global
# Constants); Sibelius calls a fermata a pause.
ARTICULATIONS: dict[Articulation, int] = {
    "staccato": 1,
    "staccatissimo": 2,
    "wedge": 3,
    "tenuto": 4,
    "accent": 5,
    "marcato": 6,
    "harmonic": 7,
    "plus": 8,
    "up_bow": 9,
    "down_bow": 10,
    "square_fermata": 12,
    "fermata": 13,
    "triangle_fermata": 14,
}

# ManuScript's notehead style indices ("Note Style Names"); Sibelius calls
# slash noteheads beat noteheads.
NOTEHEADS: dict[Notehead, int] = {
    "normal": 0,
    "cross": 1,
    "diamond": 2,
    "slash_without_stem": 3,
    "slash": 4,
    "cross_or_diamond": 5,
    "black_and_white_diamond": 6,
    "headless": 7,
    "stemless": 8,
    "silent": 9,
    "cue": 10,
    "slashed": 11,
    "back_slashed": 12,
    "arrow_down": 13,
    "arrow_up": 14,
    "inverted_triangle": 15,
}

# Sibelius line style identifiers ("Line Styles").
LINE_STYLES: dict[LineType, str] = {
    "slur": "line.staff.slur.up",
    "slur_below": "line.staff.slur.down",
    "crescendo": "line.staff.hairpin.crescendo",
    "diminuendo": "line.staff.hairpin.diminuendo",
    "decrescendo": "line.staff.hairpin.diminuendo",
    "trill": "line.staff.trill",
    "ottava": "line.staff.octava.plus8",
    "ottava_bassa": "line.staff.octava.minus8",
    "quindicesima": "line.staff.octava.plus15",
    "quindicesima_bassa": "line.staff.octava.minus15",
    "pedal": "line.staff.pedal",
    "glissando": "line.staff.gliss.straight",
}

# Sibelius staff text style identifiers ("Text Styles").
TEXT_STYLES: dict[TextStyle, str] = {
    "technique": "text.staff.technique",
    "expression": "text.staff.expression",
    "plain": "text.staff.plain",
    "boxed": "text.staff.boxed",
}

# Sibelius clef style identifiers ("Clef Styles").
CLEFS: dict[Clef, str] = {
    "treble": "clef.treble",
    "treble_8vb": "clef.treble.down.8",
    "treble_8va": "clef.treble.up.8",
    "bass": "clef.bass",
    "bass_8vb": "clef.bass.down.8",
    "alto": "clef.alto",
    "tenor": "clef.tenor",
    "soprano": "clef.soprano",
    "mezzo_soprano": "clef.soprano.mezzo",
    "baritone": "clef.baritone.f",
    "percussion": "clef.percussion",
}
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
    SET_ARTICULATION = "SetArticulation"
    SET_NOTEHEAD = "SetNotehead"
    ADD_LINE = "AddLine"
    ADD_STAFF_TEXT = "AddStaffText"
    SET_CLEF = "SetClef"
    BEAT_TO_POSITION = "BeatToPosition"
    ADD_REST = "AddRest"
    ADD_TUPLET = "AddTuplet"
    SET_TREMOLO = "SetTremolo"
    ADD_GRACE_NOTES = "AddGraceNotes"
    ADD_STICKING = "AddSticking"
    WRITE_PASSAGE = "WritePassage"


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


class _NotesChanged(_PluginReply):
    notes: int


class _LineReply(_PluginReply):
    start_measure: int
    end_measure: int
    staff: int


class _TupletPlaced(_NotePlaced):
    notes: int


class _PassageReply(_NotePlaced):
    events: int
    notes: int


class _CountAt(_PluginReply):
    """How many things were written at a measure and staff."""

    measure: int
    staff: int
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
        placed = await self._run(
            _NotePlaced,
            PluginMethod.ADD_NOTE,
            self._measure,
            self._staff,
            self._position,
            pitch,
            _length(duration, "note"),
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

    # ── Notation on existing notes, lines, text and clefs ───────────

    async def set_articulation(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        articulation: Articulation,
        beat: BeatPosition | None,
        remove: bool,
    ) -> ArticulationSet:
        reply = await self._run(
            _NotesChanged,
            PluginMethod.SET_ARTICULATION,
            start_measure,
            end_measure,
            staff,
            *_offset(None if beat is None else beat.start()),
            ARTICULATIONS[articulation],
            not remove,
        )
        return ArticulationSet(
            articulation=articulation,
            removed=remove,
            start_measure=start_measure,
            end_measure=end_measure,
            staff=staff,
            beat=beat,
            notes=reply.notes,
        )

    async def set_notehead(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        notehead: Notehead | int,
        beat: BeatPosition | None,
    ) -> NoteheadSet:
        reply = await self._run(
            _NotesChanged,
            PluginMethod.SET_NOTEHEAD,
            start_measure,
            end_measure,
            staff,
            *_offset(None if beat is None else beat.start()),
            notehead if isinstance(notehead, int) else NOTEHEADS[notehead],
        )
        return NoteheadSet(
            notehead=notehead,
            start_measure=start_measure,
            end_measure=end_measure,
            staff=staff,
            beat=beat,
            notes=reply.notes,
        )

    async def add_line(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        line: LineType,
        start_beat: BeatPosition | None = None,
        end_beat: BeatPosition | None = None,
    ) -> LineAdded:
        reply = await self._run(
            _LineReply,
            PluginMethod.ADD_LINE,
            start_measure,
            end_measure,
            staff,
            *_offset(None if start_beat is None else start_beat.start()),
            *_offset(None if end_beat is None else end_beat.end()),
            LINE_STYLES[line],
        )
        return LineAdded(
            line=line,
            start_measure=reply.start_measure,
            end_measure=reply.end_measure,
            staff=reply.staff,
            start_beat=start_beat,
            end_beat=end_beat,
        )

    async def add_text(self, text: str, style: TextStyle) -> TextAdded:
        # A backslash starts a Sibelius formatting command; write it literally.
        position = await self._run(
            CursorPosition,
            PluginMethod.ADD_STAFF_TEXT,
            self._measure,
            self._staff,
            self._position,
            text.replace("\\", "\\\\"),
            TEXT_STYLES[style],
        )
        return TextAdded(
            text=text, style=style, measure=position.measure, staff=position.staff
        )

    async def set_clef(self, clef: Clef) -> ClefSet:
        position = await self._run(
            CursorPosition,
            PluginMethod.SET_CLEF,
            self._measure,
            self._staff,
            self._position,
            CLEFS[clef],
        )
        return ClefSet(clef=clef, measure=position.measure, staff=position.staff)

    # ── Rhythm and percussion notation ───────────────────────────────

    async def go_to_beat(self, beat: BeatPosition) -> CursorPosition:
        placed = await self._run(
            _NotePlaced,
            PluginMethod.BEAT_TO_POSITION,
            self._measure,
            self._staff,
            *_offset(beat.start()),
        )
        self._position = placed.position
        return CursorPosition(measure=placed.measure, staff=placed.staff)

    async def add_rest(
        self, duration: Duration, advance_cursor: bool = True
    ) -> RestAdded:
        placed = await self._run(
            _NotePlaced,
            PluginMethod.ADD_REST,
            self._measure,
            self._staff,
            self._position,
            _length(duration, "rest"),
        )
        if advance_cursor:
            self._measure = placed.measure
            self._position = placed.position
        return RestAdded(measure=self._measure, staff=self._staff, duration=duration)

    async def add_tuplet(
        self, pitches: list[int | None], actual: int, normal: int, unit: Duration
    ) -> TupletAdded:
        if len(pitches) != actual:
            raise BridgeError(
                f"A tuplet of {actual} needs {actual} pitches or rests, "
                f"not {len(pitches)}."
            )
        placed = await self._run(
            _TupletPlaced,
            PluginMethod.ADD_TUPLET,
            self._measure,
            self._staff,
            self._position,
            [-1 if pitch is None else pitch for pitch in pitches],
            actual,
            normal,
            _length(unit, "tuplet note"),
        )
        self._measure = placed.measure
        self._position = placed.position
        return TupletAdded(
            measure=self._measure,
            staff=self._staff,
            actual=actual,
            normal=normal,
            unit=unit,
            notes=placed.notes,
        )

    async def set_tremolo(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        kind: TremoloKind,
        strokes: int,
        beat: BeatPosition | None,
    ) -> TremoloSet:
        if kind == "buzz":
            strokes = BUZZ_ROLL
        elif not 0 <= strokes <= MAX_TREMOLO_STROKES:
            raise BridgeError(
                f"Sibelius draws 0 to {MAX_TREMOLO_STROKES} tremolo strokes."
            )
        reply = await self._run(
            _NotesChanged,
            PluginMethod.SET_TREMOLO,
            start_measure,
            end_measure,
            staff,
            *_offset(None if beat is None else beat.start()),
            kind == "double",
            strokes,
        )
        return TremoloSet(
            kind=kind,
            strokes=strokes,
            start_measure=start_measure,
            end_measure=end_measure,
            staff=staff,
            beat=beat,
            notes=reply.notes,
        )

    async def add_grace_notes(self, ornament: GraceOrnament) -> GraceNotesAdded:
        count, slashed, length = GRACE_ORNAMENTS[ornament]
        reply = await self._run(
            _CountAt,
            PluginMethod.ADD_GRACE_NOTES,
            self._measure,
            self._staff,
            self._position,
            count,
            slashed,
            length,
        )
        return GraceNotesAdded(
            ornament=ornament,
            measure=reply.measure,
            staff=reply.staff,
            notes=reply.notes,
        )

    async def add_sticking(self, sticking: list[str]) -> StickingAdded:
        reply = await self._run(
            _CountAt,
            PluginMethod.ADD_STICKING,
            self._measure,
            self._staff,
            self._position,
            # A backslash starts a Sibelius formatting command.
            [letter.replace("\\", "\\\\") for letter in sticking],
        )
        return StickingAdded(
            sticking=sticking,
            measure=reply.measure,
            staff=reply.staff,
            notes=reply.notes,
        )

    async def write_passage(self, events: list[PassageEvent]) -> PassageWritten:
        if not events:
            raise BridgeError("A passage needs at least one event.")
        try:
            indexes = tuplet_indexes(events)
        except ValueError as error:
            raise BridgeError(str(error)) from None
        payload = [
            _passage_event(number, event, index)
            for number, (event, index) in enumerate(
                zip(events, indexes, strict=True), start=1
            )
        ]
        reply = await self._run(
            _PassageReply,
            PluginMethod.WRITE_PASSAGE,
            self._measure,
            self._staff,
            self._position,
            payload,
        )
        self._measure = reply.measure
        self._position = reply.position
        return PassageWritten(
            measure=reply.measure,
            staff=reply.staff,
            events=reply.events,
            notes=reply.notes,
        )


def _offset(beats: Fraction | None) -> tuple[int, int]:
    """A point in a measure, in beats, as the numerator and denominator the
    plug-in takes; (-1, 1) stands for no point (every note, or the bar's end).

    The plug-in turns it into Sibelius units with the measure's beat length,
    which only it knows.
    """
    if beats is None:
        return -1, 1
    return beats.numerator, beats.denominator


NO_SINGLE_TREMOLO = -2
"""What the plug-in takes for "leave the stem's tremolo alone"."""


def _passage_event(
    number: int, event: PassageEvent, tuplet_index: int | None
) -> dict[str, Any]:
    """The Dictionary the plug-in's WritePassage reads for one event.

    Raises:
        BridgeError: When Sibelius cannot write the event as given.
    """
    pitches = (
        []
        if event.pitch is None
        else [event.pitch]
        if isinstance(event.pitch, int)
        else event.pitch
    )
    rest = not pitches
    if rest and (
        event.notehead is not None
        or event.articulations
        or event.tremolo is not None
        or event.grace is not None
        or event.sticking
    ):
        raise BridgeError(
            f"Event {number}: a rest takes no notehead, articulation, tremolo, "
            "grace notes or sticking."
        )
    if event.dynamic and not DYNAMIC.fullmatch(event.dynamic):
        raise BridgeError(
            f"Event {number}: Sibelius writes dynamics with the letters p, m, f, "
            f"r, s, z and n; {event.dynamic!r} is not one."
        )
    single_tremolo, double_tremolo = NO_SINGLE_TREMOLO, -1
    if event.tremolo == "buzz":
        single_tremolo = BUZZ_ROLL
    elif event.tremolo is not None:
        if not 0 <= event.tremolo_strokes <= MAX_TREMOLO_STROKES:
            raise BridgeError(
                f"Event {number}: Sibelius draws 0 to {MAX_TREMOLO_STROKES} "
                "tremolo strokes."
            )
        if event.tremolo == "double":
            double_tremolo = event.tremolo_strokes
        else:
            single_tremolo = event.tremolo_strokes
    grace_count, grace_slashed, grace_length = (
        (0, False, 0) if event.grace is None else GRACE_ORNAMENTS[event.grace]
    )
    offset_num, offset_den = _offset(None if event.beat is None else event.beat.start())
    notehead = event.notehead
    return {
        "bar": event.measure or 0,
        "offset_num": offset_num,
        "offset_den": offset_den,
        "pitches": pitches,
        "duration": _length(event.duration, "note"),
        "tuplet_actual": 0 if event.tuplet is None else event.tuplet.actual,
        "tuplet_normal": 0 if event.tuplet is None else event.tuplet.normal,
        "tuplet_index": -1 if tuplet_index is None else tuplet_index,
        "notehead": (
            -1
            if notehead is None
            else notehead
            if isinstance(notehead, int)
            else NOTEHEADS[notehead]
        ),
        "articulations": [ARTICULATIONS[name] for name in event.articulations],
        "single_tremolo": single_tremolo,
        "double_tremolo": double_tremolo,
        "grace_count": grace_count,
        "grace_slashed": grace_slashed,
        "grace_duration": grace_length,
        "sticking": (event.sticking or "").replace("\\", "\\\\"),
        "dynamic": event.dynamic or "",
    }


def _length(duration: Duration, what: str) -> int:
    """*duration* in Sibelius's units (1/256 of a quarter note).

    Raises:
        BridgeError: When it is not a whole number of units.
    """
    length = Fraction(duration.numerator, duration.denominator) * WHOLE_NOTE
    if length.denominator != 1 or length <= 0:
        raise BridgeError(
            f"Sibelius cannot write a {what} of {duration.numerator}/"
            f"{duration.denominator} of a whole note."
        )
    return length.numerator


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
