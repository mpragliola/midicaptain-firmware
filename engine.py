# engine.py — command execution, key handling, page switching

from adafruit_midi.program_change import ProgramChange
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_on import NoteOn
import state as S
from config import _resolve
from pages import Page


# =============================================================================
# HELPERS
# =============================================================================

def _dbg_key():
    """Active key name for debug output."""
    return S._key_name(S._active_key) if S._active_key is not None else "?"


def _color_int(rgb):
    """Pack (r, g, b) tuple into 24-bit integer."""
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def _send_midi(status_byte, ch, data):
    """Send a MIDI message on both USB and UART."""
    if S._usb_midi_iface:
        S._usb_midi_iface.out_channel = ch
        if status_byte == 0xC0:
            S._usb_midi_iface.send(ProgramChange(data[0]))
        elif status_byte == 0xB0:
            S._usb_midi_iface.send(ControlChange(data[0], data[1]))
        elif status_byte == 0x90:
            S._usb_midi_iface.send(NoteOn(data[0], data[1]))
    S._uart.write(bytes([status_byte | ch] + data))


def _run_as_key(key_idx, cmds):
    """Run cmds with _active_key set to key_idx, then restore."""
    prev = S._active_key
    S._active_key = key_idx
    exec_commands(cmds)
    S._active_key = prev


def _update_sub_color(key_idx, led_triple):
    """Set pending sublabel background color from an LED color triple."""
    fc = S._first_non_null_color(led_triple)
    S.disp.set_sub_color(key_idx, _color_int(fc) if fc else -1)


def set_key_leds(key_idx, colors):
    """Write colors to the 3 NeoPixels for key_idx."""
    base = key_idx * 3
    for j in range(3):
        c = colors[j] if j < len(colors) else None
        if c is not None:
            S.pixels[base + j] = c


def clear_key_leds(key_idx):
    """Turn off all 3 LEDs for key_idx."""
    base = key_idx * 3
    for j in range(3):
        S.pixels[base + j] = (0, 0, 0)


# =============================================================================
# COMMAND EXECUTION
# =============================================================================

def exec_commands(cmds):
    """Execute a list of (a, b, c, d) command tuples parsed from config."""
    for cmd in cmds:
        if cmd[0] == "CMD":
            _b = cmd[1]
            cmd_id = int(_b) if (_b and _b != "-") else -1
            if S.DEBUG:
                print("[CMD] {} | macro {}".format(_dbg_key(), cmd_id))
            macro = S.current_page.cmds.get(cmd_id)
            if macro is None:
                macro = S.current_page.global_cmds.get(cmd_id)
            if macro:
                for mcmd in macro:
                    try:
                        _exec_one_command(mcmd)
                    except (ValueError, TypeError) as e:
                        if S.DEBUG:
                            print("[ERR] bad command {}: {}".format(mcmd, e))
            continue
        try:
            _exec_one_command(cmd)
        except (ValueError, TypeError) as e:
            if S.DEBUG:
                print("[ERR] bad command {}: {}".format(cmd, e))


def _exec_one_command(cmd):
    """Execute a single (a, b, c, d) command tuple. May raise ValueError."""
    a, b, c, d = cmd

    # ---- Page switch ------------------------------------------------
    if a == "PAGE":
        if b == "inc":
            page_num = S.page_cur + 1
        elif b == "dec":
            page_num = S.page_cur - 1
        else:
            page_num = int(b) if (b and b != "-") else 0
        if S.DEBUG:
            print("[CMD] {} | PAGE {} (deferred)".format(_dbg_key(), page_num))
        S._pending_page_switch = page_num
        S._page_switched = True
        return

    # ---- Key simulation ---------------------------------------------
    if a == "KEY":
        key_num = int(b) if (b and b != "-") else -1
        if S.DEBUG:
            print("[CMD] {} | KEY {} step={} lstep={}".format(_dbg_key(), S._key_name(key_num), c, d))
        if 0 <= key_num < S.NUM_TOTAL_KEYS and key_num != S._active_key:
            page = S.current_page
            kc_key = page.keys[key_num]
            if c and c != "-":
                target_step = int(c) - 1
                page.set_cycle_pos(key_num, (target_step - 1) % max(1, kc_key["cycle"]))
                g = kc_key["group"]
                if g > 0:
                    page.set_group_active(g, key_num)
            press_key(key_num)
            release_key(key_num, long_press=False)
            if d and d != "-":
                target_lstep = int(d) - 1
                lc_count = kc_key["longcycle"]
                if lc_count > 0:
                    page.set_long_cycle_pos(key_num, (target_lstep - 1) % lc_count)
                    lg = kc_key["longgroup"]
                    if lg > 0:
                        page.set_group_active_long(lg, key_num)
                    longpress_key(key_num)
        return

    # ---- MIDI -------------------------------------------------------
    ch  = (int(a) - 1) & 0x0F
    val = _resolve(d)

    if b == "PC":
        if c == "inc":
            step = int(d) if (d and d != "-") else 1
            num_int = min(127, S._pc_state.get(ch, 0) + step)
        elif c == "dec":
            step = int(d) if (d and d != "-") else 1
            num_int = max(0, S._pc_state.get(ch, 0) - step)
        else:
            num_int = _resolve(c)
        S._pc_state[ch] = num_int
        if S.DEBUG:
            print("[TX]  {} | PC  ch={} prog={}".format(_dbg_key(), ch + 1, num_int))
        _send_midi(0xC0, ch, [num_int])

    elif b == "CC":
        num_int = _resolve(c)
        if S.DEBUG:
            print("[TX]  {} | CC  ch={} cc={} val={}".format(_dbg_key(), ch + 1, num_int, val))
        _send_midi(0xB0, ch, [num_int, val])

    elif b == "NT":
        num_int = _resolve(c)
        if S.DEBUG:
            print("[TX]  {} | NT  ch={} note={} vel={}".format(_dbg_key(), ch + 1, num_int, val))
        _send_midi(0x90, ch, [num_int, val])


