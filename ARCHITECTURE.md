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

USB-MIDI only (`usb_midi.ports[0]`), all 16 channels. Receives CC messages for virtual-key control.

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
2. **code.py** initialises all hardware (SPI display, PWM backlight, GPIO switches, NeoPixels, UART), loads fonts, reads global aliases from `ultrasetup/aliases.txt`, loads page 0 config from `ultrasetup/page0.txt`, builds the display layer stack, then enters the async event loop.

### Async event loop

`asyncio.run(main())` launches three concurrent tasks:

```
main()
 |-- key_check()     switch polling, debounce, press/long-press detection
 |-- disp_task()     batched display refresh
 +-- midi_in_task()  USB-MIDI input polling
```

All three yield cooperatively with `await asyncio.sleep(0)`.

#### key_check(): input handling

Polls all 6 GPIOs every iteration with a per-key state machine:

- **Debounce:** 20 ms stability window.
- **Short press:** fires on *release* (hold < 500 ms).
- **Long press:** fires as soon as 500 ms threshold is crossed while still held.
- **Combos:** SW1+SW3+SWA+SWC held 2 s triggers microcontroller.reset(); SW1+SW3 held 1 s hot-reloads the current page.

On a confirmed event the task advances the key cycle position, executes the command list for that step/action, updates LEDs, and queues pending label changes (setting `display_dirty = True`).

#### disp_task(): display management

Decouples rendering from input so that glyph rasterisation never blocks switch polling:

1. Watches `display_dirty`.
2. When set, applies all pending text and colour changes to `displayio` label objects in one batch.
3. Clears the flag and yields.

ST7789 runs with `auto_refresh=True`; DMA pushes the framebuffer in the background.

#### midi_in_task(): external control

Polls USB-MIDI for ControlChange messages matching the configured channel/CC (`ext_capture_cc`). CC value encodes both the key index (bits 0-4) and the action type (bits 5-6):

| Value range | Action |
|-------------|--------|
| 0x00-0x1F   | Short press down |
| 0x20-0x3F   | Long press down |
| 0x40-0x5F   | Short release |
| 0x60-0x7F   | Long release |

Optionally forwards all incoming MIDI to output (midi_thru).

### Display layer stack

10-layer displayio.Group:

| Layer | Content |
|-------|---------|
| 0 | Background: BMP wallpaper (wallpaper/) or solid colour |
| 1 | Status label: 48 pt Bahnschrift, active key text |
| 2-7 | Sub-grid: 6 stomp cells (3x2), each with coloured tile + 24 pt label |
| 8 | Page bar: full-width colour behind page name |
| 9 | Page label: terminal font at 2x scale |

Text colour auto-inverts (white on dark / black on bright) via luminance calculation.

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

- **Page files:** `ultrasetup/pageN.txt` in INI-like format with bracket-delimited values. Sections: [global], [page], [key0] through [key31].
- **Aliases:** `ultrasetup/aliases.txt` maps symbolic names to integers (e.g. tx_gain = 102) for use in page files.

## File Map

| Path | Role |
|------|------|
| boot.py | Boot-mode selection (USB drive vs. normal) |
| code.py | Entire firmware (~1115 lines): hardware init, async tasks, config parser, MIDI engine, display renderer |
| lib/ | Pre-compiled CircuitPython libraries (~133 KB): asyncio, adafruit_midi, adafruit_st7789, neopixel, display_text, bitmap_font, etc. |
| ultrasetup/ | User configuration: page files (pageN.txt), aliases (aliases.txt) |
| fonts/ | PCF bitmap fonts (~209 KB): Bahnschrift at 24, 32, 48 pt |
| wallpaper/ | Optional BMP background images (~174 KB) |
