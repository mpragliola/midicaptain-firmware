# engine.py — command execution, key handling, page switching

import displayio
from adafruit_midi.program_change import ProgramChange
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_on import NoteOn
import state as S
from config import load_page, _resolve


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
    S._pending_sub_colors[key_idx] = _color_int(fc) if fc else -1


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
        try:
            _exec_one_command(cmd)
        except (ValueError, TypeError) as e:
            if S.DEBUG:
                print("[ERR] bad command {}: {}".format(cmd, e))


def _exec_one_command(cmd):
    """Execute a single (a, b, c, d) command tuple. May raise ValueError."""
    a, b, c, d = cmd

    # ---- Macro (reusable command defined in [page] as cmdN) ----------
    if a == "CMD":
        cmd_id = int(b) if (b and b != "-") else -1
        if S.DEBUG:
            print("[CMD] {} | macro {}".format(_dbg_key(), cmd_id))
        if cmd_id in S.cfg.get("cmds", {}):
            exec_commands(S.cfg["cmds"][cmd_id])
        elif cmd_id in S.cfg.get("global_cmds", {}):
            exec_commands(S.cfg["global_cmds"][cmd_id])
        return

    # ---- Page switch ------------------------------------------------
    if a == "PAGE":
        if b == "inc":
            page_num = S.page_cur + 1
        elif b == "dec":
            page_num = S.page_cur - 1
        else:
            page_num = int(b) if (b and b != "-") else 0
        if S.DEBUG:
            print("[CMD] {} | PAGE {}".format(_dbg_key(), page_num))
        switch_page(page_num)
        return

    # ---- Key simulation ---------------------------------------------
    if a == "KEY":
        key_num = int(b) if (b and b != "-") else -1
        if S.DEBUG:
            print("[CMD] {} | KEY {} step={} lstep={}".format(_dbg_key(), S._key_name(key_num), c, d))
        if 0 <= key_num < S.NUM_TOTAL_KEYS and key_num != S._active_key:
            kc_key = S.cfg["keys"][key_num]
            if c and c != "-":
                target_step = int(c) - 1
                S.cycle_pos[key_num] = (target_step - 1) % max(1, kc_key["cycle"])
                g = kc_key["group"]
                if g > 0:
                    S.group_active[g] = key_num
            press_key(key_num)
            release_key(key_num, long_press=False)
            if d and d != "-":
                target_lstep = int(d) - 1
                lc_count = kc_key["longcycle"]
                if lc_count > 0:
                    S.long_cycle_pos[key_num] = (target_lstep - 1) % lc_count
                    lg = kc_key["longgroup"]
                    if lg > 0:
                        S.long_group_active[lg] = key_num
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
    # Apply global brightness settings from config
    S.pixels.brightness    = max(0.0, min(1.0, S.cfg["led_brightness"] / 100))
    S.backlight.duty_cycle = int(max(0, min(100, S.cfg["screen_brightness"])) / 100 * 65535)

    S.group_active = {}
    S.long_group_active = {}
    for i in range(S.NUM_TOTAL_KEYS):
        S.cycle_pos[i]      = -1
        S.long_cycle_pos[i] = -1
    for i in range(S.NUM_PHYSICAL_KEYS):
        clear_key_leds(i)
    S.pixels.show()

    # Apply page_label colors and full-width background bar
    S.page_label.color = S.cfg["page_color"]
    bg = S.cfg["page_bgcolor"]
    if bg is not None:
        S._page_bar_palette[0] = bg
        S._page_bar_palette.make_opaque(0)
    else:
        S._page_bar_palette.make_transparent(0)

    # Queue display update
    S._pending_page = S.cfg["page_name"]

    # --- Visualization layout ---
    ml_size = S.cfg["vis_mainlabel_size"]
    n_subs  = S.cfg["vis_sublabels"]
    sat, ch, num_rows, sub_font, sub_scale, mc = S._compute_vis_layout(ml_size, n_subs)
    S._vis_sublabels     = n_subs
    S._vis_sub_max_chars = mc
    if S.DEBUG:
        print("[VIS] ml_size={} n_subs={} sat={} ch={} mc={}".format(ml_size, n_subs, sat, ch, mc))

    # Main label: recreate with the right font, or hide for size=0
    S._pending_status = None
    main_font = S._VIS_MAIN_FONT[ml_size]
    if main_font is None:
        S.status_label = S._lmod.Label(S.FONT_STATUS, text="", color=0xFFFFFF,
                                       scale=1, line_spacing=0.9,
                                       anchor_point=(0.5, 0),
                                       anchored_position=(999, 999))
    else:
        S.status_label = S._lmod.Label(main_font, text="", color=0xFFFFFF,
                                       scale=1, line_spacing=0.9,
                                       anchor_point=(0.5, 0),
                                       anchored_position=(S.display.width // 2,
                                                          S._VIS_MAIN_LABEL_Y[ml_size]))
    S.splash[1] = S.status_label

    # Rebuild sublabel bitmap if cell height changed
    if ch != S._vis_sub_cell_h:
        S._vis_sub_cell_h = ch
        S._sub_cell_h     = ch
        S._sub_bar_bitmap = displayio.Bitmap(S._SUB_CELL_W, ch, 1)

    # Rebuild _sub_group with exactly n_subs tile+label pairs
    while len(S._sub_group):
        S._sub_group.pop()
    S._sub_bar_tiles.clear()
    S._sub_labels.clear()
    for i in range(n_subs):
        _nt = displayio.TileGrid(S._sub_bar_bitmap, pixel_shader=S._sub_bar_palettes[i],
                                 x=999, y=999)
        S._sub_bar_tiles.append(_nt)
        S._sub_group.append(_nt)
    for i in range(n_subs):
        _nl = S._lmod.Label(sub_font, text="", color=0xFFFFFF,
                            scale=sub_scale, line_spacing=0.9,
                            anchor_point=(0.5, 0.5),
                            anchored_position=(999, 999))
        S._sub_labels.append(_nl)
        S._sub_group.append(_nl)

    # Position active sublabel slots
    for i in range(n_subs):
        if S.cfg["keys"][i]["stompmode"] > 0:
            col = i % 3
            row = i // 3
            ry  = sat + ch // 2 + row * ch
            S._sub_bar_tiles[i].x = col * 80 + (80 - S._SUB_CELL_W) // 2
            S._sub_bar_tiles[i].y = ry - ch // 2
            S._sub_labels[i].anchored_position = (S._SUB_GRID_X[col], ry)
        S._sub_bar_palettes[i].make_transparent(0)
        S._pending_subs[i] = ""

    S.display_dirty = True


