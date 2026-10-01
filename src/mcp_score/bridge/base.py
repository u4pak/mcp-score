"""The interface every score application bridge implements.

A bridge talks to one running notation application. The MCP tools only
depend on this interface, so an application is supported by adding a
bridge, not by touching the tools. Every operation returns one of the
result models in :mod:`mcp_score.bridge.results`; an operation the
application cannot perform raises :class:`BridgeError` with the
application's explanation, which the tools report as a tool error.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_score.bridge.results import (
        Articulation,
        ArticulationSet,
        BarlineSet,
        BeatPosition,
        ChordSymbolAdded,
        Clef,
        ClefSet,
        CursorInfo,
        CursorPosition,
        Duration,
        DynamicAdded,
        GraceNotesAdded,
        GraceOrnament,
        KeySignatureSet,
        LineAdded,
        LineType,
        MeasuresAppended,
        NoteAdded,
        Notehead,
        NoteheadSet,
        RehearsalMarkAdded,
        RestAdded,
        ScoreInfo,
        SelectedRange,
        SelectionProperties,
        StickingAdded,
        TempoSet,
        TextAdded,
        TextStyle,
        TimeSignatureSet,
        Transposed,
        TremoloKind,
        TremoloSet,
        TupletAdded,
    )

__all__ = ["BridgeError", "CommandResult", "ScoreBridge"]

type CommandResult = dict[str, Any]
"""An application's decoded JSON reply, before a bridge reads a result out of it."""


