# pages.py — Page class: owns page configuration and runtime state

import state as S
from config import load_page as _load_page_dict


class Page:
    """Owns all configuration and runtime state for a single page.

    Configuration values are extracted from the raw config dict at construction
    time and stored as direct attributes. The raw dict is not retained.

    Runtime state (cycle positions, group active flags) is managed via
    behavior methods rather than direct array access.
    """

    __slots__ = (
        'number',
        # Page-level config
        'name', 'color', 'bgcolor', 'background_int', 'background_image',
        'led_brightness', 'screen_brightness',
        'capture_channel', 'capture_cc', 'midi_thru',
        'vis_mainlabel_size', 'vis_sublabels',
        'init_commands', 'errors',
        'global_cmds', 'cmds', 'group_cycle',
        'keys',
        # Runtime state
        '_cycle_pos', '_long_cycle_pos', '_group_active', '_long_group_active'
    )

    def __init__(self, page_num, config_name=None):
        """Load and apply a page from config file.

        Reads the raw config dict, extracts all values into typed attributes,
        then discards the dict. config_name defaults to S.cfg_name.
        """
        raw = _load_page_dict(page_num, config_name)
        self.number = page_num

        # Page-level config — extracted once, owned directly
        self.name               = raw['page_name']
        self.color              = raw['page_color']
        self.bgcolor            = raw['page_bgcolor']
        self.background_int     = raw['page_bg']
        self.background_image   = raw['page_bg_img']
        self.led_brightness     = raw['led_brightness']
        self.screen_brightness  = raw['screen_brightness']
        self.capture_channel    = raw['capture_ch']
        self.capture_cc         = raw['capture_cc']
        self.midi_thru          = raw['midi_thru']
        self.vis_mainlabel_size = raw['vis_mainlabel_size']
        self.vis_sublabels      = raw['vis_sublabels']
        self.init_commands      = raw['init_commands']
        self.errors             = raw['page_errors']
        self.global_cmds        = raw['global_cmds']
        self.cmds               = raw['cmds']
        self.group_cycle        = raw['group_cycle']
        self.keys               = raw['keys']   # list of 32 key config dicts

        # Runtime state
        self._cycle_pos       = [-1] * S.NUM_TOTAL_KEYS
        self._long_cycle_pos  = [-1] * S.NUM_TOTAL_KEYS
        self._group_active      = {}
        self._long_group_active = {}

    # ---- Cycle advancement ----

    def advance_cycle(self, key_idx):
        """Advance the short-press cycle for a key and return the new position."""
        total = self.keys[key_idx]['cycle']
        self._cycle_pos[key_idx] = (self._cycle_pos[key_idx] + 1) % total
        return self._cycle_pos[key_idx]

    def advance_long_cycle(self, key_idx):
        """Advance the long-press cycle for a key and return the new position.

        Returns -1 if the key has no long cycle configured.
        """
        total = self.keys[key_idx].get('longcycle', 0)
        if total > 0:
            self._long_cycle_pos[key_idx] = (self._long_cycle_pos[key_idx] + 1) % total
            return self._long_cycle_pos[key_idx]
        return -1

    def get_cycle_pos(self, key_idx):
        """Current short-press cycle position for a key."""
        return self._cycle_pos[key_idx]

    def set_cycle_pos(self, key_idx, pos):
        """Set short-press cycle position directly (used by key simulation)."""
        self._cycle_pos[key_idx] = pos

    def get_long_cycle_pos(self, key_idx):
        """Current long-press cycle position for a key."""
        return self._long_cycle_pos[key_idx]

    def set_long_cycle_pos(self, key_idx, pos):
        """Set long-press cycle position directly (used by key simulation)."""
        self._long_cycle_pos[key_idx] = pos

    # ---- Group (radio-button) state ----

    def get_group_active(self, group_id):
        """Return the active key index in a group, or None."""
        return self._group_active.get(group_id, None)

    def set_group_active(self, group_id, key_idx):
        """Mark a key as active in a group, implicitly deactivating others."""
        self._group_active[group_id] = key_idx

    def get_group_active_long(self, group_id):
        """Return the active key index in a long-press group, or None."""
        return self._long_group_active.get(group_id, None)

    def set_group_active_long(self, group_id, key_idx):
        """Mark a key as active in a long-press group."""
        self._long_group_active[group_id] = key_idx

    # ---- Page reset ----

    def reset(self):
        """Reset all runtime state (called on page switch)."""
        for i in range(S.NUM_TOTAL_KEYS):
            self._cycle_pos[i]      = -1
            self._long_cycle_pos[i] = -1
        self._group_active      = {}
        self._long_group_active = {}
