# =============================================================================
# UltraMidi firmware — main entry point
# Runs on a MidiCaptain Mini 6 (RP2040 / CircuitPython 7.3.1).
# Reads page config from ultrasetup/pageN.txt, manages 6 footswitches,
# 18 NeoPixel LEDs (3 per switch), a 240×240 ST7789 display and dual MIDI out
# (USB-MIDI + classic DIN-5 via UART).
# =============================================================================

import os
import time
import microcontroller
import usb_midi as _usb_midi
import adafruit_midi
from adafruit_midi.program_change import ProgramChange
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_on import NoteOn
import board
import busio
import displayio
import terminalio
import pwmio
import digitalio
import asyncio
import neopixel
try:
    from adafruit_display_text import bitmap_label as _lmod   # fast tile-based rendering
except ImportError:
    from adafruit_display_text import label as _lmod           # fallback
from adafruit_st7789 import ST7789

# =============================================================================
# FONTS
# =============================================================================
from adafruit_bitmap_font import bitmap_font as _bf
FONT_STATUS = _bf.load_font("fonts/bahnschrift_48.pcf")   # large centre label
FONT_PAGE   = terminalio.FONT   # smaller secondary label
FONT_SUB    = _bf.load_font("fonts/bahnschrift_32.pcf")   # smaller secondary label
FONT_SUBGRID = _bf.load_font("fonts/bahnschrift_24.pcf")  # stomp sub-grid
FONT_BIG     = _bf.load_font("fonts/bahnschrift_64.pcf")  # vis_mainlabel_size=4

# Visualization layout tables — indexed by vis_mainlabel_size (0..4).
_VIS_MAIN_FONT    = [None, FONT_SUBGRID, FONT_SUB, FONT_STATUS, FONT_BIG]
_VIS_MAIN_LABEL_Y = [0,    30,           30,       43,          35]
_VIS_SUB_AREA_TOP = [28,   62,           70,       161,         161]


def _compute_vis_layout(ml_size, n_subs):
    """Return (sub_area_top, cell_h, num_rows, sub_font, sub_scale, max_chars)."""
    num_rows = n_subs // 3
    sat = _VIS_SUB_AREA_TOP[ml_size]
    ch = (240 - sat - num_rows) // num_rows
    if   ch >= 42: sf, sc, mc = FONT_SUB, 1, 4
    elif ch >= 28: sf, sc, mc = FONT_SUBGRID, 1, 5
    elif ch >= 16: sf, sc, mc = FONT_PAGE, 2, 6
    else:          sf, sc, mc = FONT_PAGE, 1, 10
    return sat, ch, num_rows, sf, sc, mc


# =============================================================================
# DISPLAY  (ST7789, 240×240, SPI)
# GP8  = backlight PWM
# GP14 = SPI clock, GP15 = SPI MOSI
# GP12 = D/C, GP13 = CS
# rowstart=80 accounts for the physical offset of this specific display module.
# =============================================================================
displayio.release_displays()

backlight = pwmio.PWMOut(board.GP8)
backlight.duty_cycle = 0          # full brightness

spi         = busio.SPI(board.GP14, board.GP15)
display_bus = displayio.FourWire(spi, command=board.GP12, chip_select=board.GP13,
                                  baudrate=62_500_000)
display     = ST7789(display_bus, width=240, height=240, rowstart=80, rotation=180,
                     auto_refresh=False)

splash = displayio.Group()
display.show(splash)          # CircuitPython 7 API (CP8+ uses display.root_group)

# Background layer — always at splash[0], behind all labels.
# Set once at boot from [global] config; never changed on page switches
# because BMP loading is too slow for live transitions.
_bg_bitmap  = displayio.Bitmap(display.width, display.height, 1)
_bg_palette = displayio.Palette(1)
_bg_palette[0] = 0x000000            # default: black until config loaded
_bg_tile = displayio.TileGrid(_bg_bitmap, pixel_shader=_bg_palette)
splash.append(_bg_tile)              # index 0
_bg_file = None                      # open file handle kept alive for OnDiskBitmap