def _show_page_errors(errs, page_num):
    """Override display to show page validation errors after apply_page()."""
    # Red page bar, white text
    S._page_bar_palette[0] = 0xCC2200
    S._page_bar_palette.make_opaque(0)
    S.page_label.color = 0xFFFFFF
    S._pending_page = "p{}:ERR".format(page_num)

    # First error in the main status label (colon -> newline via disp_task)
    # If vis_mainlabel_size=0 the label is hidden; reposition it to size-3 slot
    if S.cfg["vis_mainlabel_size"] == 0:
        S.status_label.anchored_position = (
            S.display.width // 2,
            S._VIS_MAIN_LABEL_Y[3],
        )
    S._pending_status = errs[0]

    # Show up to 6 errors in sub-cells, force-positioned regardless of stompmode
    sat = S._VIS_SUB_AREA_TOP[S.cfg["vis_mainlabel_size"]]
    ch  = S._sub_cell_h
    n   = min(6, len(errs), len(S._sub_labels))
    for i in range(n):
        col = i % 3
        row = i // 3
        ry  = sat + ch // 2 + row * ch
        S._sub_bar_tiles[i].x = col * 80 + (80 - S._SUB_CELL_W) // 2
        S._sub_bar_tiles[i].y = ry - ch // 2
        S._sub_labels[i].anchored_position = (S._SUB_GRID_X[col], ry)
        S._sub_bar_palettes[i][0] = 0xCC2200
        S._sub_bar_palettes[i].make_opaque(0)
        S._pending_subs[i] = errs[i]

    S.display_dirty = True


def switch_page(page_num):
    """Load a new page config, reset state, and run init commands."""
    S._page_switched = False
    S.page_cur = page_num
    S.cfg      = load_page(page_num)
    apply_page()
    if S.cfg["page_errors"]:
        _show_page_errors(S.cfg["page_errors"], page_num)
    else:
        exec_commands(S.cfg["init_commands"])
    S._page_switched = True


# =============================================================================
# KEY HANDLERS
# =============================================================================

