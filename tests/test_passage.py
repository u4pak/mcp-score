"""Tests for passage events: how they read beats and group into tuplets."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from mcp_score.bridge.passage import PassageEvent, tuplet_indexes
from mcp_score.bridge.results import BeatPosition

EIGHTH: dict[str, int] = {"numerator": 1, "denominator": 8}
SIXTEENTH: dict[str, int] = {"numerator": 1, "denominator": 16}
TRIPLET: dict[str, int] = {"actual": 3, "normal": 2}


def _events(*fields: dict[str, Any]) -> list[PassageEvent]:
    return [PassageEvent.model_validate({"pitch": 38, **event}) for event in fields]


class TestPassageEventBeat:
    def test_counted_beat_is_read_into_a_position(self) -> None:
        # Act
        event = PassageEvent.model_validate(
            {"pitch": 38, "duration": SIXTEENTH, "beat": "3e"}
        )

        # Assert
        assert event.beat == BeatPosition(beat=3, subdivision=4, partial=2)

    def test_unreadable_beat_is_a_validation_error_naming_the_format(self) -> None:
        # Act / Assert
        with pytest.raises(ValidationError, match="counted partial"):
            PassageEvent.model_validate(
                {"pitch": 38, "duration": SIXTEENTH, "beat": "three"}
            )

    def test_schema_tells_clients_a_beat_is_a_number_or_a_string(self) -> None:
        # Act
        schema = TypeAdapter(PassageEvent).json_schema()

        # Assert
        beat_schema = schema["$defs"]["BeatArgument"]
        assert beat_schema["anyOf"] == [{"type": "integer"}, {"type": "string"}]


class TestTupletIndexes:
    def test_plain_events_are_outside_tuplets(self) -> None:
        # Act / Assert
        assert tuplet_indexes(_events({"duration": EIGHTH}, {"duration": EIGHTH})) == [
            None,
            None,
        ]

    def test_consecutive_triplet_events_fill_one_tuplet_after_another(self) -> None:
        # Arrange: two eighth-note triplets, then a plain eighth
        triplet_note = {"duration": EIGHTH, "tuplet": TRIPLET}
        events = _events(*[triplet_note] * 6, {"duration": EIGHTH})

        # Act / Assert
        assert tuplet_indexes(events) == [0, 1, 2, 0, 1, 2, None]

    def test_incomplete_tuplet_at_the_end_is_refused(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="needs 3 notes; it has 2"):
            tuplet_indexes(_events(*[{"duration": EIGHTH, "tuplet": TRIPLET}] * 2))

    def test_tuplet_cut_short_by_another_value_is_refused(self) -> None:
        # Arrange
        events = _events(
            {"duration": EIGHTH, "tuplet": TRIPLET},
            {"duration": SIXTEENTH, "tuplet": TRIPLET},
        )

        # Act / Assert
        with pytest.raises(ValueError, match="Event 2: the tuplet before it needs 3"):
            tuplet_indexes(events)

    def test_jump_inside_a_tuplet_is_refused(self) -> None:
        # Arrange
        events = _events(
            {"duration": EIGHTH, "tuplet": TRIPLET},
            {"duration": EIGHTH, "tuplet": TRIPLET, "beat": "2&"},
            {"duration": EIGHTH, "tuplet": TRIPLET},
        )

        # Act / Assert
        with pytest.raises(ValueError, match="Event 2: only a tuplet's first note"):
            tuplet_indexes(events)
