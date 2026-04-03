# Architecture

## Device

**MidiCaptain Mini 6** running the **UltraMidi** custom firmware.

A 6-footswitch MIDI controller for controlling music gear (guitar processors, synthesizers, DAWs) over USB-MIDI and classic DIN-5 MIDI.

## Board

| Field   | Value |
|---------|-------|
| Board   | Raspberry Pi Pico |
| MCU     | RP2040 (dual Cortex-M0+, 264 KB RAM, 2 MB flash) |
| Runtime | Adafruit CircuitPython 7.3.1 (2022-06-22) |
| Board ID | `raspberry_pi_pico` |

## Components and Pins

### Display: ST7789 240x240 TFT (SPI)

| Signal    | Pin  |
|-----------|------|
| SPI Clock | GP14 |
| SPI MOSI  | GP15 |
| D/C       | GP12 |
| CS        | GP13 |
| Backlight | GP8 (PWM, active-low) |

SPI baudrate 62.5 MHz. 180 degree rotation, row offset 80.

### NeoPixel LEDs: 18x WS2812B

| Signal | Pin |
|--------|-----|
| Data   | GP7 |

3 LEDs per footswitch, brightness 30%, batch-updated (`auto_write=False`).

### Footswitches: 6x momentary (active-low, internal pull-ups)

| Switch | Pin  |
|--------|------|
| SW1    | GP1  |
| SW2    | GP25 |
| SW3    | GP24 |
| SWA    | GP9  |
| SWB    | GP10 |
| SWC    | GP11 |

32 addressable keys total (6 physical + 26 virtual via incoming MIDI CC).

### MIDI Output: dual interface

| Interface  | Detail |
|------------|--------|
| USB-MIDI   | `usb_midi.ports[1]` via `adafruit_midi` |
| UART DIN-5 | GP16 (TX) / GP17 (RX), 31250 baud, raw bytes |

UART bypasses `adafruit_midi` to work around CP 7.3.1 buffering quirks.

### MIDI Input

USB-MIDI and DIN-5 UART (`usb_midi.ports[0]` + UART RX), all 16 channels. Receives CC messages for virtual-key control. UART input uses a custom running-status parser.

### Boot Mode (GP1 / SW1, read in boot.py)

| State | Behaviour |
|-------|-----------|
| Released (high) | Normal boot: USB drive disabled, filesystem writable |
| Held (low) | USB mass-storage mode (label MIDICAPTAIN), filesystem read-only |

## How the Firmware Works

### Entry point

CircuitPython auto-executes `code.py` on boot. There is no OS; the firmware is a single cooperative-multitasking application built on `asyncio`.

### Boot sequence

1. **boot.py** reads GP1 to select USB-drive vs. normal mode; sets filesystem writability.
2. **code.py** initialises all hardware (SPI display, PWM backlight, GPIO switches, NeoPixels, UART), loads fonts, reads global aliases from `ultrasetup/aliases.txt`.
3. **Config discovery**: scans `ultrasetup/` for `.txt` config files. Prefers `init.txt` if it exists, otherwise picks the first config file alphabetically. Sets `S.cfg_name` to the chosen config name.
4. Loads page 0 from `ultrasetup/<config>.txt`, builds the display layer stack, applies the page layout (LEDs, labels, sublabels), runs `init_commands`, then enters the async event loop.

### Async event loop

`asyncio.run(main())` launches three concurrent tasks:

```
main()
 |-- key_check()     switch polling, debounce, press/long-press detection
 |-- disp_task()     batched display refresh
 +-- midi_in_task()  USB-MIDI + UART MIDI input polling
```

All three yield cooperatively with `await asyncio.sleep(0)`.

#### key_check(): input handling

Polls all 6 GPIOs every iteration with a per-key state machine:

- **Debounce:** 20 ms stability window.
- **Short press:** fires on *release* (hold < 500 ms).
- **Long press:** fires as soon as 500 ms threshold is crossed while still held.
- **Key combos** (checked after the per-key loop each iteration):

| Combo | Hold time | Action | Notes |
|-------|-----------|--------|-------|
| SW3 + SWA (keys 2+3) | 0.5 s | Enter Explorer Mode | Config browser; releases are suppressed to prevent false cancel/down |
| SW1 + SW3 (keys 0+2) | 1.0 s | Hot-reload current page | Disabled while Explorer Mode is active |
| SW1 + SW3 + SWA + SWC (keys 0+2+3+5) | 2.0 s | Reboot (microcontroller.reset) | Disabled while Explorer Mode is active |

On a confirmed event the task advances the key cycle position, executes the command list for that step/action, updates LEDs, and queues pending label changes (setting `display_dirty = True`).

**Explorer mode gating:** When `S.explorer_mode` is True, key events are
routed to `explorer_press()` (falling edge) and `explorer_key()` (rising edge)
instead of the normal performance handlers. Long-press detection still runs
(for the `is_long` flag) but `longpress_key()` is skipped. The reload and
reboot combos are gated out entirely.

**Combo suppression:** When the SW3+SWA explorer combo fires, a
`_combo23_suppressed` flag is set. This prevents the subsequent release of
keys 2 and 3 from triggering `explorer_key(2)` (cancel) or `explorer_key(3)`
(cursor down). The flag clears once both keys are fully released.

