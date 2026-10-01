"""Where Sibelius keeps user plug-ins.

Sibelius loads per-user plug-ins from ``Avid/Sibelius/Plugins`` in the
user's application data folder, one subfolder per plug-in category.
Sibelius runs on Windows and macOS only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["PLUGIN_CATEGORY", "PLUGIN_FILE_NAME", "plugins_directory"]

PLUGIN_CATEGORY = "MCP Score"
"""The category subfolder the bridge plug-in is installed into."""

PLUGIN_FILE_NAME = "McpScoreBridge.plg"
"""The plug-in's file; its name without ``.plg`` is how Sibelius Connect calls it."""

_WINDOWS_APPDATA_ENV_VAR = "APPDATA"


def plugins_directory(home: Path | None = None, platform: str = sys.platform) -> Path:
    """Sibelius's per-user plug-ins directory on *platform*."""
    home = home or Path.home()
    if platform == "win32":
        appdata = os.environ.get(_WINDOWS_APPDATA_ENV_VAR)
        roaming = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return roaming / "Avid" / "Sibelius" / "Plugins"
    return home / "Library" / "Application Support" / "Avid" / "Sibelius" / "Plugins"
