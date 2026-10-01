"""Reference guides: notation knowledge an assistant reads before writing.

The VDL notehead guide (`guides/vdl.md`) says which notehead plays
each sound of the Virtual Drumline battery instruments in Sibelius.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_score.resources import GUIDES_DIRECTORY, package_path
from mcp_score.tools import ToolError

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

__all__ = ["VDL_PROMPT_NAME", "load_vdl_guide", "register"]

VDL_GUIDE_FILE = "vdl.md"
VDL_PROMPT_NAME = "vdl-noteheads"
"""Name of the MCP prompt that serves the VDL notehead guide."""


def load_vdl_guide() -> str:
    """The bundled VDL notehead guide.

    Raises:
        FileNotFoundError: When the guide is not bundled.
    """
    return package_path(str(GUIDES_DIRECTORY / VDL_GUIDE_FILE)).read_text(
        encoding="utf-8"
    )


def vdl_notehead_guide() -> str:
    """Return the VDL (Virtual Drumline) notehead guide for the drumline battery.

    Read this before writing or editing snare, tenor, bass drum or cymbal
    line parts in a Sibelius score built on the VDL template. VDL picks
    each sound (left or right hand, hit, shot, rim, dread, rod, crush,
    roll...) by notehead number, and many of those noteheads look alike;
    the guide lists the number for every sound, to pass to
    set_live_notehead, and which sounds take a buzz or tremolo strokes.
    Takes no parameters.

    Returns the guide as Markdown.
    """
    try:
        return load_vdl_guide()
    except FileNotFoundError as exception:
        raise ToolError(str(exception)) from None


def vdl_noteheads_prompt() -> str:
    """Serve the VDL notehead guide as a prompt for clients that support them."""
    return load_vdl_guide()


def register(server: MCPServer) -> None:
    server.tool()(vdl_notehead_guide)
    server.prompt(
        name=VDL_PROMPT_NAME,
        title="VDL notehead guide",
        description=(
            "Load the Virtual Drumline notehead numbers for the battery "
            "before writing drumline parts in Sibelius."
        ),
    )(vdl_noteheads_prompt)
