# display.py — Display class: owns all ST7789 display state and update queue

import gc
import displayio
import terminalio
import state as S


class Display:
    """Owns all display hardware references, displayio objects, fonts,
    visualization state, and the pending-update queue.

    Constructed once in code.py after hardware init; stored on state.py as
    S.disp.  All display writes go through methods on this object rather than
    module-level globals on state.py.
    """

    __slots__ = (
        # Hardware
        '_hw_display',
        '_backlight',
        # Label module (bitmap_label or label fallback)
        '_lmod',
        # Fonts
        'font_status',
        'font_page',
        'font_sub',
        'font_subgrid',
        'font_big',
        # Vis layout tables
        '_vis_main_font',
        '_vis_main_label_y',
        '_vis_sub_area_top',
        # Layout constants
        '_sub_cell_w',
        '_sub_grid_x',
        # displayio hierarchy
        'splash',
        '_bg_palette',
        'status_label',
        '_sub_group',
        '_page_bar_palette',
        'page_label',
        # Sub-grid objects
        '_sub_bar_bitmap',
        '_sub_bar_palettes',
        '_sub_bar_tiles',
        '_sub_labels',
        # Visualization runtime state (merged _vis_sub_cell_h + _sub_cell_h)
        '_vis_sublabels',
        '_vis_sub_max_chars',
        '_sub_cell_h',
        # Pending update queue
        '_dirty',
        '_pending_page',
        '_pending_status',
        '_pending_subs',
        '_pending_sub_colors',
    )

    def __init__(self, hw_display, backlight, lmod, fonts):
        """Build the full displayio hierarchy and initialize the update queue.

        hw_display — ST7789 display object
        backlight  — pwmio.PWMOut
        lmod       — label module (bitmap_label or label fallback)
        fonts      — dict with keys: status, page, sub, subgrid, big
        """
        self._hw_display = hw_display
        self._backlight  = backlight
        self._lmod       = lmod

        # Fonts
        self.font_status  = fonts['status']
        self.font_page    = fonts['page']
        self.font_sub     = fonts['sub']
        self.font_subgrid = fonts['subgrid']
        self.font_big     = fonts['big']

        # Vis layout tables
        self._vis_main_font    = [None, self.font_subgrid, self.font_sub,
                                  self.font_status, self.font_big]
        self._vis_main_label_y = [0, 30, 30, 43, 35]
        self._vis_sub_area_top = [28, 62, 70, 161, 161]

        # Layout constants
        self._sub_cell_w = 78
        self._sub_grid_x = [40, 120, 200]

        # Pending update queue
        self._dirty              = False
        self._pending_page       = None
        self._pending_status     = None
        self._pending_subs       = [None] * 12
        self._pending_sub_colors = [None] * 12

        # Visualization runtime state
        self._vis_sublabels     = 6
        self._vis_sub_max_chars = 5
        self._sub_cell_h        = 38

        # ---- Build displayio hierarchy ----

        self.splash = displayio.Group()

        # splash[0] — background layer (solid color by default)
        _bg_bitmap      = displayio.Bitmap(hw_display.width, hw_display.height, 1)
        self._bg_palette = displayio.Palette(1)
        self._bg_palette[0] = 0x000000
        self.splash.append(displayio.TileGrid(_bg_bitmap, pixel_shader=self._bg_palette))

        # splash[1] — main status label
        self.status_label = lmod.Label(
            self.font_status,
            text="",
            color=0xFFFFFF,
            scale=1,
            line_spacing=0.9,
            anchor_point=(0.5, 0),
            anchored_position=(hw_display.width // 2, 43),
        )
        self.splash.append(self.status_label)

        # splash[2] — sub-grid group
        # 12 palettes (all transparent), 6 initial tiles + 6 initial labels;
        # apply_vis() rebuilds tiles/labels to match n_subs each page switch.
        self._sub_bar_bitmap  = displayio.Bitmap(self._sub_cell_w, 38, 1)
        self._sub_bar_palettes = []
        self._sub_bar_tiles    = []
        self._sub_labels       = []
        self._sub_group        = displayio.Group()

        for i in range(12):
            sp = displayio.Palette(1)
            sp[0] = 0x000000
            sp.make_transparent(0)
            self._sub_bar_palettes.append(sp)

        for i in range(6):
            st = displayio.TileGrid(
                self._sub_bar_bitmap,
                pixel_shader=self._sub_bar_palettes[i],
                x=999, y=999)
            self._sub_bar_tiles.append(st)
            self._sub_group.append(st)
        for i in range(6):
            sl = lmod.Label(
                self.font_subgrid,
                text="",
                color=0xFFFFFF,
                scale=1,
                anchor_point=(0.5, 0.5),
                anchored_position=(999, 999),
            )
            self._sub_labels.append(sl)
            self._sub_group.append(sl)

        self.splash.append(self._sub_group)

        # splash[3] — page bar (color strip behind page name)
        _page_bar_bitmap    = displayio.Bitmap(hw_display.width, 28, 1)
        self._page_bar_palette = displayio.Palette(1)
        self._page_bar_palette[0] = 0x000000
        self._page_bar_palette.make_transparent(0)
        self.splash.append(
            displayio.TileGrid(_page_bar_bitmap, pixel_shader=self._page_bar_palette)
        )

        # splash[4] — page name label
        self.page_label = lmod.Label(
            self.font_page,
            text="",
            color=0xf84848,
            scale=2,
            anchor_point=(0.5, 0.0),
            anchored_position=(hw_display.width // 2, 0),
        )
        self.splash.append(self.page_label)

        hw_display.show(self.splash)

    # ---- Brightness ----

    def set_brightness(self, pct):
        """Set screen brightness 0-100."""
        self._backlight.duty_cycle = int(max(0, min(100, pct)) / 100 * 65535)

    # ---- Background ----

    def set_background_color(self, color_int):
        """Set the background layer to a solid color."""
        self._bg_palette[0] = color_int

    def set_background_image(self, bmp_obj, bg_file):
        """Replace the background layer with a bitmap image.

        bg_file is the open file handle; the caller is responsible for keeping
        it open for the lifetime of the firmware run.
        """
        self.splash[0] = displayio.TileGrid(bmp_obj, pixel_shader=bmp_obj.pixel_shader)

    # ---- Pending update queue ----

    def set_page(self, name):
        """Queue a page name update."""
        self._pending_page = name

    def set_status(self, text):
        """Queue a main label text update."""
        self._pending_status = text

    def set_sub(self, idx, text):
        """Queue a sublabel text update."""
        self._pending_subs[idx] = text

    def set_sub_color(self, idx, color_int):
        """Queue a sublabel color update. color_int=-1 means transparent."""
        self._pending_sub_colors[idx] = color_int

    def mark_dirty(self):
        """Signal that the display needs a refresh on the next disp_task tick."""
        self._dirty = True

    # ---- Flush ----

    def flush(self):
        """Apply all pending updates and refresh the hardware display."""
        self._dirty = False
        if self._pending_page is not None:
            self.page_label.text = self._pending_page
            self._pending_page   = None
        if self._pending_status is not None:
            self.status_label.text = self._pending_status.replace(":", "\n")
            self._pending_status   = None
        for i in range(self._vis_sublabels):
            if self._pending_subs[i] is not None:
                self._sub_labels[i].text = self._pending_subs[i][:self._vis_sub_max_chars]
                self._pending_subs[i] = None
            if self._pending_sub_colors[i] is not None:
                c = self._pending_sub_colors[i]
                if c == -1:
                    self._sub_bar_palettes[i].make_transparent(0)
                else:
                    self._sub_bar_palettes[i][0] = c
                    self._sub_bar_palettes[i].make_opaque(0)
                    r = (c >> 16) & 0xFF
                    g = (c >> 8)  & 0xFF
                    b = c & 0xFF
                    self._sub_labels[i].color = (
                        0x000000 if (r * 299 + g * 587 + b * 114) > 128000
                        else 0xFFFFFF
                    )
                self._pending_sub_colors[i] = None
        self._hw_display.refresh()

    # ---- Display group control ----

    def show(self, group):
        """Show a displayio group (e.g. the explorer overlay)."""
        self._hw_display.show(group)

    def restore(self):
        """Restore the performance splash group as the active display."""
        self._hw_display.show(self.splash)

    def refresh(self):
        """Force an immediate hardware refresh without flushing the queue."""
        self._hw_display.refresh()

    # ---- Visualization layout ----

    def _compute_vis_layout(self, ml_size, n_subs):
        """Return (sub_area_top, cell_h, num_rows, sub_font, sub_scale, max_chars)."""
        num_rows = max(1, n_subs // 3)
        sat = self._vis_sub_area_top[ml_size]
        ch  = (240 - sat - num_rows) // num_rows
        if   ch >= 42: sf, sc, mc = self.font_sub,     1, 4
        elif ch >= 28: sf, sc, mc = self.font_subgrid,  1, 5
        elif ch >= 16: sf, sc, mc = self.font_page,     2, 6
        else:          sf, sc, mc = self.font_page,     1, 10
        return sat, ch, num_rows, sf, sc, mc

    def apply_vis(self, page):
        """Rebuild the visualization layout for a page.

        Called from engine.apply_page() after LED state is reset.  Handles
        page bar color, main label font, and the sublabel grid.
        """
        # Page bar
        self.page_label.color = page.color
        bg = page.bgcolor
        if bg is not None:
            self._page_bar_palette[0] = bg
            self._page_bar_palette.make_opaque(0)
        else:
            self._page_bar_palette.make_transparent(0)

        self._pending_page   = page.name
        self._pending_status = None

        # Visualization layout
        ml_size = page.vis_mainlabel_size
        n_subs  = page.vis_sublabels
        sat, ch, num_rows, sub_font, sub_scale, mc = self._compute_vis_layout(ml_size, n_subs)
        self._vis_sublabels     = n_subs
        self._vis_sub_max_chars = mc

        if S.DEBUG:
            print("[VIS] ml_size={} n_subs={} sat={} ch={} mc={}".format(
                ml_size, n_subs, sat, ch, mc))

        # Main label: recreate with the right font, or park off-screen for size=0
        main_font = self._vis_main_font[ml_size]
        if main_font is None:
            self.status_label = self._lmod.Label(
                self.font_status, text="", color=0xFFFFFF,
                scale=1, line_spacing=0.9,
                anchor_point=(0.5, 0),
                anchored_position=(999, 999))
        else:
            self.status_label = self._lmod.Label(
                main_font, text="", color=0xFFFFFF,
                scale=1, line_spacing=0.9,
                anchor_point=(0.5, 0),
                anchored_position=(self._hw_display.width // 2,
                                   self._vis_main_label_y[ml_size]))
        self.splash[1] = self.status_label

        # Rebuild sub bitmap if cell height changed
        if ch != self._sub_cell_h:
            self._sub_cell_h = ch
            self._sub_bar_bitmap = displayio.Bitmap(self._sub_cell_w, ch, 1)
            gc.collect()

        # Rebuild _sub_group with exactly n_subs tile+label pairs
        while len(self._sub_group):
            self._sub_group.pop()
        self._sub_bar_tiles = []
        self._sub_labels    = []

        for i in range(n_subs):
            t = displayio.TileGrid(
                self._sub_bar_bitmap,
                pixel_shader=self._sub_bar_palettes[i],
                x=999, y=999)
            self._sub_bar_tiles.append(t)
            self._sub_group.append(t)
        for i in range(n_subs):
            lbl = self._lmod.Label(
                sub_font, text="", color=0xFFFFFF,
                scale=sub_scale, line_spacing=0.9,
                anchor_point=(0.5, 0.5),
                anchored_position=(999, 999))
            self._sub_labels.append(lbl)
            self._sub_group.append(lbl)
        gc.collect()

        # Position active sublabel slots and reset pending state
        for i in range(n_subs):
            if page.keys[i]["stompmode"] > 0:
                col = i % 3
                row = i // 3
                ry  = sat + ch // 2 + row * ch
                self._sub_bar_tiles[i].x = col * 80 + (80 - self._sub_cell_w) // 2
                self._sub_bar_tiles[i].y = ry - ch // 2
                self._sub_labels[i].anchored_position = (self._sub_grid_x[col], ry)
            self._sub_bar_palettes[i].make_transparent(0)
            self._pending_subs[i]       = ""
            self._pending_sub_colors[i] = None

        self._dirty = True

    def show_errors(self, errors, page_num):
        """Override the display with page validation errors."""
        self._page_bar_palette[0] = 0xCC2200
        self._page_bar_palette.make_opaque(0)
        self.page_label.color = 0xFFFFFF
        self._pending_page = "P{}:ERR".format(page_num)

        for i in range(len(self._sub_bar_palettes)):
            self._sub_bar_palettes[i].make_transparent(0)
        for i in range(len(self._sub_labels)):
            self._sub_labels[i].text = ""

        txt = "\n".join(errors[:8])
        self.status_label = self._lmod.Label(
            terminalio.FONT, text=txt, color=0xFFFFFF,
            scale=2, line_spacing=1.2,
            anchor_point=(0.5, 0),
            anchored_position=(self._hw_display.width // 2, 30))
        self.splash[1] = self.status_label
        self._dirty = True
