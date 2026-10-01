"""What the score operations report back.

Every model here is what a tool returns to the model, so the MCP server
publishes it as the tool's output schema and validates each result
against it. The bridges build them from the applications' replies.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ApplicationReply",
    "Articulation",
    "ArticulationSet",
    "BarlineSet",
    "BeatPosition",
    "ChordSymbolAdded",
    "Clef",
    "ClefSet",
    "GraceNotesAdded",
    "GraceOrnament",
    "CursorInfo",
    "CursorPosition",
    "Duration",
    "DynamicAdded",
    "Element",
    "KeySignatureSet",
    "LineAdded",
    "LineType",
    "MeasuresAppended",
    "Note",
    "NoteAdded",
    "Notehead",
    "NoteheadSet",
    "RestAdded",
    "Part",
    "RehearsalMarkAdded",
    "Result",
    "ScoreInfo",
    "SelectedRange",
    "SelectionProperties",
    "TempoSet",
    "StickingAdded",
    "TextAdded",
    "TextStyle",
    "TimeSignature",
    "TimeSignatureSet",
    "Transposed",
    "TremoloKind",
    "TremoloSet",
    "TupletAdded",
]


class Result(BaseModel):
    """Base of every result: strict about fields, documented by attribute."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class ApplicationReply(BaseModel):
    """An application's reply passed on as it came, for data with no fixed shape."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)


# ── Score ─────────────────────────────────────────────────────────────


class Duration(Result):
    """A note length as a fraction of a whole note (1/4 is a quarter note)."""

    numerator: int
    denominator: int


class TimeSignature(Result):
    numerator: int
    denominator: int


class Part(Result):
    name: str
    start_staff: int
    """First staff of the part (0-indexed)."""
    end_staff: int
    """Last staff of the part (0-indexed, inclusive)."""


class ScoreInfo(Result):
    """What is known about the open score without reading its content."""

    title: str
    part_count: int
    parts: list[Part]
    measure_count: int
    key_signature: int | None
    """Sharps (positive) or flats (negative) at the start, when known."""
    time_signature: TimeSignature | None
    """The time signature at the start, when known."""


# ── Cursor ────────────────────────────────────────────────────────────


class CursorPosition(Result):
    """Where the application's cursor is."""

    measure: int
    """Measure number (1-indexed)."""
    staff: int
    """Staff index (0-indexed)."""


class Note(Result):
    pitch: int
    """MIDI pitch (60 = middle C)."""
    tpc: int
    """Tonal pitch class, which fixes the spelling (C# versus Db)."""
    name: str | None
    """Note name with octave, when the application gives one."""


class Element(Result):
    """What sits at the cursor: a chord, a rest, a single note or something else."""

    type: int | str
    """The application's element type: MuseScore's code, Sibelius's type name."""
    notes: list[Note] | None = None
    """The notes of a chord."""
    duration: Duration | None = None
    """The length of a chord or rest."""
    pitch: int | None = None
    """MIDI pitch of a single note."""
    tpc: int | None = None
    """Tonal pitch class of a single note."""
    name: str | None = None
    """Name of a single note."""


class CursorInfo(CursorPosition):
    """The cursor position and what is there."""

    voice: int
    beat: int | None
    """Beat within the measure (1-indexed), when the time signature is known."""
    tick: int
    """Position in the application's internal ticks."""
    element: Element | None
    """The element at the cursor, or None on an empty position."""


class SelectionProperties(Result):
    """What the application reports about the current selection.

    MuseScore and Sibelius report the cursor position; Dorico reports the
    properties of the selected items as they come from its API.
    """

    cursor: CursorInfo | None = None
    properties: ApplicationReply | None = None
    warning: str | None = None


# ── Selection ─────────────────────────────────────────────────────────


class SelectedRange(Result):
    start_measure: int
    end_measure: int
    start_staff: int
    end_staff: int


# ── Edits: each echoes what was written and where ─────────────────────


class NoteAdded(CursorPosition):
    """A note was added; the position is where the cursor went afterwards."""

    pitch: int
    duration: Duration


class RehearsalMarkAdded(Result):
    text: str
    measure: int
    warning: str | None = None
    """Set when the application kept the mark but not the text."""


class ChordSymbolAdded(Result):
    text: str
    measure: int


class DynamicAdded(Result):
    dynamic: str
    measure: int


class BarlineSet(Result):
    barline_type: str
    measure: int


class KeySignatureSet(Result):
    fifths: int
    measure: int


class TimeSignatureSet(TimeSignature):
    measure: int


class TempoSet(Result):
    bpm: int
    text: str
    """The tempo marking as written."""
    measure: int


class MeasuresAppended(Result):
    count: int
    total_measures: int


class Transposed(Result):
    semitones: int
    notes: int
    """How many notes were moved."""


# ── Positions inside a measure ────────────────────────────────────────


