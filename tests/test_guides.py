"""Tests for the reference guide tools."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from mcp_score.tools import ToolError
from mcp_score.tools.guides import vdl_notehead_guide

if TYPE_CHECKING:
    from pathlib import Path

BATTERY_INSTRUMENTS = (
    "Snare Solo Kevlar",
    "Snare Solo Mylar",
    "SnareLine Manual",
    "SnareLine (AutoRL)",
    "TenorLine Manual",
    "TenorLine (AutoRL)",
    "Tenor Solo",
    "BassLine Manual",
    "BassLine (AutoRL)",
    "BassLine 10-Drums Manual",
    "BassLine 10-Drums (AutoRL)",
    "Cymbal Line (All, 16in, 18in, 20in)",
    "Showstyle Single Tenors",
)


class TestVdlNoteheadGuide:
    def test_bundled_guide_covers_every_battery_instrument(self) -> None:
        # Act
        guide = vdl_notehead_guide()

        # Assert
        headings = re.findall(r"^## (.+)$", guide, re.MULTILINE)
        assert set(BATTERY_INSTRUMENTS) <= set(headings)
        assert "used with" in guide  # the permission and attribution notice

    def test_every_notehead_number_is_one_sibelius_can_set(self) -> None:
        # Arrange: table cells holding numbers, such as "| 31 | 0 |"
        guide = vdl_notehead_guide()
        rows = [line for line in guide.splitlines() if line.startswith("| ")]

        # Act
        numbers = [
            int(number)
            for row in rows
            for cell in row.strip("|").split("|")[1:]
            for number in re.findall(r"\b\d+\b", cell)
        ]

        # Assert: what set_live_notehead accepts
        assert numbers
        assert all(0 <= number <= 127 for number in numbers)

    def test_missing_guide_is_a_tool_error(self, tmp_path: Path) -> None:
        # Arrange
        with (
            patch(
                "mcp_score.tools.guides.package_path",
                side_effect=FileNotFoundError("Cannot find bundled resource"),
            ),
            pytest.raises(ToolError, match="Cannot find bundled resource"),
        ):
            # Act
            vdl_notehead_guide()
