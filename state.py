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
page_cur     = 0
current_page = None  # Active Page object (from pages.py)
_dn_advanced         = [False] * NUM_TOTAL_KEYS
_page_switched       = False
_pending_page_switch = None
_active_key          = None
_pc_state      = {}
cfg_name       = "init"   # active config name (filename stem under ultrasetup/)
explorer_mode  = False    # True while the config-browser overlay is active

# Explorer mode runtime state.
# Populated by enter_explorer(), cleared to None by exit_explorer()/confirm.
# These are transient — only valid while explorer_mode is True.
_explorer_grp       = None   # the displayio.Group shown during explorer
_explorer_up_lbl    = None   # "^" scroll-up indicator Label
_explorer_dn_lbl    = None   # "v" scroll-down indicator Label
_explorer_item_lbls = None   # list of 6 Label objects (visible item slots)
_explorer_configs   = None   # sorted list of config names (filename stems)
_explorer_cursor    = 0      # index into _explorer_configs of highlighted item
_explorer_scroll    = 0      # index of the first visible item (multiple of 6)

# Hardware references (set by code.py during init)
pixels = None
_uart  = None
_usb_midi_iface = None
disp   = None   # Display instance (display.py)


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
