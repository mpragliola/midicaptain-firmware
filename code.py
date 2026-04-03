# =============================================================================
# UltraMidi firmware — main entry point
# written by mpragliola <marcopragliola@gmail.com>
#
# Runs on a MidiCaptain Mini 6 (RP2040 / CircuitPython 7.3.1).
# Reads config from ultrasetup/<name>.txt, manages 6 footswitches,
# 18 NeoPixel LEDs (3 per switch), a 240×240 ST7789 display and dual MIDI out
# (USB-MIDI + classic DIN-5 via UART).
# =============================================================================

import gc
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
    from adafruit_display_text import bitmap_label as _lmod
except ImportError:
    from adafruit_display_text import label as _lmod
from adafruit_st7789 import ST7789

import state as S
from config import list_configs
from pages import Page
from display import Display
from engine import (exec_commands, apply_page, switch_page,
                    enter_explorer, explorer_key,
                    explorer_press,
                    press_key, longpress_key, release_key,
                    process_capture_cc)

# =============================================================================
# FONTS
# =============================================================================
from adafruit_bitmap_font import bitmap_font as _bf
_font_status  = _bf.load_font("fonts/bahnschrift_48.pcf")
_font_page    = terminalio.FONT
_font_sub     = _bf.load_font("fonts/bahnschrift_32.pcf")
_font_subgrid = _bf.load_font("fonts/bahnschrift_24.pcf")
_font_big     = _bf.load_font("fonts/bahnschrift_64.pcf")

# =============================================================================
# DISPLAY  (ST7789, 240×240, SPI)
# =============================================================================
displayio.release_displays()

_backlight = pwmio.PWMOut(board.GP8)
_backlight.duty_cycle = 0

spi         = busio.SPI(board.GP14, board.GP15)
display_bus = displayio.FourWire(spi, command=board.GP12, chip_select=board.GP13,
                                  baudrate=62_500_000)
_hw_display = ST7789(display_bus, width=240, height=240, rowstart=80, rotation=180,
                     auto_refresh=False)

gc.collect()
S.disp = Display(
    _hw_display,
    _backlight,
    _lmod,
    {
        "status":  _font_status,
        "page":    _font_page,
        "sub":     _font_sub,
        "subgrid": _font_subgrid,
        "big":     _font_big,
    }
)
gc.collect()

# =============================================================================
# NEOPIXELS
# =============================================================================
S.pixels = neopixel.NeoPixel(board.GP7, 18, brightness=0.3, auto_write=False)
S.pixels.fill((0, 0, 0))
S.pixels.show()

# Boot flash
S.pixels.fill((0, 255, 0)); S.pixels.show(); time.sleep(0.25)
S.pixels.fill((255, 0, 0)); S.pixels.show(); time.sleep(0.25)
S.pixels.fill((0, 0, 255)); S.pixels.show(); time.sleep(0.25)
S.pixels.fill((0, 0, 0)); S.pixels.show()

# =============================================================================
# FOOTSWITCHES
# =============================================================================
KEY_PINS = [board.GP1, board.GP25, board.GP24, board.GP9, board.GP10, board.GP11]

switches = []
for pin in KEY_PINS:
    sw = digitalio.DigitalInOut(pin)
    sw.direction = digitalio.Direction.INPUT
    sw.pull = digitalio.Pull.UP
    switches.append(sw)

# =============================================================================
# MIDI OUTPUT
# =============================================================================
S._uart = busio.UART(board.GP16, board.GP17, baudrate=31250)

try:
    S._usb_midi_iface = adafruit_midi.MIDI(midi_out=_usb_midi.ports[1], out_channel=0)
except (IndexError, AttributeError) as e:
    print("USB MIDI unavailable:", e)
    S._usb_midi_iface = None

# MIDI INPUT
try:
    _usb_midi_in = adafruit_midi.MIDI(midi_in=_usb_midi.ports[0], in_channel=tuple(range(16)))
except (IndexError, AttributeError, ValueError) as e:
    print("USB MIDI IN unavailable:", e)
    _usb_midi_in = None


# =============================================================================
# BOOT
# =============================================================================
# --- Config discovery ---
# Scan ultrasetup/ for config .txt files (e.g. init.txt, live_rig.txt).
# Prefer "init" if it exists, otherwise pick the first alphabetically.
_startup_cfgs = list_configs()
if "init" in _startup_cfgs:
    S.cfg_name = "init"
elif _startup_cfgs:
    S.cfg_name = _startup_cfgs[0]
S.current_page = Page(S.page_cur)

# Apply background once — loaded from [global] section, never changed on page switches
_bg_file = None
_bg_img  = S.current_page.background_image
if _bg_img:
    try:
        _bg_file = open("wallpaper/{}.bmp".format(_bg_img), "rb")
        _bmp = displayio.OnDiskBitmap(_bg_file)
        S.disp.set_background_image(_bmp, _bg_file)
    except OSError:
        S.disp.set_background_color(S.current_page.background_int)