class BridgeError(Exception):
    """The application could not do what was asked; the message says why.

    Raised for the application's own refusals (``details`` carries any
    other fields of its reply), for operations its protocol cannot
    express, and for a connection that could not be made or kept.
    """

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ScoreBridge(ABC):
    """Interface for communicating with a score notation application.

    Every operation returns the result model that describes what the
    application reported, and raises :class:`BridgeError` when it could
    not do what was asked.
    """

    @property
    @abstractmethod
    def application_name(self) -> str:
        """Human-readable name of the application, for messages to the model."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether commands can be sent right now."""

    @property
    def content_reading_limitation(self) -> str | None:
        """Why reading score content is limited, or ``None`` when it is not.

        Analysis tools attach this as a warning so the model knows the data
        it got is the best the application can give.
        """
        return None

    # ── Connection ──────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the application. Returns whether it succeeded."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection to the application."""

    @abstractmethod
    async def ping(self) -> bool:
        """Whether the application answers."""

    @abstractmethod
    async def send_command(
        self, action: str, params: dict[str, Any] | None = None
    ) -> CommandResult:
        """Send an application-native command and return its raw reply."""

    # ── Reading ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_score(self) -> ScoreInfo:
        """Metadata about the open score."""

    @abstractmethod
    async def get_cursor_info(self) -> CursorInfo:
        """The current position and what is there."""

    @abstractmethod
    async def get_properties(self) -> SelectionProperties:
        """Properties of the current selection."""

    # ── Navigation and selection ────────────────────────────────────

    @abstractmethod
    async def go_to_measure(self, measure: int) -> CursorPosition:
        """Move to a measure (1-indexed)."""

    @abstractmethod
    async def go_to_staff(self, staff: int) -> CursorPosition:
        """Move to a staff (0-indexed)."""

    @abstractmethod
    async def select_measure(self) -> CursorPosition:
        """Select the measure at the current position."""

    @abstractmethod
    async def select_range(
        self, start_measure: int, end_measure: int, start_staff: int, end_staff: int
    ) -> SelectedRange:
        """Select a range of measures (1-indexed) and staves (0-indexed), inclusive."""

    # ── Writing ─────────────────────────────────────────────────────

    @abstractmethod
    async def add_note(
        self, pitch: int, duration: Duration, advance_cursor: bool = True
    ) -> NoteAdded:
        """Add a note (MIDI pitch) at the current position."""

    @abstractmethod
    async def add_rehearsal_mark(self, text: str) -> RehearsalMarkAdded:
        """Add a rehearsal mark at the current position."""

    @abstractmethod
    async def add_chord_symbol(self, text: str) -> ChordSymbolAdded:
        """Add a chord symbol at the current position."""

    @abstractmethod
    async def add_dynamic(self, dynamic: str) -> DynamicAdded:
        """Add a dynamic marking (``"mf"``, ``"p"``, ...) at the current position."""

    @abstractmethod
    async def set_barline(self, barline_type: str) -> BarlineSet:
        """Set the bar line at the end of the current measure."""

    @abstractmethod
    async def set_key_signature(self, fifths: int) -> KeySignatureSet:
        """Set the key signature (positive = sharps, negative = flats)."""

    @abstractmethod
    async def set_time_signature(
        self, numerator: int, denominator: int
    ) -> TimeSignatureSet:
        """Set the time signature at the current position."""

    @abstractmethod
    async def set_tempo(self, bpm: int, text: str | None = None) -> TempoSet:
        """Set the tempo at the current position."""

    @abstractmethod
    async def append_measures(self, count: int) -> MeasuresAppended:
        """Append empty measures to the end of the score."""

    @abstractmethod
    async def transpose(self, semitones: int) -> Transposed:
        """Transpose the current selection by a number of semitones."""

    @abstractmethod
    async def undo(self) -> CursorPosition:
        """Undo the last change; the cursor may move if the change removed measures."""

    # ── Notation on existing notes, lines, text and clefs ───────────
    #
    # Not every bridge implements these yet, so each refuses by default.

    async def set_articulation(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        articulation: Articulation,
        beat: BeatPosition | None,
        remove: bool,
    ) -> ArticulationSet:
        """Add (or remove) an articulation on the notes of a passage.

        *beat* limits the change to the notes starting there in each
        measure.
        """
        raise self._not_supported("set articulations")

    async def set_notehead(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        notehead: Notehead | int,
        beat: BeatPosition | None,
    ) -> NoteheadSet:
        """Change the notehead of the notes of a passage; *beat* as above.

        *notehead* is a shape name or the application's notehead number.
        """
        raise self._not_supported("change noteheads")

    async def add_line(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        line: LineType,
        start_beat: BeatPosition | None = None,
        end_beat: BeatPosition | None = None,
    ) -> LineAdded:
        """Add a line from one measure to another.

        It starts on *start_beat* of the first measure (its start when
        None) and ends with *end_beat* of the last (its end when None).
        """
        raise self._not_supported("add lines")

    async def add_text(self, text: str, style: TextStyle) -> TextAdded:
        """Add staff text at the current position."""
        raise self._not_supported("add staff text")

    async def set_clef(self, clef: Clef) -> ClefSet:
        """Change the clef at the current position."""
        raise self._not_supported("change clefs")

    # ── Rhythm and percussion notation ───────────────────────────────

    async def go_to_beat(self, beat: BeatPosition) -> CursorPosition:
        """Move to a beat, or a partial of one, in the current measure."""
        raise self._not_supported("move to a beat")

    async def add_rest(
        self, duration: Duration, advance_cursor: bool = True
    ) -> RestAdded:
        """Add a rest at the current position."""
        raise self._not_supported("add rests")

    async def add_tuplet(
        self, pitches: list[int | None], actual: int, normal: int, unit: Duration
    ) -> TupletAdded:
        """Add a tuplet of *unit* notes at the current position.

        *actual* notes take the time of *normal*; each pitch is a MIDI
        pitch or None for a rest, and there must be *actual* of them.
        """
        raise self._not_supported("add tuplets")

    async def set_tremolo(
        self,
        start_measure: int,
        end_measure: int,
        staff: int,
        kind: TremoloKind,
        strokes: int,
        beat: BeatPosition | None,
    ) -> TremoloSet:
        """Set tremolo strokes (0 removes them) on the notes of a passage."""
        raise self._not_supported("add tremolos")

    async def add_grace_notes(self, ornament: GraceOrnament) -> GraceNotesAdded:
        """Add a flam, drag or ruff before the note at the current position."""
        raise self._not_supported("add grace notes")

    async def add_sticking(self, sticking: list[str]) -> StickingAdded:
        """Write one sticking letter under each note from the current position."""
        raise self._not_supported("add sticking")

    def _not_supported(self, operation: str) -> BridgeError:
        return BridgeError(
            f"mcp-score cannot {operation} in {self.application_name} yet."
        )