class BeatPosition(Result):
    """A point in a measure: a beat, or a partial of one.

    Beats count in the time signature's beat unit (quarters in 4/4,
    eighths in 6/8). A beat is split into `subdivision` equal partials and
    `partial` picks one, so the "and" of 2 is beat 2, partial 2 of 2, the
    "a" of 3 is beat 3, partial 4 of 4, and the last note of a triplet on
    beat 1 is beat 1, partial 3 of 3.
    """

    beat: int
    """The beat (1-indexed)."""
    subdivision: int = 1
    """How many equal partials the beat is split into."""
    partial: int = 1
    """The partial (1-indexed) within the beat."""

    def start(self) -> Fraction:
        """Where the partial starts, in beats from the start of the measure."""
        return self.beat - 1 + Fraction(self.partial - 1, self.subdivision)

    def end(self) -> Fraction:
        """Where the partial ends, in beats from the start of the measure."""
        return self.beat - 1 + Fraction(self.partial, self.subdivision)


# ── Notation on existing notes, lines, text and clefs ─────────────────

type Articulation = Literal[
    "staccato",
    "staccatissimo",
    "wedge",
    "tenuto",
    "accent",
    "marcato",
    "harmonic",
    "plus",
    "up_bow",
    "down_bow",
    "fermata",
    "square_fermata",
    "triangle_fermata",
]
"""An articulation mark on a note or chord."""

type Notehead = Literal[
    "normal",
    "cross",
    "diamond",
    "slash",
    "slash_without_stem",
    "cross_or_diamond",
    "black_and_white_diamond",
    "headless",
    "stemless",
    "silent",
    "cue",
    "slashed",
    "back_slashed",
    "arrow_down",
    "arrow_up",
    "inverted_triangle",
]
"""A notehead shape."""

type LineType = Literal[
    "slur",
    "slur_below",
    "crescendo",
    "diminuendo",
    "decrescendo",
    "trill",
    "ottava",
    "ottava_bassa",
    "quindicesima",
    "quindicesima_bassa",
    "pedal",
    "glissando",
]
"""A line: slurs, hairpins (decrescendo is diminuendo), trills, octave lines, pedal."""

type TextStyle = Literal["technique", "expression", "plain", "boxed"]
"""How staff text is styled: technique (pizz.), expression (dolce), plain, boxed."""

type Clef = Literal[
    "treble",
    "treble_8vb",
    "treble_8va",
    "bass",
    "bass_8vb",
    "alto",
    "tenor",
    "soprano",
    "mezzo_soprano",
    "baritone",
    "percussion",
]
"""A clef; baritone is the F clef on the middle line."""


class ArticulationSet(Result):
    articulation: Articulation
    removed: bool
    """True when the articulation was taken off rather than added."""
    start_measure: int
    end_measure: int
    staff: int
    beat: BeatPosition | None
    """The position the change was limited to, or None for every note."""
    notes: int
    """How many notes and chords were changed."""


class NoteheadSet(Result):
    notehead: Notehead | int
    """The notehead, by name or by the application's notehead number."""
    start_measure: int
    end_measure: int
    staff: int
    beat: BeatPosition | None
    """The position the change was limited to, or None for every note."""
    notes: int
    """How many noteheads were changed (each note of a chord counts)."""


class LineAdded(Result):
    line: LineType
    start_measure: int
    end_measure: int
    staff: int
    start_beat: BeatPosition | None = None
    """Where the line starts, or None for the start of the measure."""
    end_beat: BeatPosition | None = None
    """The beat or partial the line ends with, or None for the measure's end."""


class TextAdded(Result):
    text: str
    style: TextStyle
    measure: int
    staff: int


class ClefSet(Result):
    clef: Clef
    measure: int
    staff: int


# ── Rhythm and percussion notation ────────────────────────────────────

type TremoloKind = Literal["single", "double", "buzz"]
"""Strokes on one note's stem, strokes between two notes, or a buzz (z) roll."""

type GraceOrnament = Literal["flam", "drag", "ruff"]
"""One, two or three grace notes before a note, in the note's pitch."""


class RestAdded(CursorPosition):
    """A rest was added; the position is where the cursor went afterwards."""

    duration: Duration


class TupletAdded(CursorPosition):
    """A tuplet was filled; the position is where the cursor went afterwards."""

    actual: int
    """Notes in the tuplet (3 in a triplet)."""
    normal: int
    """Notes of the same value the tuplet takes the time of (2 in a triplet)."""
    unit: Duration
    """The value of each note in the tuplet."""
    notes: int
    """How many notes and rests were written."""


class TremoloSet(Result):
    kind: TremoloKind
    strokes: int
    """Tremolo strokes (0 removes them); -1 for a buzz roll."""
    start_measure: int
    end_measure: int
    staff: int
    beat: BeatPosition | None
    """The position the change was limited to, or None for every note."""
    notes: int
    """How many notes and chords were changed."""


class GraceNotesAdded(Result):
    ornament: GraceOrnament
    measure: int
    staff: int
    notes: int
    """How many grace notes were added."""


class StickingAdded(Result):
    sticking: list[str]
    """The letters, one per note, as written under the notes."""
    measure: int
    staff: int
    notes: int
    """How many notes got a letter; fewer than the letters when notes ran out."""
