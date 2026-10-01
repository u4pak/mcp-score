"""A passage: many notes, rests and their markings written in one call.

``write_live_passage`` takes a list of :class:`PassageEvent`. Events
follow each other from the cursor, across bar lines, unless one names a
``measure`` or ``beat`` to jump to. Consecutive events with the same
``tuplet`` ratio and duration form tuplets of ``actual`` events each.
:func:`tuplet_indexes` checks that grouping for every bridge.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

from mcp_score.bridge.results import (
    BEAT_FORMAT,
    Articulation,
    BeatPosition,
    CursorPosition,
    Duration,
    GraceOrnament,
    Notehead,
    Result,
    TremoloKind,
)

__all__ = [
    "PassageEvent",
    "PassageWritten",
    "TupletRatio",
    "tuplet_indexes",
]


def _read_beat(value: object) -> object:
    """Turn a beat number or counted partial into a :class:`BeatPosition`."""
    if isinstance(value, int | str) and not isinstance(value, bool):
        return BeatPosition.parse(value)
    return value


type BeatArgument = Annotated[
    BeatPosition,
    BeforeValidator(_read_beat),
    WithJsonSchema(
        {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": f"Where the event starts: {BEAT_FORMAT}.",
        }
    ),
]
"""A beat or partial, written as tools take it ("2&", "1trip", 3)."""


class TupletRatio(Result):
    actual: int
    """Notes in the tuplet (3 in a triplet)."""
    normal: int
    """Notes of the same value it takes the time of (2 in a triplet)."""


class PassageEvent(Result):
    """One note, chord or rest of a passage, with its markings."""

    pitch: int | list[int] | None = None
    """MIDI pitch, a list of pitches for a chord, or null for a rest."""
    duration: Duration
    """Length as a fraction of a whole note (1/16 is a sixteenth). Inside a
    tuplet, the written value of each tuplet note (1/8 for eighth triplets)."""
    measure: int | None = None
    """Jump to this measure (1-indexed) first; otherwise follow the last event."""
    beat: BeatArgument | None = None
    """Jump to this point in the measure first."""
    tuplet: TupletRatio | None = None
    """Put the event in a tuplet; consecutive events with the same ratio and
    duration fill tuplets of `actual` events each."""
    notehead: Notehead | int | None = None
    """Notehead shape, or the application's notehead number (VDL sounds)."""
    articulations: list[Articulation] = []
    """Articulations on the note or chord."""
    tremolo: TremoloKind | None = None
    """Tremolo: single strokes on the stem, double (to the next note), buzz."""
    tremolo_strokes: int = 3
    """Tremolo strokes, 0-7 (ignored for buzz)."""
    grace: GraceOrnament | None = None
    """Flam, drag or ruff before the note."""
    sticking: str | None = None
    """Sticking written under the note ("R", "L", "RH")."""
    dynamic: str | None = None
    """Dynamic at the event ("p", "mf", "fp", "sfz")."""


class PassageWritten(CursorPosition):
    """A passage was written; the position is where the cursor went afterwards."""

    events: int
    """How many events (notes, chords and rests) were written."""
    notes: int
    """How many noteheads were written, counting each note of a chord."""


def tuplet_indexes(events: list[PassageEvent]) -> list[int | None]:
    """Each event's index within its tuplet, or None outside one.

    Raises:
        ValueError: When a tuplet is left incomplete, changes duration
            midway, or jumps to a new measure or beat after its first note.
    """
    indexes: list[int | None] = []
    group: PassageEvent | None = None
    filled = 0
    for number, event in enumerate(events, start=1):
        tuplet = event.tuplet
        if group is not None and group.tuplet is not None:
            same = tuplet == group.tuplet and event.duration == group.duration
            if filled < group.tuplet.actual:
                if not same:
                    raise ValueError(
                        f"Event {number}: the tuplet before it needs "
                        f"{group.tuplet.actual} notes of the same value."
                    )
                if event.measure is not None or event.beat is not None:
                    raise ValueError(
                        f"Event {number}: only a tuplet's first note can jump "
                        "to a measure or beat."
                    )
                indexes.append(filled)
                filled += 1
                continue
        if tuplet is None:
            group, filled = None, 0
            indexes.append(None)
            continue
        if tuplet.actual < 1 or tuplet.normal < 1:
            raise ValueError(f"Event {number}: tuplet actual and normal must be >= 1.")
        group, filled = event, 1
        indexes.append(0)
    if group is not None and group.tuplet is not None and filled < group.tuplet.actual:
        raise ValueError(
            f"The last tuplet needs {group.tuplet.actual} notes; it has {filled}."
        )
    return indexes
