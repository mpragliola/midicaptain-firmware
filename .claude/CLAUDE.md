# UltraMidi - Claude Code Configuration

## What This Is

Custom CircuitPython firmware for the **MidiCaptain Mini 6** MIDI foot controller (RP2040).
Text-file-driven configuration system for controlling guitar processors, synths, and DAWs
via USB-MIDI and DIN-5 MIDI.

## Critical Constraints

- **MCU**: RP2040 — 264 KB RAM, 2 MB flash. Every byte matters.
- **Runtime**: CircuitPython 7.3.1 — no threads, no typing module, limited stdlib.
- **No automated tests** — this is bare-metal embedded firmware tested on hardware.
- **No build step** — CircuitPython interprets `.py` files directly on device.

### What This Means for Code Changes

- Avoid unnecessary object allocations, list comprehensions over large data, or string concatenation in loops. Prefer pre-allocated buffers and in-place mutation.
- Do not add type hints — CircuitPython 7.3.1 does not support `typing`.
- Do not add `dataclasses`, `enum`, `pathlib`, or other CPython-only modules.
- Keep imports minimal; each import costs RAM.
- Avoid adding new `.py` files unless absolutely necessary — each module has import overhead.
- Never use f-strings (not supported in CP 7.3.1). Use `.format()` or `%` formatting.
- `gc.collect()` is used deliberately — do not remove those calls.

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

### Async Model

Three cooperative tasks via `asyncio`, all yielding with `await asyncio.sleep(0)`:
- `key_check()` — GPIO polling, debounce (20ms), short/long press detection
- `disp_task()` — batched display refresh (decoupled from input to avoid blocking)
- `midi_in_task()` — USB-MIDI + UART input polling

Never block the event loop. No `time.sleep()` in the main loop.

## Configuration System

- Configs are `.txt` files directly under `ultrasetup/` (e.g. `init.txt`, `live_rig.txt`)
- The filename (without `.txt`) is the config name shown in Explorer Mode
- Each file contains one `[global]` section, then multiple `[page]` sections (numbered progressively from 0), each followed by its `[keyN]` sections
- `aliases.txt` and `config-template.txt` are excluded from config discovery
- Global aliases in `ultrasetup/aliases.txt`
- Template with all options documented: `ultrasetup/config-template.txt`

### Config Syntax

Sections: `[global]`, `[page]` (repeatable), `[key0]`-`[key31]` (per page)
Values are bracket-delimited: `[channel][CC][control][value]`
Cycle steps are 1-based in config, 0-based internally.
Colors: hex `0xRRGGBB`, `-` = unchanged, `0x000000` = off.

## Key Naming

| Name | Index | Type |
|------|-------|------|
| SW1-SW3 | 0-2 | Physical footswitches |
| SWA-SWC | 3-5 | Physical footswitches |
| V6-V31 | 6-31 | Virtual keys (via MIDI CC input) |

## Development Workflow

1. Edit code locally
2. `sync_to_device.py` watches and copies changes to device at `G:/`
3. Device executes code directly (no compilation)
4. Hot-reload: hold SW1+SW3 for 1s to reload current page config without reboot
5. Debug: set `DEBUG = True` in `state.py` for console logging

## Commit Style

Use imperative mood. Describe the *what* and *why*. Examples from history:
- "Implement validator. It will check among other things also recursion..."
- "Sync script:: show free space. Space is an important constraint..."
- "Guard against division by zero in _compute_vis_layout"

## Documentation

Docs live in `docs/`. Key files:
- `ARCHITECTURE.md` — hardware pins, MCU specs, firmware internals
- `COMMANDS.md` — command reference
- `PAGES.md` — page system and Explorer Mode
- `CONFIGURATION.md` — config file format
- `VISUALIZATIONS.md` — display layout modes

When making structural changes to the firmware, update `docs/ARCHITECTURE.md`.
When changing config format or commands, update the relevant doc and `ultrasetup/config-template.txt`.

## Files NOT to Modify

- `lib/` — pre-compiled CircuitPython libraries (`.mpy` files), managed externally
- `fonts/` — pre-built PCF bitmap fonts
- `wallpaper/` — user BMP images
- `boot.py` — rarely needs changes (boot mode selection)
- `sync_config.ini` — local dev machine config, gitignored
