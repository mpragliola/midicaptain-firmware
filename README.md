# UltraMidi

Custom firmware for the **MidiCaptain Mini 6** MIDI foot controller. Replaces the stock firmware with a fully configurable, text-file-driven system for controlling guitar processors, synthesizers, DAWs, and other MIDI gear.

> **Disclaimer:** use at your own risk. The author assumes no reponsibility for any consequence of this software.

## Why this firmware

The Mini 6 offers easy and open access to its internals, and can become _de facto_ a
prototyping laboratory for MIDI controllers. I decided to write a custom firmware from
scratch both for fun, and as a way to implement functionalities that were absent in
the original firmware.

The result is **a much more flexible system** (though I can't
guarantee about its stability).

* [Hardware specs](docs/specs.md)
* [How to configure](docs/CONFIGURATION.md)
* [Pages](docs/PAGES.md)



## Features

* freely assignable LEDs
* possibility to integrate the functionalities of on-board switches withswitches from
  external controllers, de facto allowing to extend the controllers
* different layout modes 
* 2 parallel cycles
* button grouping
* macros
* free number of pages





* pages can be useful to prepare **specialized configurations**; useful
  if you want to have different configurations for different songs, 
  setlists, bands or target devices
* use them also when 6 footswitches are a limit: you can distribute 
  functionality among pages and widen your control possibilties
* the free assingments allows us to change navigation mode at each page.
  Most of the times it's advisable to **assign page navigation to  the same buttons and actions across pages for consistency**.
  But if you are on page 0, for example, it makes no sense to have a 
  "previous page" assignment (unless you want to cycle to the last), 
  so you could free a slot and make the button perform other actions.

## Aliases

The file `/ultrasetup/aliases.txt` can be edited to modify the **aliases**.
An alias is a sequence of characters that will be substituted in the page 
configuration with its assigned value.

### Defining an alias

Add, delete or modify  in the format:

```
alias_name = <value>;
```

### Use cases for aliases

There are mainly two use cases for aliases.

#### 1. Use aliases as variables

Let's say you want to control a device that is receiving on MIDI channel 4. You
could model your commands by specifying the channel directly, e.g. `[4][PC][2]`;
but what happens if you defined 50 commands and decide to change the MIDI 
channel?

Instead you can assign an alias to channel 4 (e.g. `hxstomp_chan = 4;`) and use
it in command declarations: `[hxstomp_chan][PC][2]`. If one day you decide to change
the receiving channel on the target device, you will have to change the configuration
only in one place.

You can also use aliases as mnemonics for **colors**. The `aliases.txt` files already defines useful color constants prefixed by `C_*`.

#### 2. Use aliases as MIDI mappings

