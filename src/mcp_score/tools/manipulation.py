"""Manipulation tools: change the score in the connected application.

Tools that take a `beat` accept any point in a measure, not just beats:
beats count in the time signature's beat unit, and partials are written
the way they are counted ("2&", "3e", "1trip") or as
"beat:partial/subdivision" for any tuplet.

Every tool that takes a measure moves there first and refuses to continue
if the application cannot get there, so a change never lands in the wrong
place. What an application cannot do comes back as its own explanation:
Dorico's Remote Control API triggers commands but cannot type into
popovers or move the selection, so most of these tools work with
MuseScore and Sibelius only. Articulations, noteheads, lines, staff text,
clefs, rests, tuplets, tremolos, grace notes, sticking and placing things
on a beat work with Sibelius only for now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_score.bridge.results import (
    Articulation,
    ArticulationSet,
    BarlineSet,
    ChordSymbolAdded,
    Clef,
    ClefSet,
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
from mcp_score.context import ScoreContext
from mcp_score.tools import (
    ToolError,
    navigate,
    parse_beat,
    require_bridge,
    require_measure,
    require_measure_range,
    score_tool,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

__all__ = ["register"]

MIN_MIDI_PITCH = 0
MAX_MIDI_PITCH = 127
MAX_NOTEHEAD_NUMBER = 127


def _require_pitch(pitch: int) -> None:
    if not MIN_MIDI_PITCH <= pitch <= MAX_MIDI_PITCH:
        raise ToolError(f"pitch must be between {MIN_MIDI_PITCH} and {MAX_MIDI_PITCH}.")


def _require_duration(numerator: int, denominator: int) -> None:
    if numerator < 1 or denominator < 1:
        raise ToolError("numerator and denominator must be >= 1.")


@score_tool
async def add_live_note(
    context: ScoreContext,
    measure: int,
    pitch: int,
    numerator: int = 1,
    denominator: int = 4,
    staff: int = 0,
    beat: int | str | None = None,
) -> NoteAdded:
    """Add a note at the start of a measure in the live score.

    Consecutive calls on the same measure append notes one after another,
    since the application advances its cursor after each note. Not
    available with Dorico.

    Args:
        measure: Measure number (1-indexed).
        pitch: MIDI pitch (60 = middle C). On a percussion staff the pitch
            picks the instrument, as the staff's drum map says.
        numerator: Duration numerator (default 1, with denominator 4 = quarter note).
        denominator: Duration denominator (default 4).
        staff: Staff index (0-indexed, default: 0).
        beat: Start here instead of where the last note ended: a beat (2), a
            counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Sibelius only.
    """
    bridge = require_bridge(context)
    require_measure(measure)
    _require_pitch(pitch)
    _require_duration(numerator, denominator)
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_note(
        pitch, Duration(numerator=numerator, denominator=denominator)
    )


@score_tool
async def add_live_rehearsal_mark(
    context: ScoreContext, measure: int, text: str
) -> RehearsalMarkAdded:
    """Add a rehearsal mark to a measure in the live score.

    Dorico numbers rehearsal marks itself and ignores the text; Sibelius
    writes one or two letters or a number as given and numbers anything
    else itself. The result says so in a warning when the text was not
    kept.

    Args:
        measure: Measure number (1-indexed).
        text: Rehearsal mark text (e.g. "A", "B", "Intro").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    await navigate(bridge, measure)
    return await bridge.add_rehearsal_mark(text)


