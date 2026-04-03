# pages.py — Page class for encapsulating page state and behavior

import state as S
from config import load_page as _load_page_dict


class Page:
    """Encapsulates a single page: config, runtime state, and page-level behavior.

    Owns all state and configuration for a page. Provides methods to:
    - Advance cycles for keys
    - Manage group active states (radio-button logic)
    - Reset page state on page switch
    - Access page configuration and settings
    """

    __slots__ = (
        'number', 'cfg', '_cycle_pos', '_long_cycle_pos',
        '_group_active', '_long_group_active'
    )

    def __init__(self, page_num, config_name=None):
        """Load a page from config file.

        Args:
            page_num: Page number (0-based)
            config_name: Config name (e.g. 'init', 'live_rig'). If None, uses S.cfg_name
        """
        self.number = page_num
        self.cfg = _load_page_dict(page_num, config_name)

        # Per-page runtime state
        self._cycle_pos = [-1] * S.NUM_TOTAL_KEYS
        self._long_cycle_pos = [-1] * S.NUM_TOTAL_KEYS
        self._group_active = {}
        self._long_group_active = {}

    # ---- Key data access ----

    def get_key(self, key_idx):
        """Return key config dict for a given key index."""
        return self.cfg['keys'][key_idx]

    # ---- Cycle advancement ----

    def advance_cycle(self, key_idx):
        """Advance cycle for a key, return new cycle position.

        Wraps around when reaching total cycles for this key.
        """
        key_cfg = self.cfg['keys'][key_idx]
        total = key_cfg['cycle']
        self._cycle_pos[key_idx] = (self._cycle_pos[key_idx] + 1) % total
        return self._cycle_pos[key_idx]

    def advance_long_cycle(self, key_idx):
        """Advance long-press cycle for a key, return new position.

        Returns -1 if key has no long cycle.
        """
        key_cfg = self.cfg['keys'][key_idx]
        total = key_cfg.get('longcycle', 0)
        if total > 0:
            self._long_cycle_pos[key_idx] = (self._long_cycle_pos[key_idx] + 1) % total
            return self._long_cycle_pos[key_idx]
        return -1

    def get_cycle_pos(self, key_idx):
        """Get current cycle position for a key."""
        return self._cycle_pos[key_idx]

    def set_cycle_pos(self, key_idx, pos):
        """Set cycle position directly (for key simulation)."""
        self._cycle_pos[key_idx] = pos

    def get_long_cycle_pos(self, key_idx):
        """Get long-press cycle position for a key."""
        return self._long_cycle_pos[key_idx]

    def set_long_cycle_pos(self, key_idx, pos):
        """Set long-press cycle position directly (for key simulation)."""
        self._long_cycle_pos[key_idx] = pos

    # ---- Group (radio-button) logic ----

    def set_group_active(self, group_id, key_idx):
        """Mark a key as active in a group (short-press).

        Implicitly deactivates other keys in the group (radio-button behavior).
        """
        self._group_active[group_id] = key_idx

    def get_group_active(self, group_id):
        """Return the active key in a group, or None if no key is active."""
        return self._group_active.get(group_id, None)

    def clear_group(self, group_id):
        """Clear a group (deactivate all keys in it)."""
        if group_id in self._group_active:
            del self._group_active[group_id]

    def set_group_active_long(self, group_id, key_idx):
        """Mark a key as active in a long-press group."""
        self._long_group_active[group_id] = key_idx

    def get_group_active_long(self, group_id):
        """Return the active key in a long-press group, or None."""
        return self._long_group_active.get(group_id, None)

    def clear_group_long(self, group_id):
        """Clear a long-press group."""
        if group_id in self._long_group_active:
            del self._long_group_active[group_id]

    # ---- Page reset ----

    def reset(self):
        """Reset all page state (used on page switch or init)."""
        for i in range(S.NUM_TOTAL_KEYS):
            self._cycle_pos[i] = -1
            self._long_cycle_pos[i] = -1
        self._group_active = {}
        self._long_group_active = {}

    # ---- Page-level properties ----

    @property
    def name(self):
        """Page display name."""
        return self.cfg['page_name']

    @property
    def color(self):
        """Page color (0xRRGGBB)."""
        return self.cfg['page_color']

    @property
    def bgcolor(self):
        """Page background color override (or None)."""
        return self.cfg['page_bgcolor']

    @property
    def background_int(self):
        """Page background as int (0xRRGGBB)."""
        return self.cfg['page_bg']

    @property
    def background_image(self):
        """Page background image filename (or None)."""
        return self.cfg['page_bg_img']

    @property
    def led_brightness(self):
        """LED brightness (0-255)."""
        return self.cfg['led_brightness']

    @property
    def screen_brightness(self):
        """Screen brightness (0-255)."""
        return self.cfg['screen_brightness']

    @property
    def capture_channel(self):
        """MIDI channel for CC capture (-1 = disabled)."""
        return self.cfg['capture_ch']

    @property
    def capture_cc(self):
        """CC number to capture (-1 = disabled)."""
        return self.cfg['capture_cc']

    @property
    def midi_thru(self):
        """Whether MIDI thru is enabled."""
        return self.cfg['midi_thru']

    @property
    def init_commands(self):
        """Init commands to run when page loads."""
        return self.cfg['init_commands']

    @property
    def errors(self):
        """Validation errors (if any)."""
        return self.cfg['page_errors']