#### disp_task(): display management

Decouples rendering from input so that glyph rasterisation never blocks switch polling:

1. Watches `display_dirty`.
2. When set, applies all pending text and colour changes to `displayio` label objects in one batch.
3. Clears the flag, calls `display.refresh()`, and yields.

ST7789 runs with `auto_refresh=False`; `display.refresh()` is called explicitly after each batch update or explorer render.

**Explorer mode:** `disp_task()` is not involved in explorer rendering. Explorer mode never sets `display_dirty`; instead, `_explorer_render()` and `enter_explorer()` call `S.display.refresh()` directly after updating the explorer group. The two display paths do not interfere.

#### midi_in_task(): external control

Polls both USB-MIDI and DIN-5 UART for incoming messages. ControlChange messages matching the configured channel/CC (`ext_capture_cc`) trigger virtual-key events. CC value encodes both the key index (bits 0-4) and the action type (bits 5-6):

| Value range | Action |
|-------------|--------|
| 0x00-0x1F   | Short press down |
| 0x20-0x3F   | Long press down |
| 0x40-0x5F   | Short release |
| 0x60-0x7F   | Long release |

Optionally forwards all incoming MIDI to the other output (midi_thru): USB input is forwarded to DIN-5, DIN-5 input is forwarded to USB.

### Display layer stack

10-layer displayio.Group (S.splash — the performance display):

| Layer | Content |
|-------|---------|
| 0 | Background: BMP wallpaper (wallpaper/) or solid colour |
| 1 | Status label: 48 pt Bahnschrift, active key text |
| 2-7 | Sub-grid: 6 stomp cells (3x2), each with coloured tile + 24 pt label |
| 8 | Page bar: full-width colour behind page name |
| 9 | Page label: terminal font at 2x scale |

Text colour auto-inverts (white on dark / black on bright) via luminance calculation.

**Explorer Mode display:** A separate `displayio.Group` is created on entry
with plain `Label` objects only (no tiles). It is swapped in via
`S.display.show(grp)` and swapped out via `S.display.show(S.splash)` on exit.
See [Explorer Mode in PAGES.md](PAGES.md#explorer-mode--switching-configs-at-runtime)
for the display layout and key map.

### Key behavioural model

- **Cycle:** each key can cycle through N steps on successive presses; position persists until page switch or radio-group conflict.
- **Long-press cycle:** independent counter (or shared with main cycle when longcycle is 0).
- **Radio groups:** keys in the same group are mutually exclusive. Pressing one deactivates the others.
- **Stomp mode:** keys with stompmode > 0 show their current state in the sub-grid cells.

### Command pipeline

Config-driven. Each key/step/action maps to a list of commands:

| Command | Effect |
|---------|--------|
| PAGE    | Switch to page N (or inc/dec) |
| KEY     | Simulate pressing another key |
| PC      | MIDI Program Change |
| CC      | MIDI Control Change |
| NT      | MIDI Note On |
| CMD     | Run macro (page or global) |

### Configuration

- **Configs:** each configuration is a `.txt` file under `ultrasetup/` (e.g. `init.txt`, `live_rig.txt`). The active config is chosen at boot (`init.txt` preferred, else first alphabetically). Can be switched at runtime via Explorer Mode.
- **Config file format:** INI-like with bracket-delimited values. One `[global]` section (shared settings), then multiple `[page]` sections numbered progressively from 0, each followed by its `[key0]` through `[key31]` sections.
- **Aliases:** `ultrasetup/aliases.txt` (global) maps symbolic names to values for use in all config files. Scalar aliases map to a single integer (e.g. `tx_gain = 102`). Tuple aliases map to a bracket sequence (e.g. `MY_LED = [C_GREEN][*][*]`) and expand inline wherever `[MY_LED]` appears. Tuple aliases cascade: inner alias tokens are resolved at load time in file order.
- **Explorer Mode:** SW3+SWA held 0.5 s opens a full-screen config browser. Uses a dedicated `displayio.Group` with plain `Label` objects (no tiles). LEDs show role colors at dim intensity, brightening on press. On confirm, `switch_config()` loads page 0 of the selected config and returns to performance mode.

## File Map

| Path | Role |
|------|------|
| boot.py | Boot-mode selection (USB drive vs. normal) |
| code.py | Main entry point: hardware init, async tasks (key_check, disp_task, midi_in_task) |
| state.py | Shared runtime state, constants, and hardware references |
| config.py | Config file parser: aliases, list_configs(), load_page() |
| engine.py | Command execution, key handlers, page/config switching, Explorer Mode |
| validate.py | Page config validator (runs on-device at page load) |
| lib/ | Pre-compiled CircuitPython libraries (~133 KB): asyncio, adafruit_midi, adafruit_st7789, neopixel, display_text, bitmap_font, etc. |
| ultrasetup/aliases.txt | Global MIDI aliases shared by all configs |
| ultrasetup/&lt;name&gt;.txt | Config file; contains [global], [page], and [keyN] sections for all pages |
| ultrasetup/config-template.txt | Reference template with all config options documented |
| fonts/ | PCF bitmap fonts (~209 KB): Bahnschrift at 24, 32, 48, 64 pt |
| wallpaper/ | Optional BMP background images (~174 KB) |
