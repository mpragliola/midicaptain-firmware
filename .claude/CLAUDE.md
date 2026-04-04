# UltraMidi

Custom CircuitPython firmware for the **MidiCaptain Mini 6** MIDI foot controller (RP2040).
Text-file-driven configuration system for controlling guitar processors, synths, and DAWs
via USB-MIDI and DIN-5 MIDI.

**MCU**: RP2040 — 264 KB RAM, 2 MB flash. **Runtime**: CircuitPython 7.3.1.

## Architecture

```
code.py      — Entry point: hardware init, async event loop (key_check, disp_task, midi_in_task)
engine.py    — Command execution, key handlers, page/config switching, Explorer Mode
config.py    — Config file parser, alias substitution, config discovery
state.py     — Shared runtime state, constants, hardware references (module-level globals)
validate.py  — On-device config validator (runs at page load)
boot.py      — Boot-mode selector (USB mass-storage vs normal)
```

All state lives in `state.py` as module-level variables (imported as `S`). Hardware references
are assigned by `code.py` during init — they are `None` until then.

Three cooperative asyncio tasks: `key_check()`, `disp_task()`, `midi_in_task()`.
All yield with `await asyncio.sleep(0)`. Never block the event loop.

## Rules

See `.claude/rules/` for detailed guidance:
- `firmware-constraints.md` — CircuitPython coding rules (auto-loaded when editing `.py` files)
- `config-format.md` — config file syntax and key naming (auto-loaded for `ultrasetup/`)
- `workflow.md` — dev workflow, commit style, docs maintenance
- `off-limits.md` — files that must not be modified