# Main status label — shows page name on boot, then the active key label.
status_label = _lmod.Label(
    FONT_STATUS,
    text="",
    color=0xFFFFFF,
    scale=1,
    line_spacing=0.9,
    anchor_point=(0.5, 0),
    anchored_position=(display.width // 2, 43),
)
splash.append(status_label)          # index 1

# Sub-grid: labeled cells (keys 0-5 physical, optionally 6-11 virtual)
# arranged 3 cols x 2..4 rows below the main status label.
# Each cell has a background tile (color from leds) and a text label.
# All sublabel objects live in _sub_group to avoid bloating splash.
_SUB_CELL_W  = 78
_sub_cell_h  = 38                   # mutable — recalculated on page switch
_SUB_GRID_X  = [40, 120, 200]      # column centres (fixed, 3 columns)

_sub_bar_bitmap = displayio.Bitmap(_SUB_CELL_W, _sub_cell_h, 1)
_sub_bar_palettes = []
_sub_bar_tiles = []
for _si in range(12):
    _sp = displayio.Palette(1)
    _sp[0] = 0x000000
    _sp.make_transparent(0)
    _sub_bar_palettes.append(_sp)

_sub_labels = []
_sub_group = displayio.Group()       # container for active tiles+labels

# Boot with 6 sublabel slots (default layout)
for _si in range(6):
    _st = displayio.TileGrid(_sub_bar_bitmap, pixel_shader=_sub_bar_palettes[_si], x=999, y=999)
    _sub_bar_tiles.append(_st)
    _sub_group.append(_st)
for _si in range(6):
    _sl = _lmod.Label(
        FONT_SUBGRID, text="", color=0xFFFFFF, scale=1,
        anchor_point=(0.5, 0.5), anchored_position=(999, 999),
    )
    _sub_labels.append(_sl)
    _sub_group.append(_sl)

splash.append(_sub_group)            # index 2

# Page name bar — full-width background behind page_label.
# Transparent by default; apply_page sets color from cfg["page_bgcolor"].
_page_bar_bitmap  = displayio.Bitmap(display.width, 28, 1)
_page_bar_palette = displayio.Palette(1)
_page_bar_palette[0] = 0x000000
_page_bar_palette.make_transparent(0)
_page_bar_tile = displayio.TileGrid(_page_bar_bitmap, pixel_shader=_page_bar_palette)
splash.append(_page_bar_tile)        # index 3

# Page name label — small, anchored to the top edge, drawn on top of bar.
page_label = _lmod.Label(
    FONT_PAGE,
    text="",
    color=0xf84848,
    scale=2,
    anchor_point=(0.5, 0.0),
    anchored_position=(display.width // 2, 0),
)
splash.append(page_label)            # index 4



# =============================================================================
# NEOPIXELS
# GP7 = data pin.  18 LEDs total: 3 per switch, ordered SW1..SWC.
# auto_write=False so we batch updates and call pixels.show() ourselves.
# =============================================================================
pixels = neopixel.NeoPixel(board.GP7, 18, brightness=0.3, auto_write=False)
pixels.fill((0, 0, 0))
pixels.show()

# Boot flash: green then red then blue, signals hardware is alive before slow init
pixels.fill((0, 255, 0)); pixels.show(); time.sleep(0.25)
pixels.fill((255, 0, 0)); pixels.show(); time.sleep(0.25)
pixels.fill((0, 0, 255)); pixels.show(); time.sleep(0.25)
pixels.fill((0, 0, 0)); pixels.show()

# =============================================================================
# FOOTSWITCHES
# All 6 switches use internal pull-up resistors.
# Pressed = GPIO reads False (active-low).
# =============================================================================
KEY_PINS  = [board.GP1, board.GP25, board.GP24, board.GP9, board.GP10, board.GP11]
KEY_NAMES = ["SW1", "SW2", "SW3", "SWA", "SWB", "SWC"]   # fallback display names

switches = []
for pin in KEY_PINS:
    sw = digitalio.DigitalInOut(pin)
    sw.direction = digitalio.Direction.INPUT
    sw.pull = digitalio.Pull.UP
    switches.append(sw)

# =============================================================================
# MIDI OUTPUT
# Two simultaneous outputs:
#   USB-MIDI  — via adafruit_midi wrapping usb_midi.ports[1] (the OUT port).
#               Gracefully disabled if the host doesn't enumerate MIDI
#               (e.g. booted in firmware-update mode without a MIDI host).
#   Classic   — raw MIDI bytes written directly to UART on GP16/GP17 at 31250
#               baud.  Bypasses adafruit_midi to avoid buffering quirks with
#               busio.UART in CP 7.3.1.
# =============================================================================
_uart = busio.UART(board.GP16, board.GP17, baudrate=31250)  # DIN-5 MIDI out

try:
    _usb_midi_iface = adafruit_midi.MIDI(midi_out=_usb_midi.ports[1], out_channel=0)
except (IndexError, AttributeError) as e:
    print("USB MIDI unavailable:", e)
    _usb_midi_iface = None

# MIDI INPUT � for ext_capture_cc (virtual key control)
try:
    _usb_midi_in = adafruit_midi.MIDI(midi_in=_usb_midi.ports[0], in_channel=tuple(range(16)))
except (IndexError, AttributeError, ValueError) as e:
    print("USB MIDI IN unavailable:", e)
    _usb_midi_in = None

# Last sent Program Change value per MIDI channel (0-based), used by inc/dec.
_pc_state = {}

# =============================================================================
# ALIASES  — loaded once from ultrasetup/aliases.txt
# Maps alias name → integer, used in exec_commands for CC/PC/NT number slots.
# =============================================================================
_aliases = {}
try:
    with open("ultrasetup/aliases.txt") as _af:
        for _line in _af:
            _line = _line.strip()
            if not _line or _line.startswith(";"):
                continue
            if "=" in _line:
                _ak, _, _av = _line.partition("=")
                _ak = _ak.strip()
                _av = _av.partition(";")[0].strip()   # strip inline comments
                try:
                    _aliases[_ak] = int(_av)
                except ValueError:
                    pass
except OSError:
    pass


def _resolve(s):
    """Resolve a config value token to an integer.
    Checks _aliases first, then falls back to int().
    Returns 0 for empty / '-' tokens.
    """
    if not s or s == "-":
        return 0
    if s in _aliases:
        return _aliases[s]
    return int(s)


_exec_depth = 0
_EXEC_MAX_DEPTH = 8

def exec_commands(cmds):
    """Execute a list of (a, b, c, d) command tuples parsed from config.

    Supported commands:
      [PAGE][n][][]        — switch to page n
      [PAGE][inc][][]      — switch to next page (page_cur + 1)
      [PAGE][dec][][]      — switch to previous page (page_cur - 1)
      [ch][PC][prog][]     — Program Change; prog may be "inc" or "dec"
      [ch][CC][ctrl][val]  — Control Change
      [ch][NT][note][vel]  — Note On
    Null/ignored slots are "" or "-".
    """
    global _exec_depth
    _exec_depth += 1
    if _exec_depth > _EXEC_MAX_DEPTH:
        if DEBUG:
            print("[ERR] exec_commands recursion depth {} exceeded max {}".format(_exec_depth, _EXEC_MAX_DEPTH))
        _exec_depth -= 1
        return
    try:
        _exec_commands_inner(cmds)
    finally:
        _exec_depth -= 1


def _exec_commands_inner(cmds):
    """Inner implementation of exec_commands (called after depth check)."""
    for cmd in cmds:
        try:
            _exec_one_command(cmd)
        except (ValueError, TypeError) as e:
            if DEBUG:
                print("[ERR] bad command {}: {}".format(cmd, e))


def _exec_one_command(cmd):
    """Execute a single (a, b, c, d) command tuple. May raise ValueError."""
    a, b, c, d = cmd

    # ---- Macro (reusable command defined in [page] as cmdN) ----------
    if a == "CMD":
        cmd_id = int(b) if (b and b != "-") else -1
        if DEBUG:
            print("[CMD] {} | macro {}".format(_key_name(_active_key) if _active_key is not None else "?", cmd_id))
        if cmd_id in cfg.get("cmds", {}):
            exec_commands(cfg["cmds"][cmd_id])
        elif cmd_id in cfg.get("global_cmds", {}):
            exec_commands(cfg["global_cmds"][cmd_id])
        return

    # ---- Page switch ------------------------------------------------
    if a == "PAGE":
        if b == "inc":
            page_num = page_cur + 1
        elif b == "dec":
            page_num = page_cur - 1
        else:
            page_num = int(b) if (b and b != "-") else 0
        if DEBUG:
            print("[CMD] {} | PAGE {}".format(_key_name(_active_key) if _active_key is not None else "?", page_num))
        switch_page(page_num)
        return

    # ---- Key simulation ---------------------------------------------
    if a == "KEY":
        key_num = int(b) if (b and b != "-") else -1
        if DEBUG:
            print("[CMD] {} | KEY {} step={} lstep={}".format(_key_name(_active_key) if _active_key is not None else "?", _key_name(key_num), c, d))
        if 0 <= key_num < NUM_TOTAL_KEYS and key_num != _active_key:
            kc_key = cfg["keys"][key_num]
            # Optional cycle step c (1-based in config)
            if c and c != "-":
                target_step = int(c) - 1
                # Set cycle_pos so press_key advances to target_step
                cycle_pos[key_num] = (target_step - 1) % max(1, kc_key["cycle"])
                g = kc_key["group"]
                if g > 0:
                    group_active[g] = key_num
            press_key(key_num)
            release_key(key_num, long_press=False)
            # Optional long cycle step lc (1-based in config)
            if d and d != "-":
                target_lstep = int(d) - 1
                lc_count = kc_key["longcycle"]
                if lc_count > 0:
                    long_cycle_pos[key_num] = (target_lstep - 1) % lc_count
                    lg = kc_key["longgroup"]
                    if lg > 0:
                        long_group_active[lg] = key_num
                    longpress_key(key_num)
        return

    # ---- MIDI -------------------------------------------------------
    ch  = (int(a) - 1) & 0x0F          # config is 1-based; hardware is 0-based
    val = _resolve(d)

    if b == "PC":
        if c == "inc":
            step = int(d) if (d and d != "-") else 1
            num_int = min(127, _pc_state.get(ch, 0) + step)
        elif c == "dec":
            step = int(d) if (d and d != "-") else 1
            num_int = max(0, _pc_state.get(ch, 0) - step)
        else:
            num_int = _resolve(c)
        _pc_state[ch] = num_int
        if DEBUG:
            print("[TX]  {} | PC  ch={} prog={}".format(_key_name(_active_key) if _active_key is not None else "?", ch + 1, num_int))
        if _usb_midi_iface:
            _usb_midi_iface.out_channel = ch
            _usb_midi_iface.send(ProgramChange(num_int))
        _uart.write(bytes([0xC0 | ch, num_int]))

    elif b == "CC":
        num_int = _resolve(c)
        if DEBUG:
            print("[TX]  {} | CC  ch={} cc={} val={}".format(_key_name(_active_key) if _active_key is not None else "?", ch + 1, num_int, val))
        if _usb_midi_iface:
            _usb_midi_iface.out_channel = ch
            _usb_midi_iface.send(ControlChange(num_int, val))
        _uart.write(bytes([0xB0 | ch, num_int, val]))

    elif b == "NT":
        num_int = _resolve(c)
        if DEBUG:
            print("[TX]  {} | NT  ch={} note={} vel={}".format(_key_name(_active_key) if _active_key is not None else "?", ch + 1, num_int, val))
        if _usb_midi_iface:
            _usb_midi_iface.out_channel = ch
            _usb_midi_iface.send(NoteOn(num_int, val))
        _uart.write(bytes([0x90 | ch, num_int, val]))


# =============================================================================
# KEY TIMING  (all times in seconds)
# =============================================================================
DEBOUNCE_SEC    = 0.020   # GPIO must be stable for this long before accepted
LONGPRESS_SEC   = 0.500   # hold longer than this → long press (ldn), not short (dn)
REBOOT_HOLD_SEC = 2.0     # hold the reboot combo for this long → microcontroller.reset()
REBOOT_COMBO    = (0, 2, 3, 5)   # key indices: SW1, SW3, SWA, SWC
RELOAD_HOLD_SEC = 1.0     # hold the reload combo for this long → reload current page
RELOAD_COMBO    = (0, 2)  # key indices: SW1, SW3

DEBUG = True   # serial monitor tracing (incoming MIDI, presses, commands, outgoing MIDI)

def _key_name(idx):
    """Human-readable key name for debug output."""
    if idx < NUM_PHYSICAL_KEYS:
        return KEY_NAMES[idx]
    return "V{}".format(idx)

NUM_PHYSICAL_KEYS = 6     # physical footswitches (0-5)
NUM_TOTAL_KEYS    = 32    # total addressable keys (0-31); 6 physical + 26 virtual

# =============================================================================
# CONFIG PARSER
# =============================================================================

def parse_brackets(s):
    """Extract all [value] tokens from a string into a list of strings."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "[":
            j = s.find("]", i)
            if j < 0:
                if DEBUG:
                    print("[ERR] parse_brackets: missing ']' in: {}".format(s))
                break
            result.append(s[i + 1:j])
            i = j + 1
        else:
            i += 1
    return result


def parse_commands(s):
    """Parse a command string into a list of (a, b, c, d) tuples.

    Commands are separated by spaces.  Each command is a sequence of
    [value] tokens (up to 4); missing trailing slots are padded with ''.
    Example: '[1][PC][36] [1][CC][tx_comp_pwr][0]' -> two tuples.
    """
    cmds = []
    for part in s.split(" "):
        part = part.strip()
        if not part:
            continue
        vals = parse_brackets(part)
        if not vals:
            continue
        while len(vals) < 4:
            vals.append("")
        cmds.append(tuple(vals[:4]))
    return cmds


def parse_led_color(s):
    """Parse a hex color string into (r, g, b).
    Returns None for null tokens ('' or '-'), meaning 'leave LED unchanged'.
    Returns (0,0,0) for '0x000000' (explicit black = LED off).
    """
    s = s.strip()
    if s == "" or s == "-":
        return None
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    v = int(s, 16)
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def parse_color_int(s):
    """Parse a hex color token into an integer (e.g. '0x300000' -> 0x300000).
    Returns 0 (black) for null/empty tokens.
    """
    s = s.strip()
    if s == "" or s == "-":
        return 0
    if s.startswith("0x") or s.startswith("0X"):
        return int(s[2:], 16)
    return int(s, 16)


def load_page(page_num):
    """Load and parse ultrasetup/page{page_num}.txt.

    Returns a cfg dict:
      page_name      str
      page_bg        int   background color (24-bit RGB integer, default 0x000000)
      page_bg_img    str|None  wallpaper filename without extension (e.g. 'wp1'),
                               loaded from wallpaper/<name>.bmp; overrides page_bg
      init_commands  list of (a,b,c,d) tuples — run on page load
      led_brightness int  0-100
      screen_brightness int  0-100
      group_cycle    dict  group_id -> bool (True=pause cycle on group switch)
      keys           list of NUM_TOTAL_KEYS (32) key dicts, each containing:
        group        int   0=no group, else radio-button group id
        longgroup    int   0=no group, else radio-button group id for long presses
        cycle        int   number of short-press cycle steps (1=no cycle)
        longcycle    int   0=share main cycle, >0=independent long-press cycle
        leds         list  per main-cycle-step: [c0,c1,c2]  (c may be None)
        leds_l       list  per long-cycle-step: [c0,c1,c2]
        labels       list  per main-cycle-step: str shown in status_label
        labels_l     list  per long-cycle-step: str shown in sub_label
        labels_d     list  per main-cycle-step: str shown in sub_label on press
        labels_u     list  per main-cycle-step: str shown in sub_label on release
        commands     dict  (step_1based, action) -> list of (a,b,c,d) tuples
                           action is one of: dn up ldn lup
    """
    filename = "ultrasetup/page{}.txt".format(page_num)

    # Default config returned if the file is missing
    cfg = {
        "page_name": "PAGE {}".format(page_num),
        "page_color": 0xF84848,
        "page_bgcolor": None,
        "page_bg": 0x000000,
        "page_bg_img": None,
        "global_cmds": {},
        "cmds": {},
        "init_commands": [],
        "led_brightness": 30,      # percent 0-100
        "screen_brightness": 50,   # percent 0-100
        "group_cycle": {},
        "capture_ch": -1,          # ext_capture_cc channel (0-based); -1 = disabled
        "capture_cc": -1,          # ext_capture_cc CC number; -1 = disabled
        "midi_thru": False,        # forward incoming MIDI to output
        "vis_mainlabel_size": 3,   # 0=hidden, 1=minuscule, 2=tiny, 3=big, 4=bigger
        "vis_sublabels": 6,        # 6 (keys 0-5) or 12 (keys 0-11)
        "keys": [
            {
                "group": 0, "longgroup": 0, "cycle": 1, "longcycle": 0, "stompmode": 0,
                "leds": [], "leds_l": [],
                "labels": [], "labels_l": [],
                "labels_d": [], "labels_u": [],
                "commands": {},
            }
            for _ in range(NUM_TOTAL_KEYS)
        ],
    }

    try:
        os.stat(filename)
    except OSError:
        return cfg

    current_section = None
    with open(filename, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";"):
                continue

            # Section header: [page] or [key0]..[key5]
            if line.startswith("[") and line.endswith("]") and "=" not in line:
                current_section = line[1:-1]
                continue

            if "=" not in line:
                continue

            k, _, v = line.partition("=")
            k    = k.strip()
            v    = v.strip()
            vals = parse_brackets(v)

            # ---- [global] section ----------------------------------------
            if current_section == "global":
                if k == "led_brightness":
                    cfg["led_brightness"] = int(vals[0]) if vals else 30
                elif k == "screen_brightness":
                    cfg["screen_brightness"] = int(vals[0]) if vals else 50
                elif k == "page_bg":
                    cfg["page_bg"] = parse_color_int(vals[0]) if vals else 0
                elif k == "page_bg_img":
                    v0 = vals[0].strip() if vals else ""
                    cfg["page_bg_img"] = v0 if (v0 and v0 != "-") else None
                elif k == "ext_capture_cc":
                    if len(vals) >= 2:
                        cfg["capture_ch"] = int(vals[0]) - 1  # 0-based
                        cfg["capture_cc"] = int(vals[1])
                elif k == "midi_thru":
                    cfg["midi_thru"] = (vals[0] == "1") if vals else False
                elif k.startswith("cmd") and k[3:].isdigit():
                    cmd_id = int(k[3:])
                    cfg["global_cmds"][cmd_id] = parse_commands(v)

            # ---- [page] section -----------------------------------------
            elif current_section == "page":
                if k == "page_name":
                    cfg["page_name"] = vals[0] if vals else ""
                elif k == "init_commands":
                    cfg["init_commands"] = parse_commands(v)
                elif k == "color":
                    cfg["page_color"] = parse_color_int(vals[0]) if vals else 0xF84848
                elif k == "bgcolor":
                    v0 = vals[0].strip() if vals else ""
                    cfg["page_bgcolor"] = parse_color_int(v0) if (v0 and v0 != "-") else None
                elif k.startswith("cmd") and k[3:].isdigit():
                    cmd_id = int(k[3:])
                    cfg["cmds"][cmd_id] = parse_commands(v)
                elif k == "vis_mainlabel_size":
                    cfg["vis_mainlabel_size"] = max(0, min(4, int(vals[0]))) if vals else 3
                elif k == "vis_sublabels":
                    v0 = int(vals[0]) if vals else 6
                    cfg["vis_sublabels"] = 12 if v0 >= 12 else 6
                elif k.startswith("group_cycle"):
                    # group_cycleN = [0|1]
                    gid = int(k[len("group_cycle"):])
                    cfg["group_cycle"][gid] = (vals[0] == "1") if vals else False

            # ---- [keyN] section -----------------------------------------
            elif current_section is not None and current_section.startswith("key"):
                try:
                    idx = int(current_section[3:])
                except ValueError:
                    continue
                if idx < 0 or idx >= NUM_TOTAL_KEYS:
                    continue
                kc = cfg["keys"][idx]

                if k == "group":
                    kc["group"] = int(vals[0]) if vals else 0

                elif k == "longgroup":
                    kc["longgroup"] = int(vals[0]) if vals else 0

                elif k == "cycle":
                    _cv = int(vals[0]) if vals else 1
                    if _cv < 1:
                        if DEBUG:
                            print("[ERR] key{} cycle={} invalid, using 1".format(idx, _cv))
                        _cv = 1
                    kc["cycle"] = _cv

                elif k == "longcycle":
                    kc["longcycle"] = int(vals[0]) if vals else 0

                elif k == "stompmode":
                    kc["stompmode"] = int(vals[0]) if vals else 0

                elif k.startswith("led") and k.endswith("l") and k[3:-1].isdigit():
                    # ledXl  — LED colors for long-press cycle step X
                    colors = [parse_led_color(c) for c in vals]
                    while len(colors) < 3:
                        colors.append(None)
                    kc["leds_l"].append(colors[:3])

                elif k.startswith("led") and k[3:].isdigit():
                    # ledX   — LED colors for main cycle step X
                    colors = [parse_led_color(c) for c in vals]
                    while len(colors) < 3:
                        colors.append(None)
                    kc["leds"].append(colors[:3])

                elif k.startswith("label") and k.endswith("l") and k[5:-1].isdigit():
                    # labelXl — sub_label text for long-press cycle step X
                    kc["labels_l"].append(vals[0] if vals else "")

                elif k.startswith("label") and k[5:].isdigit():
                    # labelX  — status_label text for main cycle step X
                    kc["labels"].append(vals[0] if vals else "")

                elif k.startswith("label") and k.endswith("d") and k[5:-1].isdigit():
                    # labelXd — sub_label text shown on press at main step X
                    kc["labels_d"].append(vals[0] if vals else "")

                elif k.startswith("label") and k.endswith("u") and k[5:-1].isdigit():
                    # labelXu — sub_label text shown on release at main step X
                    kc["labels_u"].append(vals[0] if vals else "")

                elif k.startswith("key") and len(k) > 3:
                    # keyXdn / keyXup / keyXldn / keyXlup
                    # X is the 1-based cycle step; action suffix determines timing.
                    rest = k[3:]
                    for action in ("ldn", "lup", "dn", "up"):
                        if rest.endswith(action):
                            step_str = rest[:-len(action)]
                            if step_str.isdigit():
                                step = int(step_str)
                                kc["commands"][(step, action)] = parse_commands(v)
                            break
    return cfg


# =============================================================================
# LED HELPERS
# =============================================================================

def set_key_leds(key_idx, colors):
    """Write colors to the 3 NeoPixels for key_idx."""
    base = key_idx * 3
    for j in range(3):
        c = colors[j] if j < len(colors) else None
        if c is not None:
            pixels[base + j] = c


def clear_key_leds(key_idx):
    """Turn off all 3 LEDs for key_idx."""
    base = key_idx * 3
    for j in range(3):
        pixels[base + j] = (0, 0, 0)


# =============================================================================
# RUNTIME STATE
# =============================================================================
page_cur       = 0
cfg            = load_page(page_cur)

# Main cycle position per key.  -1 = not yet pressed (so first press → step 0).
cycle_pos      = [-1] * NUM_TOTAL_KEYS

# Independent long-press cycle position per key.  -1 = never long-pressed.
# Only used when kc["longcycle"] > 0; otherwise long press shares main cycle.
long_cycle_pos = [-1] * NUM_TOTAL_KEYS

# group_id -> key_idx of the last pressed key in that group.
group_active   = {}

# longgroup_id -> key_idx of the last long-pressed key in that long group.
long_group_active = {}

# Per-key: True if press_key() was already called on the falling edge for this press.
# False means press_key() is deferred to the rising edge (key has no dn commands).
_dn_advanced = [False] * NUM_TOTAL_KEYS

# Set True by press/longpress handlers; cleared by disp_task each frame.
display_dirty  = False
_page_switched = False   # set by switch_page; suppresses LED+label update in press_key
_active_key    = None    # index of key whose commands are currently executing (loop guard)

# Pending display text — key handlers write here (fast, no rendering cost).
# disp_task picks them up and assigns to label objects (where the actual work happens).
# None means "no change pending".
_pending_status = None
_pending_subs       = [None] * 12
_pending_sub_colors = [None] * 12
_pending_page   = None

# Visualization state — cached from cfg on page switch for fast access.
_vis_sublabels     = 6     # number of active sublabel slots (6 or 12)
_vis_sub_max_chars = 5     # text truncation limit for sublabels
_vis_sub_cell_h    = 38    # current sublabel cell height in pixels


def _first_non_null_color(led_triple):
    """Return the first non-None color tuple from a [c0, c1, c2] LED list."""
    for col in led_triple:
        if col is not None:
            return col
    return None


def apply_page():
    """Reset all key state, LEDs and display for the current page cfg."""
    global group_active, long_group_active, display_dirty, _pending_status, _pending_page
    global _vis_sublabels, _vis_sub_max_chars, _vis_sub_cell_h
    global _sub_bar_bitmap, _sub_cell_h
    global status_label, _sub_labels

    # Apply global brightness settings from config
    pixels.brightness    = max(0.0, min(1.0, cfg["led_brightness"] / 100))
    backlight.duty_cycle = int(max(0, min(100, cfg["screen_brightness"])) / 100 * 65535)

    group_active = {}
    long_group_active = {}
    for i in range(NUM_TOTAL_KEYS):
        cycle_pos[i]      = -1
        long_cycle_pos[i] = -1
    for i in range(NUM_PHYSICAL_KEYS):
        clear_key_leds(i)
    pixels.show()

    # Apply page_label colors and full-width background bar
    page_label.color = cfg["page_color"]
    bg = cfg["page_bgcolor"]
    if bg is not None:
        _page_bar_palette[0] = bg
        _page_bar_palette.make_opaque(0)
    else:
        _page_bar_palette.make_transparent(0)

    # Queue display update
    _pending_page   = cfg["page_name"]

    # --- Visualization layout ---
    ml_size = cfg["vis_mainlabel_size"]
    n_subs  = cfg["vis_sublabels"]
    sat, ch, num_rows, sub_font, sub_scale, mc = _compute_vis_layout(ml_size, n_subs)
    _vis_sublabels     = n_subs
    _vis_sub_max_chars = mc
    if DEBUG:
        print("[VIS] ml_size={} n_subs={} sat={} ch={} mc={}".format(ml_size, n_subs, sat, ch, mc))

    # Main label: recreate with the right font, or hide for size=0
    _pending_status = None
    main_font = _VIS_MAIN_FONT[ml_size]
    if main_font is None:
        status_label = _lmod.Label(FONT_STATUS, text="", color=0xFFFFFF,
                                   scale=1, line_spacing=0.9,
                                   anchor_point=(0.5, 0),
                                   anchored_position=(999, 999))
    else:
        status_label = _lmod.Label(main_font, text="", color=0xFFFFFF,
                                   scale=1, line_spacing=0.9,
                                   anchor_point=(0.5, 0),
                                   anchored_position=(display.width // 2,
                                                      _VIS_MAIN_LABEL_Y[ml_size]))
    splash[1] = status_label

    # Rebuild sublabel bitmap if cell height changed
    if ch != _vis_sub_cell_h:
        _vis_sub_cell_h = ch
        _sub_cell_h     = ch
        _sub_bar_bitmap = displayio.Bitmap(_SUB_CELL_W, ch, 1)

    # Rebuild _sub_group with exactly n_subs tile+label pairs
    while len(_sub_group):
        _sub_group.pop()
    _sub_bar_tiles.clear()
    _sub_labels.clear()
    for i in range(n_subs):
        _nt = displayio.TileGrid(_sub_bar_bitmap, pixel_shader=_sub_bar_palettes[i],
                                 x=999, y=999)
        _sub_bar_tiles.append(_nt)
        _sub_group.append(_nt)
    for i in range(n_subs):
        _nl = _lmod.Label(sub_font, text="", color=0xFFFFFF,
                          scale=sub_scale, line_spacing=0.9,
                          anchor_point=(0.5, 0.5),
                          anchored_position=(999, 999))
        _sub_labels.append(_nl)
        _sub_group.append(_nl)

    # Position active sublabel slots
    for i in range(n_subs):
        if cfg["keys"][i]["stompmode"] > 0:
            col = i % 3
            row = i // 3
            ry  = sat + ch // 2 + row * ch
            _sub_bar_tiles[i].x = col * 80 + (80 - _SUB_CELL_W) // 2
            _sub_bar_tiles[i].y = ry - ch // 2
            _sub_labels[i].anchored_position = (_SUB_GRID_X[col], ry)
        _sub_bar_palettes[i].make_transparent(0)
        _pending_subs[i] = ""

    display_dirty   = True


def press_key(key_idx):
    """Handle a confirmed short press on key_idx.

    Actions (in order):
      1. Group logic — turn off other keys in the same group; maybe reset cycle.
      2. Advance main cycle_pos.
      3. Execute dn MIDI commands (may trigger a page switch via switch_page).
      4. If no page switch occurred: update LEDs and labels.
    """
    global display_dirty, _page_switched, _pending_status, _active_key
    _page_switched = False
    kc           = cfg["keys"][key_idx]
    group        = kc["group"]
    total_cycles = kc["cycle"]
    leds         = kc["leds"]
    labels       = kc["labels"]

    # --- Group (radio-button) logic ---
    if group > 0:
        prev_active       = group_active.get(group, None)
        group_cycle_reset = cfg["group_cycle"].get(group, False)
        for i in range(NUM_TOTAL_KEYS):
            # Clear all other members of this group
            if i != key_idx and cfg["keys"][i]["group"] == group:
                if i < NUM_PHYSICAL_KEYS:
                    clear_key_leds(i)
                cycle_pos[i] = -1
                long_cycle_pos[i] = -1
                if i < _vis_sublabels and cfg["keys"][i]["stompmode"] > 0:
                    _pending_subs[i] = ""
                    _pending_sub_colors[i] = -1
        # If group_cycle is False (0) and a *different* key was last active,
        # reset this key's cycle back to the start.
        if group_cycle_reset and prev_active != key_idx:
            cycle_pos[key_idx] = -1
        group_active[group] = key_idx
        # Virtual key won't reach the pixels.show() below — flush now so
        # cleared physical-key LEDs actually update on the hardware.
        if key_idx >= NUM_PHYSICAL_KEYS:
            pixels.show()

    # --- Advance cycle ---
    cycle_pos[key_idx] = (cycle_pos[key_idx] + 1) % total_cycles
    step = cycle_pos[key_idx]

    # --- MIDI commands (may trigger switch_page which sets _page_switched) ---
    cmd_step = step + 1   # config uses 1-based step numbers
    prev_active = _active_key
    _active_key = key_idx
    exec_commands(kc["commands"].get((cmd_step, "dn"), []))
    _active_key = prev_active

    # --- LEDs and labels — skipped if a page switch just happened ---
    if not _page_switched:
        if key_idx < NUM_PHYSICAL_KEYS:
            set_key_leds(key_idx, leds[step] if step < len(leds) else [])
            pixels.show()

        labels_d = kc["labels_d"]
        if step < len(labels) and labels[step]:
            _pending_status = labels[step]
        elif key_idx < NUM_PHYSICAL_KEYS and not labels_d:
            _pending_status = KEY_NAMES[key_idx]

        sm = kc["stompmode"] if key_idx < _vis_sublabels else 0
        if sm == 1:
            lbl = labels[step] if step < len(labels) else ""
            _pending_subs[key_idx] = lbl
            fc = _first_non_null_color(leds[step] if step < len(leds) else [])
            if fc:
                _pending_sub_colors[key_idx] = (fc[0] << 16) | (fc[1] << 8) | fc[2]
            else:
                _pending_sub_colors[key_idx] = -1
        elif sm == 2 and kc["longcycle"] > 0:
            lstep = long_cycle_pos[key_idx]
            labels_l = kc["labels_l"]
            _pending_subs[key_idx] = labels_l[lstep] if 0 <= lstep < len(labels_l) else ""

        display_dirty = True


def longpress_key(key_idx):
    """Handle a confirmed long press on key_idx.

    Does NOT advance the main cycle.
    If longcycle > 0: advances the independent long-press cycle, applies leds_l
    and updates sub_label with labels_l for the new long-press step.
    If longcycle == 0: uses the current main cycle step for command lookup.
    Fires ldn MIDI commands.
    """
    global display_dirty, _active_key
    kc        = cfg["keys"][key_idx]
    longcycle = kc["longcycle"]
    longgroup = kc["longgroup"]

    if longcycle > 0:
        # Long group (radio-button) logic for long presses
        if longgroup > 0:
            prev_active = long_group_active.get(longgroup, None)
            if prev_active is not None and prev_active != key_idx:
                # Clear previous key's long cycle LEDs (reset to main cycle LEDs)
                if prev_active < NUM_PHYSICAL_KEYS:
                    prev_kc = cfg["keys"][prev_active]
                    prev_step = cycle_pos[prev_active]
                    prev_leds = prev_kc["leds"]
                    if prev_step >= 0 and prev_step < len(prev_leds):
                        set_key_leds(prev_active, prev_leds[prev_step])
                long_cycle_pos[prev_active] = -1
                if prev_active < _vis_sublabels:
                    _pending_subs[prev_active] = ""
                    _pending_sub_colors[prev_active] = -1
            if prev_active != key_idx:
                long_cycle_pos[key_idx] = -1  # reset cycle on group switch
            long_group_active[longgroup] = key_idx
            # Flush LED changes when a virtual key clears a physical key's LEDs
            if key_idx >= NUM_PHYSICAL_KEYS and prev_active is not None and prev_active < NUM_PHYSICAL_KEYS:
                pixels.show()

        # Advance independent long-press cycle
        long_cycle_pos[key_idx] = (long_cycle_pos[key_idx] + 1) % longcycle
        lstep    = long_cycle_pos[key_idx]
        cmd_step = lstep + 1

        leds_l = kc["leds_l"]
        if key_idx < NUM_PHYSICAL_KEYS and lstep < len(leds_l):
            set_key_leds(key_idx, leds_l[lstep])
            pixels.show()

        if key_idx < _vis_sublabels:
            labels_l = kc["labels_l"]
            if lstep < len(labels_l):
                _pending_subs[key_idx] = labels_l[lstep]
            leds_l_list = kc["leds_l"]
            if lstep < len(leds_l_list):
                fc = _first_non_null_color(leds_l_list[lstep])
                if fc:
                    _pending_sub_colors[key_idx] = (fc[0] << 16) | (fc[1] << 8) | fc[2]
                else:
                    _pending_sub_colors[key_idx] = -1
    else:
        # Shared cycle: look up ldn commands using the main cycle step
        # If key was never short-pressed (cycle_pos=-1), use step 1
        cmd_step = max(1, cycle_pos[key_idx] + 1)

    prev_active = _active_key
    _active_key = key_idx
    exec_commands(kc["commands"].get((cmd_step, "ldn"), []))
    _active_key = prev_active
    display_dirty = True


def release_key(key_idx, long_press=False):
    """Handle key release.  Fires lup (after long press) or up (after short press).

    If a page switch occurred during press, skip release commands entirely �
    the physical release belongs to the old page, not the new one.
    """
    if _page_switched:
        return
    kc        = cfg["keys"][key_idx]
    longcycle = kc["longcycle"]

    global _active_key
    prev_active = _active_key
    _active_key = key_idx
    if long_press:
        cmd_step = (long_cycle_pos[key_idx] + 1) if longcycle > 0 else (cycle_pos[key_idx] + 1)
        exec_commands(kc["commands"].get((cmd_step, "lup"), []))
    else:
        cmd_step = cycle_pos[key_idx] + 1
        exec_commands(kc["commands"].get((cmd_step, "up"), []))
    _active_key = prev_active


def switch_page(page_num):
    """Load a new page config, reset state, and run init commands."""
    global cfg, page_cur, _page_switched
    _page_switched = False          # clear stale flag from prior transitions
    page_cur = page_num
    cfg      = load_page(page_num)
    apply_page()
    exec_commands(cfg["init_commands"])
    _page_switched = True


# =============================================================================
# BOOT
# =============================================================================

# Apply background once — loaded from [global], never changed on page switches
# because BMP loading is too slow for live transitions.
_bg_img = cfg.get("page_bg_img")
if _bg_img:
    try:
        _bg_file = open("wallpaper/{}.bmp".format(_bg_img), "rb")
        _bmp = displayio.OnDiskBitmap(_bg_file)
        splash[0] = displayio.TileGrid(_bmp, pixel_shader=_bmp.pixel_shader)
    except OSError:
        _bg_palette[0] = cfg.get("page_bg", 0x000000)
else:
    _bg_palette[0] = cfg.get("page_bg", 0x000000)

apply_page()
exec_commands(cfg["init_commands"])    # run page-level init commands


# =============================================================================
# ASYNC TASKS
# =============================================================================

async def key_check():
    """Poll all 6 switches with per-key debouncing and long-press detection.

    State machine per key:
      raw[]         — last raw GPIO reading (True = released, False = pressed)
      debounced[]   — stable debounced reading (promoted after DEBOUNCE_SEC)
      debounce_ts[] — timestamp of the last raw-state change
      press_ts[]    — timestamp when the key was debounce-confirmed pressed
      is_long[]     — whether the current hold has already crossed LONGPRESS_SEC

    Short press: action fires on RELEASE (not on press-down), only if the key
    was released before crossing LONGPRESS_SEC.

    Long press: fires as soon as LONGPRESS_SEC is crossed while the GPIO is
    physically still held (raw=False).  The `not raw[i]` guard prevents the
    long press from firing spuriously during the release-debounce window.

    Reboot combo: if REBOOT_COMBO keys are all held for REBOOT_HOLD_SEC,
    calls microcontroller.reset() for a clean soft reboot.
    """
    raw         = [True]  * 6
    debounced   = [True]  * 6
    debounce_ts = [0.0]   * 6
    press_ts    = [0.0]   * 6
    is_long     = [False] * 6
    combo_start  = None
    reload_start = None

    while True:
        now = time.monotonic()

        for i, sw in enumerate(switches):
            r = sw.value   # True = released (pull-up), False = pressed

            # Raw edge detected → restart debounce timer
            if r != raw[i]:
                raw[i]        = r
                debounce_ts[i] = now

            # Debounce: promote raw to debounced once it has been stable
            if raw[i] != debounced[i] and (now - debounce_ts[i]) >= DEBOUNCE_SEC:
                debounced[i] = raw[i]
                if not debounced[i]:
                    # Falling edge (press confirmed): start hold timer.
                    # Fire press_key immediately only if dn commands are defined
                    # for the next cycle step; otherwise defer to release so that
                    # the cycle advance and label update happen together with up.
                    press_ts[i] = now
                    is_long[i]  = False
                    kc_i = cfg["keys"][i]
                    next_step = (cycle_pos[i] + 1) % kc_i["cycle"]
                    if kc_i["commands"].get((next_step + 1, "dn")):
                        if DEBUG:
                            print("[KEY] {} | dn  | step={}".format(KEY_NAMES[i], next_step + 1))
                        press_key(i)
                        _dn_advanced[i] = True
                    else:
                        _dn_advanced[i] = False
                else:
                    # Rising edge (release confirmed)
                    if is_long[i]:
                        if DEBUG:
                            print("[KEY] {} | lup".format(KEY_NAMES[i]))
                        release_key(i, long_press=True)    # lup
                    else:
                        if not _dn_advanced[i]:
                            _next = (cycle_pos[i] + 1) % max(1, cfg["keys"][i]["cycle"])
                            if DEBUG:
                                print("[KEY] {} | dn  | step={} (deferred)".format(KEY_NAMES[i], _next + 1))
                            press_key(i)                   # deferred: advance cycle now
                        if DEBUG:
                            print("[KEY] {} | up".format(KEY_NAMES[i]))
                        release_key(i, long_press=False)   # up

            # Long press: GPIO physically still held and threshold crossed.
            # Does NOT advance the main cycle — only ldn/lup fire for a long press.
            elif not raw[i] and not debounced[i] and not is_long[i]:
                if (now - press_ts[i]) >= LONGPRESS_SEC:
                    is_long[i] = True
                    if DEBUG:
                        print("[KEY] {} | ldn".format(KEY_NAMES[i]))
                    longpress_key(i)                       # ldn

        # Reload combo: hold key 0 + key 2 for RELOAD_HOLD_SEC → reload current page
        if all(not debounced[i] for i in RELOAD_COMBO):
            if reload_start is None:
                reload_start = now
            elif now - reload_start >= RELOAD_HOLD_SEC:
                reload_start = None
                switch_page(page_cur)
                _page_switched = False   # not called from press_key, so clear it
        else:
            reload_start = None

        # Reboot combo detection
        if all(not debounced[i] for i in REBOOT_COMBO):
            if combo_start is None:
                combo_start = now
            elif now - combo_start >= REBOOT_HOLD_SEC:
                microcontroller.reset()
        else:
            combo_start = None

        await asyncio.sleep(0)   # yield to other tasks


async def disp_task():
    """Display refresh task.

    Key handlers write to _pending_* string variables (zero cost — no rendering).
    This task picks them up and assigns to label objects, which is where the
    actual glyph rendering work happens.  Keeping it here means key_check is
    never stalled by text rendering; it only yields into this task between
    its own loop iterations.

    auto_refresh=False: we call display.refresh() explicitly after applying
    pending changes, so the ST7789 only pushes a frame when something changed.
    """
    global display_dirty, _pending_status, _pending_page
    while True:
        if display_dirty:
            display_dirty = False
            if _pending_page is not None:
                page_label.text = _pending_page
                _pending_page   = None
            if _pending_status is not None:
                status_label.text = _pending_status.replace(":", "\n")
                _pending_status   = None
            for _si in range(_vis_sublabels):
                if _pending_subs[_si] is not None:
                    _sub_labels[_si].text = _pending_subs[_si][:_vis_sub_max_chars]
                    _pending_subs[_si] = None
                if _pending_sub_colors[_si] is not None:
                    if _pending_sub_colors[_si] == -1:
                        _sub_bar_palettes[_si].make_transparent(0)
                    else:
                        _c = _pending_sub_colors[_si]
                        _sub_bar_palettes[_si][0] = _c
                        _sub_bar_palettes[_si].make_opaque(0)
                        _r = (_c >> 16) & 0xFF; _g = (_c >> 8) & 0xFF; _b = _c & 0xFF
                        _sub_labels[_si].color = 0x000000 if (_r * 299 + _g * 587 + _b * 114) > 128000 else 0xFFFFFF
                    _pending_sub_colors[_si] = None
            display.refresh()
        await asyncio.sleep(0)


def _process_capture_cc(channel, control, value):
    """Process a CC message against the ext_capture_cc config.

    Returns True if the message matched and was handled.
    """
    global display_dirty
    cap_ch = cfg.get("capture_ch", -1)
    cap_cc = cfg.get("capture_cc", -1)

    if cap_ch < 0 or cap_cc < 0:
        return False
    if channel != cap_ch or control != cap_cc:
        return False

    key_idx = value & 0x1F          # lower 5 bits = key number
    action  = (value >> 5) & 0x03   # upper 2 bits = action type

    if DEBUG:
        _actions = {0: "dn", 1: "ldn", 2: "up", 3: "lup"}
        print("[RX]  CAP | {} {}".format(_key_name(key_idx), _actions.get(action, "?")))

    if key_idx >= NUM_TOTAL_KEYS:
        return False

    if action == 0:        # 0x00-0x1F: press (dn)
        press_key(key_idx)
    elif action == 1:      # 0x20-0x3F: long press (ldn)
        longpress_key(key_idx)
    elif action == 2:      # 0x40-0x5F: key up (up)
        release_key(key_idx, long_press=False)
    elif action == 3:      # 0x60-0x7F: long press up (lup)
        release_key(key_idx, long_press=True)

    display_dirty = True
    return True


# UART MIDI parser state (running-status aware)
_uart_midi_status = 0    # last status byte
_uart_midi_buf = []      # data bytes collected so far


def _uart_parse_byte(b):
    """Feed one byte from UART into the MIDI parser.

    Returns (status, data1, data2) for complete channel-voice messages,
    or None.  Handles running status.  System messages and SysEx are ignored.
    """
    global _uart_midi_status, _uart_midi_buf

    if b >= 0xF8:
        return

    if b >= 0xF0:
        _uart_midi_status = 0
        _uart_midi_buf = []
        return

    if b & 0x80:
        _uart_midi_status = b
        _uart_midi_buf = []
        return

    # Data byte
    if _uart_midi_status == 0:
        return  # no status yet

    _uart_midi_buf.append(b)
    msg_type = _uart_midi_status & 0xF0

    if msg_type in (0xC0, 0xD0):
        result = (_uart_midi_status, _uart_midi_buf[0], 0)
        _uart_midi_buf = []
        return result
    elif len(_uart_midi_buf) >= 2:
        result = (_uart_midi_status, _uart_midi_buf[0], _uart_midi_buf[1])
        _uart_midi_buf = []
        return result


async def midi_in_task():
    """Poll MIDI input (USB + DIN-5 UART) for ext_capture_cc virtual key events.

    CC value encoding (from CAPTURE.md):
      0x00-0x1F (0-31)   = press key (dn)
      0x20-0x3F (32-63)  = long press (ldn)
      0x40-0x5F (64-95)  = key up (up)
      0x60-0x7F (96-127) = long press up (lup)
    """
    while True:
        got_msg = False

        # --- USB-MIDI input ---
        if _usb_midi_in is not None:
            msg = _usb_midi_in.receive()
            if msg is not None:
                got_msg = True
                if DEBUG:
                    if isinstance(msg, ControlChange):
                        print("[RX]  USB | CC  ch={} cc={} val={}".format(msg.channel + 1, msg.control, msg.value))
                    elif isinstance(msg, ProgramChange):
                        print("[RX]  USB | PC  ch={} prog={}".format(msg.channel + 1, msg.patch))
                    elif isinstance(msg, NoteOn):
                        print("[RX]  USB | NT  ch={} note={} vel={}".format(msg.channel + 1, msg.note, msg.velocity))
                    else:
                        print("[RX]  USB | {}".format(type(msg).__name__))
                if cfg.get("midi_thru"):
                    if _usb_midi_iface:
                        _usb_midi_iface.send(msg)
                if isinstance(msg, ControlChange):
                    _process_capture_cc(msg.channel, msg.control, msg.value)

        # --- DIN-5 UART MIDI input ---
        uart_avail = _uart.in_waiting
        if uart_avail:
            got_msg = True
            raw = _uart.read(uart_avail)
            if raw:
                for b in raw:
                    parsed = _uart_parse_byte(b)
                    if parsed is not None:
                        status, d1, d2 = parsed
                        msg_type = status & 0xF0
                        channel  = status & 0x0F
                        if DEBUG:
                            if msg_type == 0xB0:
                                print("[RX]  DIN | CC  ch={} cc={} val={}".format(channel + 1, d1, d2))
                            elif msg_type == 0xC0:
                                print("[RX]  DIN | PC  ch={} prog={}".format(channel + 1, d1))
                            elif msg_type == 0x90:
                                print("[RX]  DIN | NT  ch={} note={} vel={}".format(channel + 1, d1, d2))
                        # MIDI thru: forward DIN-5 input to USB output
                        if cfg.get("midi_thru") and _usb_midi_iface:
                            if msg_type == 0xB0:
                                _usb_midi_iface.send(ControlChange(d1, d2, channel=channel))
                            elif msg_type == 0xC0:
                                _usb_midi_iface.send(ProgramChange(d1, channel=channel))
                            elif msg_type == 0x90:
                                _usb_midi_iface.send(NoteOn(d1, d2, channel=channel))
                        # Process capture CC
                        if msg_type == 0xB0:
                            _process_capture_cc(channel, d1, d2)

        if not got_msg:
            await asyncio.sleep(0)


async def main():
    """Launch all tasks concurrently via asyncio cooperative multitasking."""
    await asyncio.gather(
        asyncio.create_task(key_check()),
        asyncio.create_task(disp_task()),
        asyncio.create_task(midi_in_task()),
    )


asyncio.run(main())