@score_tool
async def add_live_chord_symbol(
    context: ScoreContext, measure: int, symbol: str
) -> ChordSymbolAdded:
    """Add a chord symbol to a measure in the live score.

    Not available with Dorico.

    Args:
        measure: Measure number (1-indexed).
        symbol: Chord symbol (e.g. "Cmaj7", "Dm7", "G7").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    await navigate(bridge, measure)
    return await bridge.add_chord_symbol(symbol)


@score_tool
async def add_live_dynamic(
    context: ScoreContext,
    measure: int,
    dynamic: str,
    staff: int = 0,
    beat: int | str | None = None,
) -> DynamicAdded:
    """Add a dynamic marking to a measure in the live score.

    Not available with Dorico. Sibelius writes dynamics spelled with the
    letters p, m, f, r, s, z and n, so "fp", "sfz", "rfz" and "n"
    (niente) work too.

    Args:
        measure: Measure number (1-indexed).
        dynamic: Dynamic such as "pp", "p", "mp", "mf", "f", "ff", "sfz".
        staff: Staff index (0-indexed, default: 0).
        beat: Place it here instead of at the start of the measure: a beat (2),
            a counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Sibelius only.
    """
    bridge = require_bridge(context)
    require_measure(measure)
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_dynamic(dynamic)


@score_tool
async def set_live_barline(
    context: ScoreContext, measure: int, barline_type: str
) -> BarlineSet:
    """Set the bar line at the end of a measure in the live score.

    Args:
        measure: Measure number (1-indexed).
        barline_type: One of "normal", "double", "final", "dashed", "dotted",
            "tick", "short", "startRepeat", "endRepeat" or "endStartRepeat".
            "startRepeat" marks the start of this measure; "endStartRepeat"
            ends a repeat here and starts one in the next measure. Dorico
            supports "double", "final", "startRepeat" and "endRepeat";
            Sibelius supports all but "dotted" and "endStartRepeat".
    """
    bridge = require_bridge(context)
    require_measure(measure)
    await navigate(bridge, measure)
    return await bridge.set_barline(barline_type)


@score_tool
async def set_live_key_signature(
    context: ScoreContext, measure: int, fifths: int
) -> KeySignatureSet:
    """Set the key signature from a measure onward in the live score.

    Not available with Dorico.

    Args:
        measure: Measure number (1-indexed).
        fifths: Sharps (positive) or flats (negative): 0 = C major,
            2 = D major, -3 = Eb major.
    """
    bridge = require_bridge(context)
    require_measure(measure)
    await navigate(bridge, measure)
    return await bridge.set_key_signature(fifths)


@score_tool
async def set_live_time_signature(
    context: ScoreContext, measure: int, numerator: int, denominator: int
) -> TimeSignatureSet:
    """Set the time signature from a measure onward in the live score.

    Not available with Dorico.

    Args:
        measure: Measure number (1-indexed).
        numerator: Beats per measure (e.g. 3 in 3/4).
        denominator: Beat unit (e.g. 4 in 3/4).
    """
    bridge = require_bridge(context)
    require_measure(measure)
    if numerator < 1 or denominator < 1:
        raise ToolError("numerator and denominator must be >= 1.")
    await navigate(bridge, measure)
    return await bridge.set_time_signature(numerator, denominator)


@score_tool
async def set_live_tempo(
    context: ScoreContext, measure: int, bpm: int, text: str | None = None
) -> TempoSet:
    """Set the tempo at a measure in the live score.

    Not available with Dorico.

    Args:
        measure: Measure number (1-indexed).
        bpm: Beats per minute.
        text: Optional display text (e.g. "Swing", "Allegro").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    if bpm < 1:
        raise ToolError("bpm must be >= 1.")
    await navigate(bridge, measure)
    return await bridge.set_tempo(bpm, text)


@score_tool
async def append_live_measures(
    context: ScoreContext, count: int = 1
) -> MeasuresAppended:
    """Append empty measures to the end of the live score.

    Not available with Dorico.

    Args:
        count: How many measures to append (default: 1).
    """
    bridge = require_bridge(context)
    if count < 1:
        raise ToolError("count must be >= 1.")
    return await bridge.append_measures(count)


@score_tool
async def transpose_passage(
    context: ScoreContext,
    start_measure: int,
    end_measure: int,
    staff: int,
    semitones: int,
) -> Transposed:
    """Transpose the notes of a passage by a number of semitones in the live score.

    Notes are moved with conventional spelling (a minor second up turns C
    into Db). Key signatures and chord symbols in the passage are left
    unchanged. Not available with Dorico, which cannot select a range.

    Args:
        start_measure: First measure (1-indexed).
        end_measure: Last measure (inclusive, 1-indexed).
        staff: Staff index (0-indexed).
        semitones: Semitones to transpose (positive = up, negative = down).
    """
    bridge = require_bridge(context)
    require_measure_range(start_measure, end_measure)
    await navigate(bridge, start_measure, staff)
    await bridge.select_range(start_measure, end_measure, staff, staff)
    return await bridge.transpose(semitones)


