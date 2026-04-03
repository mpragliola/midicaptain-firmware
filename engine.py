# engine.py — command execution, key handling, page switching

import displayio
from adafruit_midi.program_change import ProgramChange
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_on import NoteOn
import state as S
import terminalio
from config import list_configs, _resolve
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
            kc_key = page.get_key(key_num)
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
    # Apply global brightness settings from config
    S.pixels.brightness    = max(0.0, min(1.0, S.current_page.led_brightness / 100))
    S.backlight.duty_cycle = int(max(0, min(100, S.current_page.screen_brightness)) / 100 * 65535)

    S.current_page.reset()
    for i in range(S.NUM_PHYSICAL_KEYS):
        clear_key_leds(i)
    S.pixels.show()

    # Apply page_label colors and full-width background bar
    S.page_label.color = S.current_page.color
    bg = S.current_page.bgcolor
    if bg is not None:
        S._page_bar_palette[0] = bg
        S._page_bar_palette.make_opaque(0)
    else:
        S._page_bar_palette.make_transparent(0)

    # Queue display update
    S._pending_page = S.current_page.name

    # --- Visualization layout ---
    ml_size = S.current_page.vis_mainlabel_size
    n_subs  = S.current_page.vis_sublabels
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
        if S.current_page.keys[i]["stompmode"] > 0:
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
    """Override display to show page validation errors in plain terminal font."""
    # Red page bar, white text
    S._page_bar_palette[0] = 0xCC2200
    S._page_bar_palette.make_opaque(0)
    S.page_label.color = 0xFFFFFF
    S._pending_page = "P{}:ERR".format(page_num)

    # Hide sublabels — errors don't use the performance grid
    for i in range(len(S._sub_bar_palettes)):
        S._sub_bar_palettes[i].make_transparent(0)
    for i in range(len(S._sub_labels)):
        S._sub_labels[i].text = ""

    # Show all errors as plain terminal-font text below the page bar
    txt = "\n".join(errs[:8])
    S.status_label = S._lmod.Label(
        terminalio.FONT, text=txt, color=0xFFFFFF,
        scale=2, line_spacing=1.2,
        anchor_point=(0.5, 0),
        anchored_position=(S.display.width // 2, 30),
    )
    S.splash[1] = S.status_label

    S.display_dirty = True


def switch_page(page_num):
    """Load a new page config, reset state, and run init commands."""
    S._page_switched = False
    S.page_cur = page_num
    S.current_page = Page(page_num)
    apply_page()
    if S.current_page.errors:
        _show_page_errors(S.current_page.errors, page_num)
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
    kc           = page.get_key(key_idx)
    group        = kc["group"]
    leds         = kc["leds"]
    labels       = kc["labels"]

    # --- Group (radio-button) logic ---
    if group > 0:
        prev_active       = page.get_group_active(group)
        group_cycle_reset = page.group_cycle.get(group, False)
        for i in range(S.NUM_TOTAL_KEYS):
            if i != key_idx and page.get_key(i)["group"] == group:
                if i < S.NUM_PHYSICAL_KEYS:
                    clear_key_leds(i)
                page.set_cycle_pos(i, -1)
                page.set_long_cycle_pos(i, -1)
                if i < S._vis_sublabels and page.get_key(i)["stompmode"] > 0:
                    S._pending_subs[i] = ""
                    S._pending_sub_colors[i] = -1
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
            S._pending_status = labels[step]
        elif key_idx < S.NUM_PHYSICAL_KEYS and not labels_d:
            S._pending_status = S.KEY_NAMES[key_idx]

        sm = kc["stompmode"] if key_idx < S._vis_sublabels else 0
        if sm == 1:
            lbl = labels[step] if step < len(labels) else ""
            S._pending_subs[key_idx] = lbl
            _update_sub_color(key_idx, leds[step] if step < len(leds) else [])
        elif sm == 2 and kc["longcycle"] > 0:
            lstep = page.get_long_cycle_pos(key_idx)
            labels_l = kc["labels_l"]
            S._pending_subs[key_idx] = labels_l[lstep] if 0 <= lstep < len(labels_l) else ""

        S.display_dirty = True


def longpress_key(key_idx):
    """Handle a confirmed long press on key_idx."""
    page      = S.current_page
    kc        = page.get_key(key_idx)
    longcycle = kc["longcycle"]
    longgroup = kc["longgroup"]

    if longcycle > 0:
        # Long group (radio-button) logic for long presses
        if longgroup > 0:
            prev_active = page.get_group_active_long(longgroup)
            if prev_active is not None and prev_active != key_idx:
                if prev_active < S.NUM_PHYSICAL_KEYS:
                    prev_kc = page.get_key(prev_active)
                    prev_step = page.get_cycle_pos(prev_active)
                    prev_leds = prev_kc["leds"]
                    if prev_step >= 0 and prev_step < len(prev_leds):
                        set_key_leds(prev_active, prev_leds[prev_step])
                page.set_long_cycle_pos(prev_active, -1)
                if prev_active < S._vis_sublabels:
                    S._pending_subs[prev_active] = ""
                    S._pending_sub_colors[prev_active] = -1
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

        if key_idx < S._vis_sublabels:
            labels_l = kc["labels_l"]
            if lstep < len(labels_l):
                S._pending_subs[key_idx] = labels_l[lstep]
            if lstep < len(leds_l):
                _update_sub_color(key_idx, leds_l[lstep])
    else:
        cmd_step = max(1, page.get_cycle_pos(key_idx) + 1)

    _run_as_key(key_idx, kc["commands"].get((cmd_step, "ldn"), []))
    S.display_dirty = True


def release_key(key_idx, long_press=False):
    """Handle key release. Fires lup (after long press) or up (after short press)."""
    if S._page_switched:
        return
    page      = S.current_page
    kc        = page.get_key(key_idx)
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

    S.display_dirty = True
    return True


# =============================================================================
# MULTI-CONFIG SUPPORT
#
# Configurations are .txt files under ultrasetup/ (e.g. init.txt, live_rig.txt).
# At boot the firmware picks "init" (or first alphabetically) and loads page 0.
# At runtime, Explorer Mode lets the user browse and switch configs without a
# computer.
#
# Display isolation: Explorer Mode creates its own displayio.Group and swaps it
# in via S.display.show(grp).  The performance display (S.splash) is untouched
# while explorer is active.  On exit or confirm, S.display.show(S.splash)
# restores performance mode.
#
# LED feedback: each key gets a role-colored LED (purple=nav, cyan=page,
# red=cancel, green=confirm).  LEDs are dim at idle and brighten on press.
# =============================================================================

def switch_config(name):
    """Load a named config and enter performance mode.

    Called from explorer_key(5) on confirm.  Sequence:
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
    S.display.show(S.splash)       # restore performance display group
    apply_page()
    exec_commands(S.current_page.init_commands)
    S._page_switched = True


def _explorer_render():
    """Re-draw the explorer list from current cursor/scroll state.

    Updates the 6 visible item labels and the scroll indicators.
    Color coding: yellow = cursor + active config, white = cursor only,
    green = active config, grey = other.  Items are prefixed with "> "
    for the cursor or "  " otherwise, capped at 14 chars.
    """
    configs = S._explorer_configs
    scroll  = S._explorer_scroll
    cursor  = S._explorer_cursor
    n       = len(configs)

    # Scroll indicators: show "^"/"v" when more items exist above/below
    S._explorer_up_lbl.text = "^" if scroll > 0 else " "
    S._explorer_dn_lbl.text = "v" if scroll + 6 < n else " "

    # Fill the 6 visible slots from the scroll window
    for slot in range(6):
        idx = scroll + slot
        lbl = S._explorer_item_lbls[slot]
        if idx < n:
            name = configs[idx]
            is_cursor = (idx == cursor)
            is_active = (name == S.cfg_name)
            prefix = "> " if is_cursor else "  "
            lbl.text = (prefix + name)[:14]
            if is_cursor and is_active:
                lbl.color = 0xFFFF00    # yellow: cursor on active config
            elif is_cursor:
                lbl.color = 0xFFFFFF    # white: cursor position
            elif is_active:
                lbl.color = 0x00CC00    # green: currently loaded config
            else:
                lbl.color = 0x666666    # grey: other configs
        else:
            lbl.text = ""


# Explorer LED colors — base palette
_EXPLORER_LEDS_BASE = (
    (128, 0, 128),  # key 0: purple  (cursor up)
    (0, 128, 128),  # key 1: cyan    (page up)
    (255, 0, 0),    # key 2: red     (cancel)
    (128, 0, 128),  # key 3: purple  (cursor down)
    (0, 128, 128),  # key 4: cyan    (page down)
    (0, 255, 0),    # key 5: green   (confirm)
)
# Full intensity (shown while key is held) — halved from base
_EXPLORER_LEDS_FULL = tuple(
    tuple(v // 2 for v in c) for c in _EXPLORER_LEDS_BASE
)
# Dim version (shown at idle) — quartered from base
_EXPLORER_LEDS_DIM = tuple(
    tuple(v // 4 for v in c) for c in _EXPLORER_LEDS_BASE
)


def explorer_press(key_idx):
    """Set full-brightness LED for a key pressed during explorer mode.

    Called on falling edge (press confirmed) in key_check().
    The corresponding explorer_key() call on release will restore dim.
    """
    c = _EXPLORER_LEDS_FULL[key_idx]
    for led in range(3):
        S.pixels[key_idx * 3 + led] = c
    S.pixels.show()


def enter_explorer():
    """Activate Explorer Mode: build the config-browser UI and show it.

    Called when SW3+SWA are held for LONGPRESS_SEC.  Creates a separate
    displayio.Group with:
      - Title label: "SELECT CONFIG" (24pt, centered, y=4)
      - Scroll-up indicator: "^" or " " (terminal font 2x, y=36)
      - 6 item labels: config names (24pt, left-aligned, y=56..196)
      - Scroll-down indicator: "v" or " " (terminal font 2x, y=222)

    The cursor starts on the currently active config.  All 6 physical
    LEDs are set to their role color at dim intensity.  The explorer
    group replaces S.splash via S.display.show().
    """
    configs = list_configs()

    # Place cursor on the currently active config
    cursor = 0
    for i in range(len(configs)):
        if configs[i] == S.cfg_name:
            cursor = i
            break
    # Scroll window: page of 6 that contains the cursor
    scroll = (cursor // 6) * 6

    # --- Build the explorer display group (plain Labels, no tiles) ---
    grp = displayio.Group()

    title = S._lmod.Label(S.FONT_SUBGRID, text="SELECT CONFIG",
                          color=0xFFFFFF, anchor_point=(0.5, 0.0),
                          anchored_position=(120, 4))
    grp.append(title)

    up_lbl = S._lmod.Label(terminalio.FONT, text=" ", color=0x888888, scale=2,
                           anchor_point=(0.5, 0.0), anchored_position=(120, 36))
    grp.append(up_lbl)

    item_lbls = []
    for slot in range(6):
        lbl = S._lmod.Label(S.FONT_SUBGRID, text="", color=0x666666,
                            anchor_point=(0.0, 0.0),
                            anchored_position=(4, 56 + slot * 28))
        grp.append(lbl)
        item_lbls.append(lbl)

    dn_lbl = S._lmod.Label(terminalio.FONT, text=" ", color=0x888888, scale=2,
                           anchor_point=(0.5, 0.0), anchored_position=(120, 222))
    grp.append(dn_lbl)

    # Store references on state for access by _explorer_render / explorer_key
    S._explorer_grp       = grp
    S._explorer_up_lbl    = up_lbl
    S._explorer_dn_lbl    = dn_lbl
    S._explorer_item_lbls = item_lbls
    S._explorer_configs   = configs
    S._explorer_cursor    = cursor
    S._explorer_scroll    = scroll
    S.explorer_mode       = True

    # Set all LEDs to dim role colors (brighten on press via explorer_press)
    for k in range(6):
        for led in range(3):
            S.pixels[k * 3 + led] = _EXPLORER_LEDS_DIM[k]
    S.pixels.show()

    # Swap display to explorer group, render the list, push to screen
    S.display.show(grp)
    _explorer_render()
    S.display.refresh()


def exit_explorer():
    """Leave Explorer Mode without changing config (cancel).

    Clears all explorer state, resets LEDs to black, restores S.splash
    as the active display group, and re-applies the current page layout
    (LEDs, labels, init_commands) so performance mode is fully restored.
    """
    S.explorer_mode       = False
    S._explorer_grp       = None
    S._explorer_up_lbl    = None
    S._explorer_dn_lbl    = None
    S._explorer_item_lbls = None
    S._explorer_configs   = None
    S.pixels.fill((0, 0, 0))
    S.pixels.show()
    S.display.show(S.splash)
    apply_page()
    exec_commands(S.current_page.init_commands)


def explorer_key(key_idx):
    """Handle a key release while in Explorer Mode.

    Key mapping:
      0 = cursor up       3 = cursor down
      1 = page up (6)     4 = page down (6)
      2 = cancel           5 = confirm (load selected config)

    Cancel and confirm exit explorer mode (via return) before reaching
    the LED-restore / render code at the bottom.  Navigation keys (0,1,3,4)
    fall through to restore their dim LED and re-render the list.
    """
    configs = S._explorer_configs
    n       = len(configs)

    if key_idx == 0:                        # cursor up
        if S._explorer_cursor > 0:
            S._explorer_cursor -= 1
            # Scroll window follows cursor when it moves above the top
            if S._explorer_cursor < S._explorer_scroll:
                S._explorer_scroll -= 6

    elif key_idx == 1:                      # page up — jump 6 items
        S._explorer_cursor = max(0, S._explorer_cursor - 6)
        S._explorer_scroll = (S._explorer_cursor // 6) * 6

    elif key_idx == 2:                      # cancel — exit, no config change
        exit_explorer()
        return

    elif key_idx == 3:                      # cursor down
        if S._explorer_cursor < n - 1:
            S._explorer_cursor += 1
            # Scroll window follows cursor when it moves below the bottom
            if S._explorer_cursor >= S._explorer_scroll + 6:
                S._explorer_scroll += 6

    elif key_idx == 4:                      # page down — jump 6 items
        S._explorer_cursor = min(n - 1, S._explorer_cursor + 6)
        S._explorer_scroll = (S._explorer_cursor // 6) * 6

    elif key_idx == 5:                      # confirm — load selected config
        if 0 <= S._explorer_cursor < n:
            name = configs[S._explorer_cursor]
            # Tear down explorer state before switching
            S.explorer_mode       = False
            S._explorer_grp       = None
            S._explorer_up_lbl    = None
            S._explorer_dn_lbl    = None
            S._explorer_item_lbls = None
            S._explorer_configs   = None
            switch_config(name)   # restores display, LEDs, runs init_commands
        return

    # --- Navigation keys (0,1,3,4) reach here ---
    # Restore dim LED for the key that was just released
    c = _EXPLORER_LEDS_DIM[key_idx]
    for led in range(3):
        S.pixels[key_idx * 3 + led] = c
    S.pixels.show()
    # Re-render the list with updated cursor/scroll and push to display
    _explorer_render()
    S.display.refresh()