else:
    S.disp.set_background_color(S.current_page.background_int)

apply_page()
exec_commands(S.current_page.init_commands)


# =============================================================================
# ASYNC TASKS
# =============================================================================

async def key_check():
    """Poll all 6 switches with per-key debouncing and long-press detection."""
    raw         = [True]  * 6
    debounced   = [True]  * 6
    debounce_ts = [0.0]   * 6
    press_ts    = [0.0]   * 6
    is_long     = [False] * 6
    combo_start      = None
    reload_start     = None
    explorer_start   = None     # timestamp when SW3+SWA both became held (or None)
    _combo23_suppressed = False  # when True, suppress SW3/SWA release events
                                 # to prevent cancel/down from firing right after
                                 # the explorer combo activates

    while True:
        now = time.monotonic()

        for i, sw in enumerate(switches):
            r = sw.value

            if r != raw[i]:
                raw[i]         = r
                debounce_ts[i] = now

            if raw[i] != debounced[i] and (now - debounce_ts[i]) >= S.DEBOUNCE_SEC:
                debounced[i] = raw[i]
                if not debounced[i]:
                    # Falling edge (press confirmed)
                    press_ts[i] = now
                    is_long[i]  = False
                    S._dn_advanced[i] = False
                    if S.explorer_mode:
                        # In explorer: brighten LED on press (visual feedback)
                        explorer_press(i)
                    else:
                        kc_i = S.current_page.keys[i]
                        next_step = (S.current_page.get_cycle_pos(i) + 1) % kc_i["cycle"]
                        if kc_i["commands"].get((next_step + 1, "dn")):
                            if S.DEBUG:
                                print("[KEY] {} | dn  | step={}".format(S.KEY_NAMES[i], next_step + 1))
                            press_key(i)
                            S._dn_advanced[i] = True
                else:
                    # Rising edge (release confirmed)
                    if S.explorer_mode:
                        # In explorer mode, dispatch release to explorer_key().
                        # Suppress keys 2+3 if they were part of the combo that
                        # just entered explorer — otherwise releasing them would
                        # immediately trigger cancel (2) or cursor-down (3).
                        _suppress = _combo23_suppressed and i in (2, 3)
                        if not _suppress:
                            explorer_key(i)
                    else:
                        if is_long[i]:
                            if S.DEBUG:
                                print("[KEY] {} | lup".format(S.KEY_NAMES[i]))
                            release_key(i, long_press=True)
                        else:
                            if not S._dn_advanced[i]:
                                _next = (S.current_page.get_cycle_pos(i) + 1) % max(1, S.current_page.keys[i]["cycle"])
                                if S.DEBUG:
                                    print("[KEY] {} | dn  | step={} (deferred)".format(S.KEY_NAMES[i], _next + 1))
                                press_key(i)
                            if S.DEBUG:
                                print("[KEY] {} | up".format(S.KEY_NAMES[i]))
                            release_key(i, long_press=False)

            elif not raw[i] and not debounced[i] and not is_long[i]:
                if (now - press_ts[i]) >= S.LONGPRESS_SEC:
                    is_long[i] = True
                    # Skip long-press handler in explorer mode — keys are
                    # navigation-only, no MIDI commands should fire.
                    if not S.explorer_mode:
                        if S.DEBUG:
                            print("[KEY] {} | ldn".format(S.KEY_NAMES[i]))
                        longpress_key(i)

        # --- Combo suppression cleanup ---
        # Once both SW3 and SWA are fully released after the explorer combo
        # fired, clear the suppression flag so future presses work normally.
        if _combo23_suppressed and debounced[2] and debounced[3]:
            _combo23_suppressed = False

        # --- Explorer combo: SW3 + SWA (indices 2+3) held simultaneously ---
        # Fires after LONGPRESS_SEC (0.5s).  This is shorter than the reload
        # combo (1s) and reboot combo (2s), both of which are gated out while
        # explorer_mode is True, so there's no conflict.
        if not debounced[2] and not debounced[3] and not S.explorer_mode:
            if explorer_start is None:
                explorer_start = now
            elif now - explorer_start >= S.LONGPRESS_SEC:
                explorer_start      = None
                _combo23_suppressed = True   # suppress upcoming key 2+3 releases
                is_long[2] = True   # prevent normal longpress from also firing
                is_long[3] = True
                enter_explorer()
        else:
            # Reset timer if either key is released before threshold
            if debounced[2] or debounced[3]:
                explorer_start = None

        # --- Reload and reboot combos (disabled during explorer mode) ---
        if not S.explorer_mode:
            # Reload combo
            if all(not debounced[i] for i in S.RELOAD_COMBO):
                if reload_start is None:
                    reload_start = now
                elif now - reload_start >= S.RELOAD_HOLD_SEC:
                    reload_start = None
                    switch_page(S.page_cur)
                    S._page_switched = False
            else:
                reload_start = None

            # Reboot combo
            if all(not debounced[i] for i in S.REBOOT_COMBO):
                if combo_start is None:
                    combo_start = now
                elif now - combo_start >= S.REBOOT_HOLD_SEC:
                    microcontroller.reset()
            else:
                combo_start = None

        # --- Deferred page switch (runs at shallow stack depth) ---
        if S._pending_page_switch is not None:
            _pps_n = 0
            while S._pending_page_switch is not None and _pps_n < 4:
                _pps = S._pending_page_switch
                S._pending_page_switch = None
                switch_page(_pps)
                _pps_n += 1

        await asyncio.sleep(0)