Most of the times your target device(s) will feature a **MIDI implementation chart**,
with the specific commands (usually CC#) and values needed to control functionality.

Aliases can represent those mappings, so that declaring commands is easier to remember
and to understand. 

For example, if I have a Line6 HX Stomp, the mapping tells mne that FootSwitch 1 is
mapped to CC#49. I can define an alias:;

```
line6hxstomp_fs1 = 49
```

and reuse it in command declarations:

```
init_commands = [1][CC][line6hxstomp_fs1][127]
```

### Caveats on alias use

The substitutions are "stupid" and purely based on plain text matching, therefore it's strongly advised to follow these best practices to not confuse the config parser, making sure that your alias:

* is **alphanumeric**
* does not overlap with existing commands (avoid aliases like `PAGE` or `CMD`)
* does not overwrite previous aliases 

To avoid ambiguities a good practice is to **use a prefix scheme**: use `xyz_PAGE` or `xyz_CMD`, and use product-specific prefixes like `line6hxstomp_*` for product-specific mappings. 

## Cycle steps

Each key can **cycle through up to 9 states** on successive presses. Every cycle step carries its own:

- **LED color** (independently for each of the 3 LEDs per key)
- **Display label** (shown on the main status area)
- **MIDI commands** (any combination of PC, CC, Note On, macros, ...)

This means a **single button** can:
- **Toggle** an effect on/off (2-step cycle)
- **Rotate** through presets or amp channels (N-step cycle)
- **Step through** any arbitrary sequence of MIDI actions

The cycle position **persists** across presses and is only reset by a page switch or a radio-group conflict.

### Long press with independent cycle

Keys support both **short press** and **long press** actions. Long presses can have their own **independent cycle** (separate from the main cycle), with dedicated:

- **LED colors** (`ledNl`) — typically used to light a different LED than the main cycle
- **Labels** (`labelNl`) — shown in the stomp sub-grid
- **Commands** (`keyNldn` / `keyNlup`) — fire on long press / long release

This lets a single button handle and provide feedback for
**two different functions** with eventual cycles — for
example, short press to select a preset and long press to
toggle delay.

When `longcycle = [0]` (the default), long press commands share the **main cycle step** instead of maintaining a separate counter.

### Radio groups

Keys assigned to the same **`group`** number (1-31) behave like **radio buttons**: pressing one **deactivates all others** in the group. When a key is deactivated:

- Its **LEDs turn off**
- Its **cycle position resets** to -1 (next press starts from step 1)
- Its **stomp sub-panel clears** (if stompmode is active)

This is the natural behavior for **preset selection**, where only one program should be active at a time — but it works for any mutually exclusive set of actions.

A separate **`longgroup`** provides the same mutual exclusion for **long-press cycles**, independent of the main group. This lets you have, for example, a set of keys where the main press selects an amp model (group) and long press toggles between effects that are mutually exclusive (longgroup).

Groups work **across physical and virtual keys** — an external footswitch can participate in radio-button behavior alongside the physical buttons.

### Group cycle pause

By default, switching between keys in a group **resets their cycle** to step 1. Setting **`group_cycleN = [1]`** in the `[page]` section changes this behavior: each key in group N **remembers its last cycle step**, so returning to a key **resumes where it left off**.

This is useful when keys in a group have **multi-step cycles** — for example, two amp models each with clean/drive variations. Without group cycle pause, switching amps would always reset to clean. With it, each amp remembers whether you were on clean or drive.

### Stomp mode (sub-grid display)

The display has a **3x2 sub-grid** of labeled cells at the bottom, one per physical key. Each cell shows:

- A **short label** (up to 5 characters)
- A **colored background** derived from the first non-null LED color in the step definition

| `stompmode` value | Behavior |
|-------------------|----------|
| **0** (default) | No sub-panel — the cell is hidden |
| **1** | Reflects the **main cycle** state (label + color update on each press) |
| **2** | Reflects the **long-press cycle** state (label + color update on each long press) |

This provides **at-a-glance feedback** for all active keys without having to look at the LEDs — especially useful in dark stage environments or when the key's current state isn't obvious from LED color alone.

### Command macros

Up to **9 reusable command macros** (`cmd1`-`cmd9`) can be defined at two levels:

| Level | Scope | Defined in |
|-------|-------|------------|
| **Global** | Shared across all pages | `[global]` section |
| **Page** | Page-specific, **overrides** global | `[page]` section |

Invoke them with **`[CMD][N]`** from any key action. This avoids repeating the same command sequences across multiple keys — for example, a "reset all effects" macro that every preset key calls before selecting its program.

### Virtual keys (external footswitch expansion)

The firmware addresses **32 keys**: 6 physical (0-5) and **26 virtual** (6-31). Virtual keys are triggered by **incoming MIDI CC** messages via the `ext_capture_cc` setting.

Virtual keys support **all configuration properties** except physical LEDs:

| Feature | Physical keys (0-5) | Virtual keys (6-31) |
|---------|---------------------|---------------------|
| Cycle / longcycle | Yes | Yes |
| Group / longgroup | Yes | Yes |
| Labels (main + long) | Yes | Yes |
| Commands (dn/up/ldn/lup) | Yes | Yes |
| LED colors | Yes | No (no physical LEDs) |
| Stomp sub-panel | Yes | No (panels map to keys 0-5) |

This lets you **integrate external footswitches** (or any MIDI controller) into the device's full feature set. A virtual key can be part of a radio group with physical keys, have its own cycle, send MIDI commands, and update the display — just like a physical button.

### MIDI aliases

An **`aliases.txt`** file maps **human-readable names** to MIDI CC/PC numbers:

```
; instead of remembering that CC#102 is gain:
tx_gain = 102

; use it directly in page configs:
[1][CC][tx_gain][64]
```

Aliases are loaded **once at boot** and apply to all page files. The included alias file ships with pre-built mappings for:

- **AmpliTube TONEX** — all parameters (gain, comp, gate, EQ, mod, delay, reverb, cab)
- **Neural DSP Quad Cortex** — footswitch bypass, scenes, expressions, looper
- **Line 6 HX Stomp** — footswitches, looper, snapshots, tuner

Adding your own device is as simple as appending lines to `aliases.txt`.

### Dual MIDI output

**All MIDI commands** are sent simultaneously over both interfaces:

- **USB-MIDI** — via `adafruit_midi` library
- **DIN-5 MIDI** — raw UART bytes at 31250 baud on GP16/GP17

The DIN-5 output bypasses the `adafruit_midi` library and writes raw bytes directly, working around buffering quirks in CircuitPython 7.3.1. This ensures **reliable, low-latency output** on both interfaces with no additional configuration.

### MIDI Thru

When **`midi_thru = [1]`** is set in the `[global]` section, all incoming MIDI messages are **forwarded to the output**. This allows the device to sit transparently in the middle of a MIDI chain — incoming messages from an upstream controller pass through without being swallowed.

Thru works for both **USB-MIDI** and **DIN-5 UART** inputs, forwarding CC, PC, and Note On messages.

### Init commands

The **`init_commands`** page setting executes a **list of commands automatically** when a page loads. Common uses:

- **`[KEY][n][c][lc]`** — simulate pressing a key on load, selecting a starting preset with its LEDs and label already active
- **MIDI commands** — send bank selects, program changes, or CC resets to initialize external gear to a known state
- **Macros** — call `[CMD][N]` for complex initialization sequences

Init commands run **after** the page is fully loaded and the display is reset, so all key states and LEDs reflect the init actions correctly.

### PC increment / decrement

Program Change commands support **`inc`** and **`dec`** as the value parameter, with an **optional step size**:

| Command | Effect |
|---------|--------|
| `[1][PC][inc]` | Next program (+1) on channel 1 |
| `[1][PC][dec]` | Previous program (-1) on channel 1 |
| `[1][PC][inc][4]` | Jump forward 4 programs (bank skip) |
| `[1][PC][dec][4]` | Jump back 4 programs |

The device **tracks the last PC sent** per channel, so inc/dec always step relative to the current position. This lets you scroll through presets on external gear **without dedicating a button to each one**.

### Multi-line labels

A **colon** (`:`) in a label creates a **two-line display**:

```ini
label1 = [Clean:chorus]   ; shows "Clean" on top, "chorus" below
```

Each line supports up to **8 characters**. The main status label renders in a large **48pt** font; sub-labels in the stomp grid use **24pt**.

### Sub-labels (press/release feedback)

**`labelNd`** (shown on key **d**own) and **`labelNu`** (shown on key **u**p) provide **temporary display feedback** during a press without changing the main status label.

This is useful for keys that **don't change the main label** but still need visual confirmation — for example, showing "FX ON" / "FX OFF" briefly when toggling an effect, while the main status continues to display the current preset name.

### Display customization

Each page can configure the **full visual appearance** of the display:

| Setting | Effect | Default |
|---------|--------|---------|
| **`page_name`** | Title shown in the page bar (up to 9 chars) | `PAGE N` |
| **`color`** | Page name **text** color | `0xF84848` |
| **`bgcolor`** | Page name **background** color | none |
| **`page_bg`** | Solid **background color** for the entire display | `0x000000` (black) |
| **`page_bg_img`** | **BMP wallpaper** from `wallpaper/` folder (overrides `page_bg`) | none |
| **`led_brightness`** | NeoPixel brightness, **0-100%** | 30 |
| **`screen_brightness`** | Display backlight brightness, **0-100%** | 50 |
| **`vis_mainlabel_size`** | Main label size: **0**=hidden, **1**=minuscule, **2**=tiny, **3**=big, **4**=bigger | 3 |
| **`vis_sublabels`** | Number of sublabel cells: **6** (3x2, keys 0-5) or **12** (3x4, keys 0-11) | 6 |

Text color **auto-inverts** based on background luminance — white text on dark backgrounds, black text on bright backgrounds — so labels are always readable regardless of color scheme.

### Visualization modes

The `vis_mainlabel_size` and `vis_sublabels` parameters control the balance between the main status label and the stomp sub-grid. Reducing the main label size gives more vertical space to sublabels — the sublabel font is automatically chosen to be as large as possible for the available cell height.

With `vis_sublabels = [12]`, virtual keys 6-11 get their own sublabel cells (3x4 grid). Define `ledN` on these keys to set sublabel background colors.

See `docs/VISUALIZATIONS.md` for the full layout table and examples.

### Key simulation

The **`[KEY][n][c][lc]`** command simulates pressing another key:

| Parameter | Meaning |
|-----------|---------|
| **`n`** | Key number (0-31) |
| **`c`** | *(optional)* Jump to main cycle step `c` |
| **`lc`** | *(optional)* Jump to long-press cycle step `lc` |

This enables **powerful chaining**: one key can activate another, init commands can set up complex initial states, and macros can orchestrate multiple key presses. The simulated press goes through the **full key pipeline** — group logic, cycle advance, MIDI commands, LED and display updates.

### Boot modes

The device has **two boot modes**, selected by holding **SW1** during power-on:

| SW1 state | Mode | Behavior |
|-----------|------|----------|
| **Released** (normal) | Run mode | USB drive **disabled**, filesystem writable by firmware |
| **Held** during boot | USB mode | USB mass-storage **enabled** (drive label `MIDICAPTAIN`), filesystem exposed for editing |

In USB mode, the device appears as a **removable drive** on the computer, making it easy to edit config files, upload wallpapers, or update aliases — no special software needed.

### Combo actions

Special **button combinations** provide maintenance shortcuts without needing a config entry:

| Combo | Hold time | Action |
|-------|-----------|--------|
| **SW1 + SW3** | 1 second | **Hot-reload** the current page — re-reads the config file and resets all key states without rebooting |
| **SW1 + SW3 + SWA + SWC** | 2 seconds | **Soft reboot** — clean restart of the entire firmware |

The hot-reload is especially useful during **live configuration editing**: change a page file on the device, then hold the combo to see the changes immediately.

## Configuration

All configuration lives in the **`ultrasetup/`** folder as plain text files.

### File structure

| File | Purpose |
|------|---------|
| **`ultrasetup/<name>.txt`** | Config file (all pages in one file, e.g. `init.txt`, `live_rig.txt`) |
| **`ultrasetup/aliases.txt`** | Named aliases for MIDI CC/PC numbers |
| **`ultrasetup/config-template.txt`** | Annotated template showing **all** available options with comments |

### Config file format

Config files use an **INI-like format** with bracket-delimited values. Lines starting with `;` are comments. Each file contains one `[global]` section followed by one or more `[page]` sections (numbered progressively from 0). There are three section types:

---

**`[global]`** — settings that apply across all pages:

```ini
led_brightness = [50]
screen_brightness = [50]
page_bg = [0x300000]
page_bg_img = [wp1]
ext_capture_cc = [1][30]
midi_thru = [1]
cmd1 = [1][CC][2][0] [1][CC][18][0]
```

---

**`[page]`** — page-specific settings:

```ini
page_name = [MAIN]
color = [0x000000]
bgcolor = [0xff0000]
init_commands = [KEY][0][1][]
group_cycle1 = [1]
cmd1 = [1][PC][0] [1][CC][20][127]
```

---

**`[keyN]`** — per-key configuration (N = 0-31, where 0-5 are physical and 6-31 are virtual):

```ini
[key0]
group = [1]
cycle = [3]
longcycle = [2]
longgroup = [1]
stompmode = [1]

; LED colors per cycle step (3 LEDs per key: left, center, right)
; [-] = unchanged, [0x000000] = off
led1 = [0x00ff00][-][0x00ff00]
led2 = [0x0000ff][-][0x0000ff]
led3 = [0x0000ff][-][0x00ff00]

; LED colors for long-press cycle steps
led1l = [-][0xffffff][-]
led2l = [-][0xff00ff][-]

; Labels per cycle step (colon = line break)
label1 = [Clean:chorus]
label2 = [Crunch]
label3 = [Lead]

; Long-press labels (shown in sub-grid for stompmode=2)
label1l = [DLY ON]
label2l = [DLY OF]

; Sub-labels shown during press/release
label1d = [H ON]
label1u = [H OFF]

; Commands per cycle step and action
; Format: keyNaction where N=step (1-based), action=dn|up|ldn|lup
key1dn = [1][PC][1]
key1up = [CMD][1] [1][CC][tx_gain][100]
key2dn = [1][PC][2]
key1ldn = [1][CC][tx_dly_pwr][127]
key2ldn = [1][CC][tx_dly_pwr][0]
```

### Command format

Commands use **bracket-delimited parameters**: `[a][b][c][d]`

| Command | Format | Description |
|---------|--------|-------------|
| **Program Change** | `[channel][PC][value]` | Send PC. Value can be a number, **`inc`**, or **`dec`** (with optional step) |
| **Control Change** | `[channel][CC][control][value]` | Send CC. Control and value can use **aliases** |
| **Note On** | `[channel][NT][note][velocity]` | Send Note On |
| **Page switch** | `[PAGE][n]` | Switch to page `n` (or **`inc`**/**`dec`**). Commands after PAGE are ignored |
| **Key simulation** | `[KEY][n][c][lc]` | Simulate key `n` press, optionally at cycle step `c` / long step `lc` |
| **Macro** | `[CMD][n]` | Execute macro `n` (1-9, defined in `[global]` or `[page]`) |

**Multiple commands** can be chained on one line, separated by spaces:

```ini
key1up = [CMD][1] [1][PC][36] [1][CC][tx_comp_pwr][0]
```

> **Note:** `channel` is always **1-based** (1-16). Values can be **decimal** or **hex** (`0x7F`).

### Virtual key capture protocol

Set **`ext_capture_cc = [channel][CC#]`** in `[global]` to enable external control. The device listens for CC messages on that channel/number and decodes the **CC value** as a key index + action:

| CC Value | Formula | Action |
|----------|---------|--------|
| **0-31** | K | **Press** key K |
| **32-63** | K + 32 | **Long press** key K |
| **64-95** | K + 64 | **Release** key K |
| **96-127** | K + 96 | **Long press release** key K |

The external controller must encode the **correct action values**. For a worked example: to control virtual key 8, the external device sends CC values **8** (press), **40** (long press), **72** (release), and **104** (long press release).

See `docs/CAPTURE.md` for full protocol details and additional examples.

## Project structure

```
ultramidi/
  boot.py              Boot-mode selection (USB drive vs. normal)
  code.py              Entire firmware: hardware init, async tasks,
                       config parser, MIDI engine, display renderer
  ultrasetup/          User configuration
    <name>.txt           Config files (all pages in one file)
    aliases.txt          MIDI CC/PC name aliases
    config-template.txt  Annotated config template
  fonts/               PCF bitmap fonts (Bahnschrift 24-72pt)
  wallpaper/           Optional BMP background images (240x240)
  lib/                 CircuitPython libraries (adafruit_midi,
                       adafruit_st7789, neopixel, asyncio, etc.)
  docs/                Documentation
    ARCHITECTURE.md      Hardware and firmware architecture
    COMMANDS.md          Command format reference
    CAPTURE.md           External control / virtual key protocol
    VISUALIZATIONS.md    Display layout modes and examples
    examples.md          Configuration examples for all features
```

## Architecture

The firmware is a **single cooperative-multitasking application** built on `asyncio`, running three concurrent tasks:

| Task | Responsibility |
|------|---------------|
| **`key_check`** | Polls all 6 GPIO switches with per-key **debouncing** (20ms), **short press** detection (fires on release), and **long press** detection (fires at 500ms threshold while held) |
| **`disp_task`** | **Batched display refresh**, decoupled from input so glyph rendering never blocks switch polling |
| **`midi_in_task`** | Polls **USB-MIDI** and **DIN-5 UART** for incoming CC messages matching the capture configuration |

All three tasks yield cooperatively with `await asyncio.sleep(0)`, ensuring **responsive input** even during display updates.

See `docs/ARCHITECTURE.md` for full hardware details, pin assignments, display layer stack, and the key behavioral model.

## License

See the `license` directory for license information.