# =============================================================================
# PAGE MANAGEMENT
# =============================================================================

def apply_page():
    """Reset all key state, LEDs and display for the current page cfg."""
    page = S.current_page

    # Hardware brightness
    S.pixels.brightness = max(0.0, min(1.0, page.led_brightness / 100))
    S.disp.set_brightness(page.screen_brightness)

    page.reset()
    for i in range(S.NUM_PHYSICAL_KEYS):
        clear_key_leds(i)
    S.pixels.show()

    # All display work delegated to Display
    S.disp.apply_vis(page)


def switch_page(page_num):
    """Load a new page config, reset state, and run init commands."""
    S._page_switched = False
    S.page_cur = page_num
    S.current_page = Page(page_num)
    apply_page()
    if S.current_page.errors:
        if S.DEBUG:
            print("[ERR] P{} errors: {}".format(page_num, ", ".join(S.current_page.errors)))
        S.disp.show_errors(S.current_page.errors, page_num)
    else:
        exec_commands(S.current_page.init_commands)
    S._page_switched = True


# =============================================================================
# KEY HANDLERS
# =============================================================================

def press_key(key_idx):
    """Handle a confirmed short press on key_idx."""
    S._page_switched = False
    page         = S.current_page
    kc           = page.keys[key_idx]
    group        = kc["group"]
    leds         = kc["leds"]
    labels       = kc["labels"]

    # --- Group (radio-button) logic ---
    if group > 0:
        prev_active       = page.get_group_active(group)
        group_cycle_reset = page.group_cycle.get(group, False)
        for i in range(S.NUM_TOTAL_KEYS):
            if i != key_idx and page.keys[i]["group"] == group:
                if i < S.NUM_PHYSICAL_KEYS:
                    clear_key_leds(i)
                page.set_cycle_pos(i, -1)
                page.set_long_cycle_pos(i, -1)
                if i < S.disp._vis_sublabels and page.keys[i]["stompmode"] > 0:
                    S.disp.set_sub(i, "")
                    S.disp.set_sub_color(i, -1)
        if group_cycle_reset and prev_active != key_idx:
            page.set_cycle_pos(key_idx, -1)
        page.set_group_active(group, key_idx)
        if key_idx >= S.NUM_PHYSICAL_KEYS:
            S.pixels.show()

    # --- Advance cycle ---
    step = page.advance_cycle(key_idx)

    # --- MIDI commands (may trigger switch_page which sets _page_switched) ---
    cmd_step = step + 1
    _run_as_key(key_idx, kc["commands"].get((cmd_step, "dn"), []))

    # --- LEDs and labels — skipped if a page switch just happened ---
    if not S._page_switched:
        if key_idx < S.NUM_PHYSICAL_KEYS:
            set_key_leds(key_idx, leds[step] if step < len(leds) else [])
            S.pixels.show()

        labels_d = kc["labels_d"]
        if step < len(labels) and labels[step]:
            S.disp.set_status(labels[step])
        elif key_idx < S.NUM_PHYSICAL_KEYS and not labels_d:
            S.disp.set_status(S.KEY_NAMES[key_idx])

        sm = kc["stompmode"] if key_idx < S.disp._vis_sublabels else 0
        if sm == 1:
            lbl = labels[step] if step < len(labels) else ""
            S.disp.set_sub(key_idx, lbl)
            _update_sub_color(key_idx, leds[step] if step < len(leds) else [])
        elif sm == 2 and kc["longcycle"] > 0:
            lstep = page.get_long_cycle_pos(key_idx)
            labels_l = kc["labels_l"]
            S.disp.set_sub(key_idx, labels_l[lstep] if 0 <= lstep < len(labels_l) else "")

        S.disp.mark_dirty()