async def disp_task():
    """Display refresh task — applies pending text/color changes."""
    while True:
        if S.disp._dirty:
            S.disp.flush()
        await asyncio.sleep(0)


# UART MIDI parser state (running-status aware)
_uart_midi_status = 0
_uart_midi_buf = []


def _uart_parse_byte(b):
    """Feed one byte from UART into the MIDI parser.
    Returns (status, data1, data2) for complete messages, or None.
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

    if _uart_midi_status == 0:
        return

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
    """Poll MIDI input (USB + DIN-5 UART) for ext_capture_cc virtual key events."""
    _MIDI_YIELD_EVERY = 4
    while True:
        msg_count = 0

        # --- USB-MIDI input ---
        if _usb_midi_in is not None:
            msg = _usb_midi_in.receive()
            if msg is not None:
                msg_count += 1
                if S.DEBUG:
                    if isinstance(msg, ControlChange):
                        print("[RX]  USB | CC  ch={} cc={} val={}".format(msg.channel + 1, msg.control, msg.value))
                    elif isinstance(msg, ProgramChange):
                        print("[RX]  USB | PC  ch={} prog={}".format(msg.channel + 1, msg.patch))
                    elif isinstance(msg, NoteOn):
                        print("[RX]  USB | NT  ch={} note={} vel={}".format(msg.channel + 1, msg.note, msg.velocity))
                    else:
                        print("[RX]  USB | {}".format(type(msg).__name__))
                # MIDI thru: forward USB input to DIN-5 output only
                if S.current_page.midi_thru:
                    if isinstance(msg, ControlChange):
                        S._uart.write(bytes([0xB0 | msg.channel, msg.control, msg.value]))
                    elif isinstance(msg, ProgramChange):
                        S._uart.write(bytes([0xC0 | msg.channel, msg.patch]))
                    elif isinstance(msg, NoteOn):
                        S._uart.write(bytes([0x90 | msg.channel, msg.note, msg.velocity]))
                if isinstance(msg, ControlChange):
                    process_capture_cc(msg.channel, msg.control, msg.value)

        # --- DIN-5 UART MIDI input ---
        uart_avail = S._uart.in_waiting
        if uart_avail:
            raw = S._uart.read(uart_avail)
            if raw:
                for b in raw:
                    parsed = _uart_parse_byte(b)
                    if parsed is not None:
                        msg_count += 1
                        status, d1, d2 = parsed
                        msg_type = status & 0xF0
                        channel  = status & 0x0F
                        if S.DEBUG:
                            if msg_type == 0xB0:
                                print("[RX]  DIN | CC  ch={} cc={} val={}".format(channel + 1, d1, d2))
                            elif msg_type == 0xC0:
                                print("[RX]  DIN | PC  ch={} prog={}".format(channel + 1, d1))
                            elif msg_type == 0x90:
                                print("[RX]  DIN | NT  ch={} note={} vel={}".format(channel + 1, d1, d2))
                        # MIDI thru: forward DIN-5 input to USB output
                        if S.current_page.midi_thru and S._usb_midi_iface:
                            if msg_type == 0xB0:
                                S._usb_midi_iface.send(ControlChange(d1, d2, channel=channel))
                            elif msg_type == 0xC0:
                                S._usb_midi_iface.send(ProgramChange(d1, channel=channel))
                            elif msg_type == 0x90:
                                S._usb_midi_iface.send(NoteOn(d1, d2, channel=channel))
                        # Process capture CC
                        if msg_type == 0xB0:
                            process_capture_cc(channel, d1, d2)

        if msg_count >= _MIDI_YIELD_EVERY or msg_count == 0:
            await asyncio.sleep(0)


async def main():
    """Launch all tasks concurrently via asyncio cooperative multitasking."""
    await asyncio.gather(
        asyncio.create_task(key_check()),
        asyncio.create_task(disp_task()),
        asyncio.create_task(midi_in_task()),
    )


asyncio.run(main())