def press_key(key_idx):
    """Handle a confirmed short press on key_idx."""
    S._page_switched = False
    kc           = S.cfg["keys"][key_idx]
    group        = kc["group"]
    total_cycles = kc["cycle"]
    leds         = kc["leds"]
    labels       = kc["labels"]

    # --- Group (radio-button) logic ---
    if group > 0:
        prev_active       = S.group_active.get(group, None)
        group_cycle_reset = S.cfg["group_cycle"].get(group, False)
        for i in range(S.NUM_TOTAL_KEYS):
            if i != key_idx and S.cfg["keys"][i]["group"] == group:
                if i < S.NUM_PHYSICAL_KEYS:
                    clear_key_leds(i)
                S.cycle_pos[i] = -1
                S.long_cycle_pos[i] = -1
                if i < S._vis_sublabels and S.cfg["keys"][i]["stompmode"] > 0:
                    S._pending_subs[i] = ""
                    S._pending_sub_colors[i] = -1
        if group_cycle_reset and prev_active != key_idx:
            S.cycle_pos[key_idx] = -1
        S.group_active[group] = key_idx
        if key_idx >= S.NUM_PHYSICAL_KEYS:
            S.pixels.show()

    # --- Advance cycle ---
    S.cycle_pos[key_idx] = (S.cycle_pos[key_idx] + 1) % total_cycles
    step = S.cycle_pos[key_idx]

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
            S._pending_status = labels[step]
        elif key_idx < S.NUM_PHYSICAL_KEYS and not labels_d:
            S._pending_status = S.KEY_NAMES[key_idx]

        sm = kc["stompmode"] if key_idx < S._vis_sublabels else 0
        if sm == 1:
            lbl = labels[step] if step < len(labels) else ""
            S._pending_subs[key_idx] = lbl
            _update_sub_color(key_idx, leds[step] if step < len(leds) else [])
        elif sm == 2 and kc["longcycle"] > 0:
            lstep = S.long_cycle_pos[key_idx]
            labels_l = kc["labels_l"]
            S._pending_subs[key_idx] = labels_l[lstep] if 0 <= lstep < len(labels_l) else ""

        S.display_dirty = True


def longpress_key(key_idx):
    """Handle a confirmed long press on key_idx."""
    kc        = S.cfg["keys"][key_idx]
    longcycle = kc["longcycle"]
    longgroup = kc["longgroup"]

    if longcycle > 0:
        # Long group (radio-button) logic for long presses
        if longgroup > 0:
            prev_active = S.long_group_active.get(longgroup, None)
            if prev_active is not None and prev_active != key_idx:
                if prev_active < S.NUM_PHYSICAL_KEYS:
                    prev_kc = S.cfg["keys"][prev_active]
                    prev_step = S.cycle_pos[prev_active]
                    prev_leds = prev_kc["leds"]
                    if prev_step >= 0 and prev_step < len(prev_leds):
                        set_key_leds(prev_active, prev_leds[prev_step])
                S.long_cycle_pos[prev_active] = -1
                if prev_active < S._vis_sublabels:
                    S._pending_subs[prev_active] = ""
                    S._pending_sub_colors[prev_active] = -1
            if prev_active != key_idx:
                S.long_cycle_pos[key_idx] = -1
            S.long_group_active[longgroup] = key_idx
            if key_idx >= S.NUM_PHYSICAL_KEYS and prev_active is not None and prev_active < S.NUM_PHYSICAL_KEYS:
                S.pixels.show()

        # Advance independent long-press cycle
        S.long_cycle_pos[key_idx] = (S.long_cycle_pos[key_idx] + 1) % longcycle
        lstep    = S.long_cycle_pos[key_idx]
        cmd_step = lstep + 1

        leds_l = kc["leds_l"]
        if key_idx < S.NUM_PHYSICAL_KEYS and lstep < len(leds_l):
            set_key_leds(key_idx, leds_l[lstep])
            S.pixels.show()

        if key_idx < S._vis_sublabels:
            labels_l = kc["labels_l"]
            if lstep < len(labels_l):
                S._pending_subs[key_idx] = labels_l[lstep]
            if lstep < len(leds_l):
                _update_sub_color(key_idx, leds_l[lstep])
    else:
        cmd_step = max(1, S.cycle_pos[key_idx] + 1)

    _run_as_key(key_idx, kc["commands"].get((cmd_step, "ldn"), []))
    S.display_dirty = True


def release_key(key_idx, long_press=False):
    """Handle key release. Fires lup (after long press) or up (after short press)."""
    if S._page_switched:
        return
    kc        = S.cfg["keys"][key_idx]
    longcycle = kc["longcycle"]

    if long_press:
        cmd_step = (S.long_cycle_pos[key_idx] + 1) if longcycle > 0 else (S.cycle_pos[key_idx] + 1)
        _run_as_key(key_idx, kc["commands"].get((cmd_step, "lup"), []))
    else:
        cmd_step = S.cycle_pos[key_idx] + 1
        _run_as_key(key_idx, kc["commands"].get((cmd_step, "up"), []))


# =============================================================================
# MIDI INPUT PROCESSING
# =============================================================================

def process_capture_cc(channel, control, value):
    """Process a CC message against the ext_capture_cc config.
    Returns True if the message matched and was handled.
    """
    cap_ch = S.cfg.get("capture_ch", -1)
    cap_cc = S.cfg.get("capture_cc", -1)

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

    S.display_dirty = True
    return True