@score_tool
async def undo_last_action(context: ScoreContext) -> CursorPosition:
    """Undo the last change in the connected application.

    Reports where the cursor is afterwards, since undoing can remove the
    measure it was on.
    """
    return await require_bridge(context).undo()


@score_tool
async def set_live_articulation(
    context: ScoreContext,
    start_measure: int,
    end_measure: int,
    articulation: Articulation,
    staff: int = 0,
    beat: int | str | None = None,
    remove: bool = False,
) -> ArticulationSet:
    """Add an articulation to the notes of a passage in the live score.

    Every note and chord in the measures gets the articulation, or only
    those starting on `beat` in each measure. Rests are left alone. Sibelius
    only for now.

    Args:
        start_measure: First measure (1-indexed).
        end_measure: Last measure (inclusive, 1-indexed).
        articulation: The articulation; "fermata" is the usual pause.
        staff: Staff index (0-indexed, default: 0).
        beat: Only notes starting here in each measure: a beat (2), a counted
            partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Omit for every note.
        remove: Take the articulation off instead of adding it.
    """
    bridge = require_bridge(context)
    require_measure_range(start_measure, end_measure)
    position = parse_beat(beat)
    return await bridge.set_articulation(
        start_measure, end_measure, staff, articulation, position, remove
    )


@score_tool
async def set_live_notehead(
    context: ScoreContext,
    start_measure: int,
    end_measure: int,
    notehead: Notehead | int,
    staff: int = 0,
    beat: int | str | None = None,
) -> NoteheadSet:
    """Change the notehead of the notes of a passage in the live score.

    Every note in the measures gets the notehead, or only the notes of
    chords starting on `beat` in each measure; "normal" restores the usual
    one. Sibelius only for now.

    Args:
        start_measure: First measure (1-indexed).
        end_measure: Last measure (inclusive, 1-indexed).
        notehead: The notehead shape ("slash" for rhythm slashes, "cross"
            for ghost notes and percussion), or Sibelius's notehead number
            (0-127), which percussion templates such as VDL use to pick
            sounds; see vdl_notehead_guide.
        staff: Staff index (0-indexed, default: 0).
        beat: Only notes starting here in each measure: a beat (2), a counted
            partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Omit for every note.
    """
    bridge = require_bridge(context)
    require_measure_range(start_measure, end_measure)
    if isinstance(notehead, int) and not 0 <= notehead <= MAX_NOTEHEAD_NUMBER:
        raise ToolError(f"notehead number must be between 0 and {MAX_NOTEHEAD_NUMBER}.")
    position = parse_beat(beat)
    return await bridge.set_notehead(
        start_measure, end_measure, staff, notehead, position
    )


@score_tool
async def add_live_line(
    context: ScoreContext,
    start_measure: int,
    end_measure: int,
    line: LineType,
    staff: int = 0,
    start_beat: int | str | None = None,
    end_beat: int | str | None = None,
) -> LineAdded:
    """Add a line from one measure to another in the live score.

    Slurs, hairpins (crescendo, and diminuendo or decrescendo, which are
    the same), trills, octave lines, pedal lines and glissandi. Without
    beats the line runs from the start of the first measure to the end of
    the last; with them, a hairpin can swell over a single beat. Sibelius
    only for now.

    Args:
        start_measure: Measure the line starts in (1-indexed).
        end_measure: Measure the line ends in (inclusive, 1-indexed).
        line: The kind of line.
        staff: Staff index (0-indexed, default: 0).
        start_beat: Where in the first measure the line starts: a beat (2), a
            counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Omit to start with the
            measure.
        end_beat: The beat or partial of the last measure the line ends with (it
            ends where that one ends), in the same form. Omit to end with the
            measure.
    """
    bridge = require_bridge(context)
    require_measure_range(start_measure, end_measure)
    start = parse_beat(start_beat, "start_beat")
    end = parse_beat(end_beat, "end_beat")
    if (
        start_measure == end_measure
        and start is not None
        and end is not None
        and end.end() <= start.start()
    ):
        raise ToolError("end_beat must come after start_beat within one measure.")
    return await bridge.add_line(start_measure, end_measure, staff, line, start, end)


