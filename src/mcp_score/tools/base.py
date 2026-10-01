"""What every tool module shares.

A tool raises the MCP SDK's :class:`ToolError` when it cannot proceed,
and the server reports it to the model as a tool error. An application's
refusal reaches a tool as a :class:`BridgeError`; :func:`score_tool`
reports it the same way, so no tool handles errors itself. Tools that
talk to an application take the server's :class:`ScoreContext` first,
which the MCP SDK injects; the ``require_*`` guards check the common
preconditions and :func:`navigate` moves the application's cursor before
an edit.
"""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Protocol

from mcp.server.mcpserver.exceptions import ToolError

from mcp_score.bridge import BridgeError
from mcp_score.bridge.results import BeatPosition
from mcp_score.context import registry_of

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.mcpserver import MCPServer

    from mcp_score.bridge import ScoreBridge
    from mcp_score.context import ScoreContext

__all__ = [
    "NOT_CONNECTED",
    "Tool",
    "ToolError",
    "ToolModule",
    "navigate",
    "BEAT_FORMAT",
    "parse_beat",
    "require_bridge",
    "require_measure",
    "require_measure_range",
    "score_tool",
]

NOT_CONNECTED = (
    "Not connected to any score application. "
    "Use connect_to_musescore, connect_to_dorico or connect_to_sibelius first."
)


class ToolModule(Protocol):
    """A module of tools: ``register(server)`` adds them to the server."""

    def register(self, server: MCPServer) -> None: ...


type Tool[**P, R] = Callable[P, Awaitable[R]]
"""An MCP tool: an async function whose result the server publishes as its schema."""


def score_tool[**P, R](tool: Tool[P, R]) -> Tool[P, R]:
    """Report an application's refusal (:class:`BridgeError`) as a tool error.

    The wrapped function keeps its signature, which is what the MCP server
    reads to describe the tool's parameters and result to the model.
    """

    @functools.wraps(tool)
    async def deliver(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await tool(*args, **kwargs)
        except BridgeError as error:
            raise ToolError(error.message) from error

    return deliver


def require_bridge(context: ScoreContext) -> ScoreBridge:
    """The connected bridge.

    Raises:
        ToolError: When no application is connected.
    """
    bridge = registry_of(context).connected()
    if bridge is None:
        raise ToolError(NOT_CONNECTED)
    return bridge


def require_measure(measure: int, name: str = "measure") -> None:
    """Validate a 1-indexed measure number.

    Raises:
        ToolError: When it is below 1.
    """
    if measure < 1:
        raise ToolError(f"{name} must be >= 1.")


BEAT_FORMAT = (
    'a beat number (2), a counted partial ("2e", "2&" or "2+", "2a"; "2trip" '
    'and "2let" for the second and third note of a triplet), or '
    '"beat:partial/subdivision" ("4:3/5" is the third note of a quintuplet '
    "on beat 4)"
)
"""How a tool argument names a point in a measure, for docstrings and errors."""

# The syllables of counting, as (subdivision, partial): 1 e & a, 1 trip let.
_COUNTED_PARTIALS: dict[str, tuple[int, int]] = {
    "e": (4, 2),
    "&": (2, 2),
    "+": (2, 2),
    "and": (2, 2),
    "a": (4, 4),
    "trip": (3, 2),
    "let": (3, 3),
}

_BEAT = re.compile(
    r"(?P<beat>\d+)\s*(?:(?P<counted>e|&|\+|and|a|trip|let)"
    r"|:\s*(?P<partial>\d+)\s*/\s*(?P<subdivision>\d+))?",
    re.IGNORECASE,
)


def parse_beat(value: int | str | None, name: str = "beat") -> BeatPosition | None:
    """Read a tool's beat argument (see :data:`BEAT_FORMAT`).

    Raises:
        ToolError: When it does not name a point in a measure.
    """
    if value is None:
        return None
    if isinstance(value, int):
        if value < 1:
            raise ToolError(f"{name} must be >= 1.")
        return BeatPosition(beat=value)
    match = _BEAT.fullmatch(value.strip())
    if match is None:
        raise ToolError(f"{name} must be {BEAT_FORMAT}; got {value!r}.")
    beat = int(match["beat"])
    if match["counted"] is not None:
        subdivision, partial = _COUNTED_PARTIALS[match["counted"].lower()]
    elif match["partial"] is not None:
        partial, subdivision = int(match["partial"]), int(match["subdivision"])
    else:
        subdivision, partial = 1, 1
    if beat < 1:
        raise ToolError(f"{name} must be >= 1.")
    if not 1 <= partial <= subdivision:
        raise ToolError(f"{name}: partial must be between 1 and the subdivision.")
    return BeatPosition(beat=beat, subdivision=subdivision, partial=partial)


def require_measure_range(start_measure: int, end_measure: int) -> None:
    """Validate an inclusive, 1-indexed measure range.

    Raises:
        ToolError: When the range is empty or starts below 1.
    """
    require_measure(start_measure, "start_measure")
    if end_measure < start_measure:
        raise ToolError("end_measure must be >= start_measure.")


async def navigate(
    bridge: ScoreBridge,
    measure: int,
    staff: int | None = None,
    beat: BeatPosition | None = None,
) -> None:
    """Move the application's cursor to *measure* (and *staff* and *beat*, if given).

    Raises:
        BridgeError: When the application refuses to move, so a command
            never runs at the wrong position.
    """
    await bridge.go_to_measure(measure)
    if staff is not None:
        await bridge.go_to_staff(staff)
    if beat is not None:
        await bridge.go_to_beat(beat)
