# Getting started

> Tutorial -- set up mcp-score and generate your first score.

## Prerequisites

- Python 3.14+
- An MCP-compatible client (Claude Desktop, Claude Code, etc.)
- [MuseScore Studio 4.4.2+](https://musescore.org/en/download) (optional -- needed for live manipulation features)

## Installation

```bash
pip install mcp-score-server
```

Or with uv:

```bash
uv tool install mcp-score-server
```

### Install the score generation skill

```bash
mcp-score install-skill
```

This copies the `score-generate` skill to `~/.claude/skills/score-generate/`.

### Install the MuseScore plugin (optional)

```bash
mcp-score install-plugin
```

This copies the WebSocket bridge plugin to `~/Documents/MuseScore4/Plugins/`. Restart MuseScore, then enable it: Plugins > Manage plugins > MCP Score Bridge. Running the plugin opens a status window; keep it open while you work.

## Configure your MCP client

### Claude Code

```bash
claude mcp add mcp-score -- mcp-score serve
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-score": {
      "command": "mcp-score",
      "args": ["serve"]
    }
  }
}
```

## Generate your first score

With the `score-generate` skill installed, just ask Claude:

> "Create a 12-bar blues lead sheet in Bb major at 120 BPM."

Claude writes a music21 Python script, runs it, and produces a `.musicxml` file on your Desktop. Open it in MuseScore.

More examples:

> "Write a big band chart -- 32-bar AABA form, Bb major, slow blues at 66 BPM. Standard big band instrumentation: 5 saxes, 4 trumpets, 4 trombones, piano, guitar, bass, drums."

> "Create a string quartet in D major, 3/4 time, 16 measures at 72 BPM."

### Other MCP clients

Clients other than Claude Code cannot load the skill, so the server offers the same workflow as tools. Ask the assistant to read `score_generation_guide` (or load the `score-generate` prompt, if the client supports prompts) and then call `generate_score` with its music21 script. The tool runs the script and returns the paths of the files it wrote.

## Live MuseScore manipulation

For reading and modifying a score that's already open in MuseScore:

1. Open a score in MuseScore Studio 4.4.2 or later
2. Start the MCP Score Bridge plugin (Plugins menu) and keep its window open
3. Ask Claude:

> "Connect to MuseScore."

> "What's in the score right now?"

> "Read measures 1 through 8 of the first staff."

> "Add a rehearsal mark 'A' at measure 1 and a double barline at measure 8."

> "Transpose the trumpet part in measures 5-8 up a perfect fourth (5 semitones)."

> "Undo that last change."

All modifications happen immediately in MuseScore.

## Live Dorico manipulation (experimental)

Dorico support is experimental: it uses Dorico's undocumented Remote Control WebSocket API, is command-only (it cannot read note content), and has not been verified against a running Dorico instance. To try it, enable Remote Control in Dorico's preferences and ask Claude to "Connect to Dorico."

## Live Sibelius manipulation (experimental)

Sibelius support is experimental: it follows Avid's ManuScript Language Guide but has not been run against a real Sibelius. It needs Sibelius 2024.3 or later and a ManuScript plug-in that Sibelius Connect calls:

```bash
mcp-score install-sibelius-plugin
```

This copies `McpScoreBridge.plg` into Sibelius's per-user plug-ins folder (`%APPDATA%\Avid\Sibelius\Plugins` on Windows, `~/Library/Application Support/Avid/Sibelius/Plugins` on macOS). Restart Sibelius, enable Sibelius Connect on the Input Devices page of its preferences, open a score and ask Claude to "Connect to Sibelius." Sibelius asks you to allow the connection the first time.

Besides the tools that work with MuseScore, Sibelius can also take articulations, noteheads, lines (slurs, hairpins, trills, octave lines, pedal, glissandi), staff text and clefs:

> "Put staccatos on every note in measures 1-4 of the flute."

> "Use slash noteheads in the guitar part from measure 9 to 16."

> "Add a crescendo hairpin over measures 5-6 and write 'pizz.' at measure 7 of the cello."

### Scoring percussion

The Sibelius tools cover what a battery and front ensemble score needs. Notes, rests and tuplets go where the last one ended, or at a point you name: a beat (`3`), a counted partial (`"2&"`, `"4e"`, `"1a"`, `"3trip"`, `"3let"`) or any tuplet partial as `"beat:partial/subdivision"` (`"4:3/5"`). Edits such as accents, noteheads and tremolos can be limited to that point in every measure. Dynamics, text and hairpins can sit on any beat. Tremolos cover measured diddles, unmeasured rolls, buzz rolls and rolls between two mallet notes. Flams, drags and ruffs go before a note, and sticking goes under the notes. Accents, cross noteheads for rim shots and the percussion clef come from the tools above. On a percussion staff, a note's pitch picks the instrument through the staff's drum map. For example:

> "In the snare part, measure 1: four sixteenths on beat 1, an eighth-note triplet on beat 2, then a quarter note with a flam and an accent on beat 3, and a quarter rest."

> "Buzz roll the snare in measures 9-12 with a crescendo from mp on beat 1 of measure 9 to ff on beat 4 of measure 12."

> "Write the sticking RLRR LRLL under measure 5 of the snare."

> "Roll the marimba's half notes in measures 17-24 with double tremolos, and put an sfz on beat 1 of measure 25."

> "Accent the 'and' of 2 and the last triplet partial of beat 4 in measures 1-8 of the tenors."

To write a lot at once, the assistant can use `write_live_passage`: one call takes every note, chord and rest of a passage in order, each with its own notehead, accents, tremolo or buzz, flam, drag or ruff, sticking letter and dynamic, and tuplets. Asking for a few measures of a part at a time is much faster than note by note:

> "Write measures 1-4 of the snare part: sixteenths RLRR LRLL on beats 1-2, an accented flam on 3, a buzz on 4, and repeat with a triplet on beat 2 of measure 3."

If the score uses the Virtual Drumline (VDL) template, the assistant can read the `vdl_notehead_guide` tool first. VDL picks each battery sound (left or right hand, shot, rim, dread, crush, roll) by notehead number, and the guide lists those numbers for `set_live_notehead` and `write_live_passage`:

> "In the SnareLine, make the notes on the e of every beat in measure 3 left-hand rim clicks."

## Next steps

- [Architecture](architecture.md) -- understand how mcp-score is structured
- [Tool reference](reference.md) -- complete list of MCP tools
- [MuseScore plugin](musescore-plugin.md) -- detailed plugin setup