@score_tool
async def add_live_text(
    context: ScoreContext,
    measure: int,
    text: str,
    style: TextStyle = "technique",
    staff: int = 0,
    beat: int | str | None = None,
) -> TextAdded:
    """Add staff text to a measure in the live score.

    Technique text for playing instructions ("pizz.", "con sord."),
    expression text for character ("dolce", "espress."), or plain or boxed
    text. Sibelius only for now.

    Args:
        measure: Measure number (1-indexed).
        text: The text to write.
        style: technique, expression, plain or boxed (default: technique).
        staff: Staff index (0-indexed, default: 0).
        beat: Place it here instead of at the start of the measure: a beat (2),
            a counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    if not text.strip():
        raise ToolError("text must not be empty.")
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_text(text, style)


@score_tool
async def set_live_clef(
    context: ScoreContext, measure: int, clef: Clef, staff: int = 0
) -> ClefSet:
    """Change the clef from a measure onward in the live score.

    Sibelius only for now.

    Args:
        measure: Measure number (1-indexed).
        clef: The clef; "treble_8vb" is the tenor-voice treble clef.
        staff: Staff index (0-indexed, default: 0).
    """
    bridge = require_bridge(context)
    require_measure(measure)
    await navigate(bridge, measure, staff)
    return await bridge.set_clef(clef)


@score_tool
async def add_live_rest(
    context: ScoreContext,
    measure: int,
    numerator: int = 1,
    denominator: int = 4,
    staff: int = 0,
    beat: int | str | None = None,
) -> RestAdded:
    """Add a rest in the live score, where the last note or rest ended.

    Use it between add_live_note calls to write rhythms with rests; the
    cursor advances past the rest. Sibelius only for now.

    Args:
        measure: Measure number (1-indexed).
        numerator: Duration numerator (default 1, with denominator 4 = quarter rest).
        denominator: Duration denominator (default 4).
        staff: Staff index (0-indexed, default: 0).
        beat: Start here instead of where the last note ended: a beat (2), a
            counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    _require_duration(numerator, denominator)
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_rest(Duration(numerator=numerator, denominator=denominator))


