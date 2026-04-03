# explorer.py — Explorer Mode: config browser UI and navigation
#
# A single Explorer instance lives at S.explorer (created at module level).
# All transient display objects and cursor/scroll state are owned by the
# instance — state.py has no _explorer_* globals while explorer is inactive.
#
# Display isolation: enter() builds its own displayio.Group and swaps it
# in via S.disp.show().  S.disp.splash is untouched while active.  On
# exit or confirm, S.disp.restore() restores performance mode.
#
# LED feedback: each key gets a role-colored LED (purple=nav, cyan=page,
# red=cancel, green=confirm).  LEDs are dim at idle, brighten on press.

import displayio
import terminalio
import state as S
from config import list_configs
from engine import apply_page, exec_commands, switch_config


# LED palettes — base, full (press), dim (idle)
_LEDS_BASE = (
    (128, 0, 128),  # key 0: purple  (cursor up)
    (0, 128, 128),  # key 1: cyan    (page up)
    (255, 0, 0),    # key 2: red     (cancel)
    (128, 0, 128),  # key 3: purple  (cursor down)
    (0, 128, 128),  # key 4: cyan    (page down)
    (0, 255, 0),    # key 5: green   (confirm)
)
_LEDS_FULL = tuple(tuple(v // 2 for v in c) for c in _LEDS_BASE)
_LEDS_DIM  = tuple(tuple(v // 4 for v in c) for c in _LEDS_BASE)


class Explorer:
    """Owns all Explorer Mode state and UI logic."""

    __slots__ = (
        'active',
        '_grp', '_up_lbl', '_dn_lbl', '_item_lbls',
        '_configs', '_cursor', '_scroll',
    )

    def __init__(self):
        self.active     = False
        self._grp       = None
        self._up_lbl    = None
        self._dn_lbl    = None
        self._item_lbls = None
        self._configs   = None
        self._cursor    = 0
        self._scroll    = 0

    def _render(self):
        """Re-draw the explorer list from current cursor/scroll state.

        Color coding: yellow = cursor + active config, white = cursor only,
        green = active config, grey = other.  Items are prefixed with "> "
        for the cursor or "  " otherwise, capped at 14 chars.
        The "init" config is shown as "init (Def)" to mark it as the default.
        """
        configs = self._configs
        scroll  = self._scroll
        cursor  = self._cursor
        n       = len(configs)

        self._up_lbl.text = "^" if scroll > 0 else " "
        self._dn_lbl.text = "v" if scroll + 6 < n else " "

        for slot in range(6):
            idx = scroll + slot
            lbl = self._item_lbls[slot]
            if idx < n:
                name = configs[idx]
                is_cursor = (idx == cursor)
                is_active = (name == S.cfg_name)
                prefix = "> " if is_cursor else "  "
                display_name = (name + " (Def)") if name == "init" else name
                lbl.text = (prefix + display_name)[:14]
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

    def enter(self):
        """Activate Explorer Mode: build the config-browser UI and show it.

        Called when SW3+SWA are held for LONGPRESS_SEC.  Creates a separate
        displayio.Group with:
          - Title label: "SELECT CONFIG" (24pt, centered, y=4)
          - Scroll-up indicator: "^" or " " (terminal font 2x, y=36)
          - 6 item labels: config names (24pt, left-aligned, y=56..196)
          - Scroll-down indicator: "v" or " " (terminal font 2x, y=222)

        The cursor starts on the currently active config.  All 6 physical
        LEDs are set to their role color at dim intensity.
        """
        configs = list_configs()

        cursor = 0
        for i in range(len(configs)):
            if configs[i] == S.cfg_name:
                cursor = i
                break
        scroll = (cursor // 6) * 6

        grp = displayio.Group()
        grp.append(S.disp._lmod.Label(S.disp.font_subgrid, text="SELECT CONFIG",
                                      color=0xFFFFFF, anchor_point=(0.5, 0.0),
                                      anchored_position=(120, 4)))
        up_lbl = S.disp._lmod.Label(terminalio.FONT, text=" ", color=0x888888, scale=2,
                                    anchor_point=(0.5, 0.0), anchored_position=(120, 36))
        grp.append(up_lbl)

        item_lbls = []
        for slot in range(6):
            lbl = S.disp._lmod.Label(S.disp.font_subgrid, text="", color=0x666666,
                                     anchor_point=(0.0, 0.0),
                                     anchored_position=(4, 56 + slot * 28))
            grp.append(lbl)
            item_lbls.append(lbl)

        dn_lbl = S.disp._lmod.Label(terminalio.FONT, text=" ", color=0x888888, scale=2,
                                    anchor_point=(0.5, 0.0), anchored_position=(120, 222))
        grp.append(dn_lbl)

        self._grp       = grp
        self._up_lbl    = up_lbl
        self._dn_lbl    = dn_lbl
        self._item_lbls = item_lbls
        self._configs   = configs
        self._cursor    = cursor
        self._scroll    = scroll
        self.active     = True

        for k in range(6):
            for led in range(3):
                S.pixels[k * 3 + led] = _LEDS_DIM[k]
        S.pixels.show()

        S.disp.show(grp)
        self._render()
        S.disp.refresh()

    def exit(self):
        """Leave Explorer Mode without changing config (cancel)."""
        self.active     = False
        self._grp       = None
        self._up_lbl    = None
        self._dn_lbl    = None
        self._item_lbls = None
        self._configs   = None
        S.pixels.fill((0, 0, 0))
        S.pixels.show()
        S.disp.restore()
        apply_page()
        exec_commands(S.current_page.init_commands)

    def on_press(self, key_idx):
        """Brighten LED on press; on_key() restores dim on release."""
        c = _LEDS_FULL[key_idx]
        for led in range(3):
            S.pixels[key_idx * 3 + led] = c
        S.pixels.show()

    def on_key(self, key_idx):
        """Handle a key release while in Explorer Mode.

        Key mapping:
          0 = cursor up       3 = cursor down
          1 = page up (6)     4 = page down (6)
          2 = cancel           5 = confirm (load selected config)
        """
        configs = self._configs
        n       = len(configs)

        if key_idx == 0:                        # cursor up
            if self._cursor > 0:
                self._cursor -= 1
                if self._cursor < self._scroll:
                    self._scroll -= 6

        elif key_idx == 1:                      # page up — jump 6 items
            self._cursor = max(0, self._cursor - 6)
            self._scroll = (self._cursor // 6) * 6

        elif key_idx == 2:                      # cancel
            self.exit()
            return

        elif key_idx == 3:                      # cursor down
            if self._cursor < n - 1:
                self._cursor += 1
                if self._cursor >= self._scroll + 6:
                    self._scroll += 6

        elif key_idx == 4:                      # page down — jump 6 items
            self._cursor = min(n - 1, self._cursor + 6)
            self._scroll = (self._cursor // 6) * 6

        elif key_idx == 5:                      # confirm — load selected config
            if 0 <= self._cursor < n:
                name = configs[self._cursor]
                self.active     = False
                self._grp       = None
                self._up_lbl    = None
                self._dn_lbl    = None
                self._item_lbls = None
                self._configs   = None
                switch_config(name)
            return

        # Navigation keys (0,1,3,4) reach here — restore dim LED and re-render
        c = _LEDS_DIM[key_idx]
        for led in range(3):
            S.pixels[key_idx * 3 + led] = c
        S.pixels.show()
        self._render()
        S.disp.refresh()


# Single instance — created at import time so S.explorer is never None
S.explorer = Explorer()