def longpress_key(key_idx):
    """Handle a confirmed long press on key_idx."""
    page      = S.current_page
    kc        = page.keys[key_idx]
    longcycle = kc["longcycle"]
    longgroup = kc["longgroup"]

    if longcycle > 0:
        # Long group (radio-button) logic for long presses
        if longgroup > 0:
            prev_active = page.get_group_active_long(longgroup)
            if prev_active is not None and prev_active != key_idx:
                if prev_active < S.NUM_PHYSICAL_KEYS:
                    prev_kc = page.keys[prev_active]
                    prev_step = page.get_cycle_pos(prev_active)
                    prev_leds = prev_kc["leds"]
                    if prev_step >= 0 and prev_step < len(prev_leds):
                        set_key_leds(prev_active, prev_leds[prev_step])
                page.set_long_cycle_pos(prev_active, -1)
                if prev_active < S.disp._vis_sublabels:
                    S.disp.set_sub(prev_active, "")
                    S.disp.set_sub_color(prev_active, -1)
            if prev_active != key_idx:
                page.set_long_cycle_pos(key_idx, -1)
            page.set_group_active_long(longgroup, key_idx)
            if key_idx >= S.NUM_PHYSICAL_KEYS and prev_active is not None and prev_active < S.NUM_PHYSICAL_KEYS:
                S.pixels.show()

        # Advance independent long-press cycle
        lstep = page.advance_long_cycle(key_idx)
        cmd_step = lstep + 1

        leds_l = kc["leds_l"]
        if key_idx < S.NUM_PHYSICAL_KEYS and lstep < len(leds_l):
            set_key_leds(key_idx, leds_l[lstep])
            S.pixels.show()

        if key_idx < S.disp._vis_sublabels:
            labels_l = kc["labels_l"]
            if lstep < len(labels_l):
                S.disp.set_sub(key_idx, labels_l[lstep])
            if lstep < len(leds_l):
                _update_sub_color(key_idx, leds_l[lstep])
    else:
        cmd_step = max(1, page.get_cycle_pos(key_idx) + 1)

    _run_as_key(key_idx, kc["commands"].get((cmd_step, "ldn"), []))
    S.disp.mark_dirty()


def release_key(key_idx, long_press=False):
    """Handle key release. Fires lup (after long press) or up (after short press)."""
    if S._page_switched:
        return
    page      = S.current_page
    kc        = page.keys[key_idx]
    longcycle = kc["longcycle"]

    if long_press:
        cmd_step = (page.get_long_cycle_pos(key_idx) + 1) if longcycle > 0 else (page.get_cycle_pos(key_idx) + 1)
        _run_as_key(key_idx, kc["commands"].get((cmd_step, "lup"), []))
    else:
        cmd_step = page.get_cycle_pos(key_idx) + 1
        _run_as_key(key_idx, kc["commands"].get((cmd_step, "up"), []))


# =============================================================================
# MIDI INPUT PROCESSING
# =============================================================================

def process_capture_cc(channel, control, value):
    """Process a CC message against the ext_capture_cc config.
    Returns True if the message matched and was handled.
    """
    cap_ch = S.current_page.capture_channel
    cap_cc = S.current_page.capture_cc

    if cap_ch < 0 or cap_cc < 0:
        return False
    if channel != cap_ch or control != cap_cc:
        return False

    key_idx = value & 0x1F
    action  = (value >> 5) & 0x03

    if S.DEBUG:
        _actions = {0: "dn", 1: "ldn", 2: "up", 3: "lup"}
        print("[RX]  CAP | {} {}".format(S._key_name(key_idx), _actions.get(action, "?")))

    if key_idx >= S.NUM_TOTAL_KEYS:
        return False

    if action == 0:
        press_key(key_idx)
    elif action == 1:
        longpress_key(key_idx)
    elif action == 2:
        release_key(key_idx, long_press=False)
    elif action == 3:
        release_key(key_idx, long_press=True)

    S.disp.mark_dirty()
    return True


# =============================================================================
# MULTI-CONFIG SUPPORT
#
# Configurations are .txt files under ultrasetup/ (e.g. init.txt, live_rig.txt).
# At boot the firmware picks "init" (or first alphabetically) and loads page 0.
# At runtime, Explorer Mode lets the user browse and switch configs without a
# computer.
#
# Explorer Mode UI and navigation live in explorer.py.
# =============================================================================

def switch_config(name):
    """Load a named config and enter performance mode.

    Called from Explorer.on_key(5) on confirm.  Sequence:
    1. Set cfg_name and reset page counter to 0
    2. Parse the new config file's first [page] section
    3. Clear explorer LEDs and restore the performance display group
    4. Apply the page layout (LEDs, labels, sublabels)
    5. Run the page's init_commands (same as boot)
    """
    S.cfg_name = name
    S.page_cur = 0
    S.current_page = Page(0)
    S.pixels.fill((0, 0, 0))
    S.pixels.show()
    S.disp.restore()
    apply_page()
    exec_commands(S.current_page.init_commands)
    S._page_switched = True


# Explorer Mode — implemented in explorer.py; S.explorer set at import time.
# Thin wrappers here preserve the names that code.py imports from engine.
def enter_explorer():      S.explorer.enter()
def exit_explorer():       S.explorer.exit()
def explorer_press(i):     S.explorer.on_press(i)
def explorer_key(i):       S.explorer.on_key(i)