@score_tool
async def add_live_tuplet(
    context: ScoreContext,
    measure: int,
    pitches: list[int | None],
    actual: int = 3,
    normal: int = 2,
    numerator: int = 1,
    denominator: int = 8,
    staff: int = 0,
    beat: int | str | None = None,
) -> TupletAdded:
    """Add a tuplet (triplet, sextuplet, quintuplet...) in the live score.

    `actual` notes of the given value take the time of `normal` of them,
    starting where the last note ended; the cursor advances past the
    tuplet. The defaults make an eighth-note triplet. Sibelius only for
    now.

    Args:
        measure: Measure number (1-indexed).
        pitches: One MIDI pitch per note, or null for a rest; exactly
            `actual` of them.
        actual: Notes in the tuplet (3 for a triplet, 6 for a sextuplet).
        normal: Notes of the same value it takes the time of (2 for a
            triplet, 4 for a sextuplet).
        numerator: Note value numerator (default 1).
        denominator: Note value denominator (default 8: eighth notes).
        staff: Staff index (0-indexed, default: 0).
        beat: Start here instead of where the last note ended: a beat (2), a
            counted partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    if actual < 1 or normal < 1:
        raise ToolError("actual and normal must be >= 1.")
    if len(pitches) != actual:
        raise ToolError(f"pitches must hold {actual} pitches or nulls, one per note.")
    for pitch in pitches:
        if pitch is not None:
            _require_pitch(pitch)
    _require_duration(numerator, denominator)
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_tuplet(
        pitches, actual, normal, Duration(numerator=numerator, denominator=denominator)
    )


@score_tool
async def set_live_tremolo(
    context: ScoreContext,
    start_measure: int,
    end_measure: int,
    kind: TremoloKind = "single",
    strokes: int = 3,
    staff: int = 0,
    beat: int | str | None = None,
) -> TremoloSet:
    """Add tremolos (rolls) to the notes of a passage in the live score.

    "single" puts strokes on each note's stem (three for an unmeasured
    roll, fewer for measured diddles), "buzz" a z on the stem for a buzz
    roll, and "double" strokes between each note and the next, for mallet
    and timpani rolls between two pitches (the two notes need the same
    length). strokes 0 removes tremolos. Sibelius only for now.

    Args:
        start_measure: First measure (1-indexed).
        end_measure: Last measure (inclusive, 1-indexed).
        kind: single, double or buzz (default: single).
        strokes: Tremolo strokes, 0 to 7 (default 3); ignored for buzz.
        staff: Staff index (0-indexed, default: 0).
        beat: Only notes starting here in each measure: a beat (2), a counted
            partial ("2&", "2e", "2a", "2trip", "2let") or
            "beat:partial/subdivision" ("4:3/5"). Omit for every note.
    """
    bridge = require_bridge(context)
    require_measure_range(start_measure, end_measure)
    if strokes < 0:
        raise ToolError("strokes must be >= 0.")
    position = parse_beat(beat)
    return await bridge.set_tremolo(
        start_measure, end_measure, staff, kind, strokes, position
    )


@score_tool
async def add_live_grace_notes(
    context: ScoreContext,
    measure: int,
    ornament: GraceOrnament,
    beat: int | str = 1,
    staff: int = 0,
) -> GraceNotesAdded:
    """Add a flam, drag or ruff before a note in the live score.

    A flam is one slashed eighth-note grace note, a drag two and a ruff
    three sixteenth-note grace notes, all on the note's line. The note
    must already be there. Sibelius only for now.

    Args:
        measure: Measure number (1-indexed).
        ornament: flam, drag or ruff.
        beat: Where the note starts (default 1): a beat (2), a counted partial
            ("2&", "2e", "2a", "2trip", "2let") or "beat:partial/subdivision"
            ("4:3/5").
        staff: Staff index (0-indexed, default: 0).
    """
    bridge = require_bridge(context)
    require_measure(measure)
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_grace_notes(ornament)


@score_tool
async def add_live_sticking(
    context: ScoreContext,
    measure: int,
    sticking: str,
    staff: int = 0,
    beat: int | str | None = None,
) -> StickingAdded:
    """Write sticking (R, L...) under the notes of the live score.

    One letter or group per note, from the start of the measure (or
    `beat`) on, continuing into the next measures until the sticking runs
    out. Separate groups with spaces ("R L R R L L", or "RH LH"); without
    spaces each character is one note ("RLRRLRLL"). Sibelius writes it as
    lyrics, the usual way to engrave sticking. Sibelius only for now.

    Args:
        measure: Measure number (1-indexed).
        sticking: The sticking, as described above.
        staff: Staff index (0-indexed, default: 0).
        beat: Start under the note here: a beat (2), a counted partial ("2&",
            "2e", "2a", "2trip", "2let") or "beat:partial/subdivision"
            ("4:3/5").
    """
    bridge = require_bridge(context)
    require_measure(measure)
    letters = sticking.split() if " " in sticking.strip() else list(sticking.strip())
    if not letters:
        raise ToolError("sticking must not be empty.")
    position = parse_beat(beat)
    await navigate(bridge, measure, staff, position)
    return await bridge.add_sticking(letters)


def register(server: MCPServer) -> None:
    for tool in (
        add_live_note,
        add_live_rehearsal_mark,
        add_live_chord_symbol,
        add_live_dynamic,
        set_live_barline,
        set_live_key_signature,
        set_live_time_signature,
        set_live_tempo,
        append_live_measures,
        transpose_passage,
        set_live_articulation,
        set_live_notehead,
        add_live_line,
        add_live_text,
        set_live_clef,
        add_live_rest,
        add_live_tuplet,
        set_live_tremolo,
        add_live_grace_notes,
        add_live_sticking,
        undo_last_action,
    ):
        server.tool()(tool)
