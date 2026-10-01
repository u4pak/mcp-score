"""Static checks on the bundled Sibelius plug-in file.

The plug-in runs inside Sibelius, so its behaviour cannot be tested here.
What can be checked is that it defines every method the bridge calls,
that its methods take the arguments the bridge passes, and that nothing
but its manual ``Run`` entry point opens a dialog, which would block
Sibelius while nobody is there to close it.
"""

from __future__ import annotations

import re

from mcp_score.bridge.sibelius import PluginMethod
from mcp_score.resources import SIBELIUS_PLUGIN_DIRECTORY, package_path
from mcp_score.sibelius.paths import PLUGIN_FILE_NAME

# A method entry in a .plg file: a tab, its name, then its parameter list
# and body inside one double-quoted string ending in ``}"``.
_METHOD = re.compile(r'^\t(\w+) "\(([^)]*)\) \{(.*?)\}"$', re.MULTILINE | re.DOTALL)

# How many arguments the bridge passes to each method it calls.
_BRIDGE_ARGUMENT_COUNTS: dict[PluginMethod, int] = {
    PluginMethod.PING: 0,
    PluginMethod.GET_SCORE: 0,
    PluginMethod.GET_CURSOR_INFO: 3,
    PluginMethod.GO_TO: 2,
    PluginMethod.SELECT_RANGE: 4,
    PluginMethod.ADD_NOTE: 5,
    PluginMethod.ADD_REHEARSAL_MARK: 2,
    PluginMethod.ADD_CHORD_SYMBOL: 4,
    PluginMethod.ADD_DYNAMIC: 4,
    PluginMethod.SET_KEY_SIGNATURE: 3,
    PluginMethod.SET_TIME_SIGNATURE: 4,
    PluginMethod.SET_TEMPO: 3,
    PluginMethod.APPEND_BARS: 1,
    PluginMethod.TRANSPOSE: 6,
    PluginMethod.SET_ARTICULATION: 6,
    PluginMethod.SET_NOTEHEAD: 5,
    PluginMethod.ADD_LINE: 4,
    PluginMethod.ADD_STAFF_TEXT: 5,
    PluginMethod.SET_CLEF: 4,
}


def _methods() -> dict[str, tuple[list[str], str]]:
    """Each method of the bundled plug-in: its parameter names and body."""
    source = package_path(str(SIBELIUS_PLUGIN_DIRECTORY / PLUGIN_FILE_NAME))
    text = source.read_text(encoding="utf-8")
    return {
        name: ([p.strip() for p in parameters.split(",") if p.strip()], body)
        for name, parameters, body in _METHOD.findall(text)
    }


def test_every_method_the_bridge_calls_takes_its_arguments() -> None:
    # Arrange
    methods = _methods()

    # Act
    arities = {
        method: len(methods[method][0]) for method in PluginMethod if method in methods
    }

    # Assert: the table covers every method, and the plug-in matches it
    assert set(_BRIDGE_ARGUMENT_COUNTS) == set(PluginMethod)
    assert arities == _BRIDGE_ARGUMENT_COUNTS


def test_only_the_manual_entry_point_opens_a_dialog() -> None:
    # Arrange
    methods = _methods()

    # Act
    showing_dialogs = sorted(
        name
        for name, (_, body) in methods.items()
        if re.search(r"MessageBox|ShowDialog|YesNoMessageBox", body)
    )

    # Assert
    assert showing_dialogs == ["Run"]


def test_method_bodies_quote_strings_with_single_quotes() -> None:
    # Arrange: a double quote inside a body would end the method's string
    methods = _methods()

    # Act
    with_double_quotes = sorted(
        name for name, (_, body) in methods.items() if '"' in body
    )

    # Assert
    assert with_double_quotes == []
