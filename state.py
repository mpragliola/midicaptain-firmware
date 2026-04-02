# state.py — shared runtime state, constants, and hardware references
# No heavy imports here; hardware objects are assigned by code.py during init.

DEBUG = True

NUM_PHYSICAL_KEYS = 6
NUM_TOTAL_KEYS    = 32
KEY_NAMES = ["SW1", "SW2", "SW3", "SWA", "SWB", "SWC"]

# Key timing (seconds)
DEBOUNCE_SEC    = 0.020
LONGPRESS_SEC   = 0.500
REBOOT_HOLD_SEC = 2.0
REBOOT_COMBO    = (0, 2, 3, 5)
RELOAD_HOLD_SEC = 1.0
RELOAD_COMBO    = (0, 2)


# Runtime state
page_cur       = 0
cfg            = None
cycle_pos      = [-1] * NUM_TOTAL_KEYS
long_cycle_pos = [-1] * NUM_TOTAL_KEYS
group_active   = {}
long_group_active = {}
_dn_advanced   = [False] * NUM_TOTAL_KEYS
display_dirty  = False
_page_switched       = False
_pending_page_switch = None
_active_key          = None
_pc_state      = {}
cfg_name       = "init"   # active config subdirectory name under ultrasetup/
explorer_mode  = False    # True while the config-browser overlay is active

# Pending display updates
_pending_status     = None
_pending_subs       = [None] * 12
_pending_sub_colors = [None] * 12
_pending_page       = None

# Visualization state
_vis_sublabels     = 6
_vis_sub_max_chars = 5
_vis_sub_cell_h    = 38

# Display layout constants
_SUB_CELL_W  = 78
_sub_cell_h  = 38
_SUB_GRID_X  = [40, 120, 200]

# Vis layout tables (populated by code.py after font loading)
_VIS_MAIN_FONT    = None
_VIS_MAIN_LABEL_Y = [0, 30, 30, 43, 35]
_VIS_SUB_AREA_TOP = [28, 62, 70, 161, 161]

# Explorer mode runtime state.
# Populated by enter_explorer(), cleared to None by exit_explorer()/confirm.
# These are transient — only valid while explorer_mode is True.
_explorer_grp       = None   # the displayio.Group shown during explorer
_explorer_up_lbl    = None   # "^" scroll-up indicator Label
_explorer_dn_lbl    = None   # "v" scroll-down indicator Label
_explorer_item_lbls = None   # list of 6 Label objects (visible item slots)
_explorer_configs   = None   # sorted list of config subfolder names
_explorer_cursor    = 0      # index into _explorer_configs of highlighted item
_explorer_scroll    = 0      # index of the first visible item (multiple of 6)

# Hardware references (set by code.py during init)
pixels = None
_uart  = None
_usb_midi_iface = None
backlight = None
display   = None
splash    = None
page_label = None
status_label = None
_page_bar_palette = None
_sub_bar_bitmap   = None
_sub_bar_palettes = None
_sub_bar_tiles    = None
_sub_labels       = None
_sub_group        = None
_lmod = None   # label module (bitmap_label or label fallback)

# Font references (set by code.py)
FONT_STATUS  = None
FONT_PAGE    = None
FONT_SUB     = None
FONT_SUBGRID = None
FONT_BIG     = None


def _compute_vis_layout(ml_size, n_subs):
    """Return (sub_area_top, cell_h, num_rows, sub_font, sub_scale, max_chars)."""
    num_rows = max(1, n_subs // 3)
    sat = _VIS_SUB_AREA_TOP[ml_size]
    ch = (240 - sat - num_rows) // num_rows
    if   ch >= 42: sf, sc, mc = FONT_SUB, 1, 4
    elif ch >= 28: sf, sc, mc = FONT_SUBGRID, 1, 5
    elif ch >= 16: sf, sc, mc = FONT_PAGE, 2, 6
    else:          sf, sc, mc = FONT_PAGE, 1, 10
    return sat, ch, num_rows, sf, sc, mc


def _key_name(idx):
    """Human-readable key name for debug output."""
    if idx < NUM_PHYSICAL_KEYS:
        return KEY_NAMES[idx]
    return "V{}".format(idx)


def _first_non_null_color(led_triple):
    """Return the first non-None color tuple from a [c0, c1, c2] LED list."""
    for col in led_triple:
        if col is not None:
            return col
    return None
