# Visualization Modes

The display layout can be customized per page using two parameters in the `[page]` section.

## Parameters

### vis_mainlabel_size

Controls the size and prominence of the main status label (the large text in the center that shows the active key's label).

| Value | Description | Font | Main label region |
|-------|-------------|------|-------------------|
| **0** | Hidden | — | 0px (sublabels fill the screen) |
| **1** | Minuscule | 24pt | 34px |
| **2** | Tiny | 32pt | 42px |
| **3** | Big (default) | 48pt | 133px (current layout) |
| **4** | Bigger | 64pt | 133px (same region, larger font) |

Default is **3** if omitted — identical to the standard layout.

### vis_sublabels

Controls how many sublabel cells are shown in the sub-grid.

| Value | Grid | Keys shown |
|-------|------|------------|
| **6** (default) | 3 columns x 2 rows | Physical keys 0-5 only |
| **12** | 3 columns x 4 rows | Keys 0-11 (physical 0-5 + virtual 6-11) |

With `vis_sublabels = [12]`, virtual keys 6-11 get their own sublabel cells. Define `ledN` on these keys to set sublabel background colors — the colors won't drive NeoPixels (virtual keys have none), but they will color the sublabel tile.

## Layout Calculation

The display is 240x240 pixels. The page name bar occupies the top 28px (fixed). The remaining space is split between the main label and the sub-grid based on `vis_mainlabel_size`.

**Sublabel cell height** = `(240 - sub_area_top - num_rows) / num_rows`

| vis_mainlabel_size | vis_sublabels=6 (2 rows) | vis_sublabels=12 (4 rows) |
|--------------------|--------------------------|---------------------------|
| 0 | 105px | 52px |
| 1 | 88px | 44px |
| 2 | 84px | 42px |
| 3 (default) | 38px | 19px |
| 4 | 38px | 19px |

## Sublabel Font Auto-Selection

The sublabel font is automatically chosen to be as large as possible while fitting within the cell height:

| Cell height | Font | Max characters |
|-------------|------|----------------|
| 42px+ | 32pt (Bahnschrift) | 4 |
| 28-41px | 24pt (Bahnschrift) | 5 |
| 16-27px | Terminal (2x scale) | 6 |
| < 16px | Terminal (1x scale) | 10 |

The default combination (size=3, sublabels=6) produces 38px cells with 24pt font and 5-character labels — identical to the standard layout.

## Configuration

```ini
[page]
page_name = [STOMPS]
vis_mainlabel_size = [1]
vis_sublabels = [12]
```

## Examples

### Large sublabels, no main label

Maximize sublabel size for a stomp-box style display where every key shows its state:

```ini
[page]
page_name = [FX BOARD]
vis_mainlabel_size = [0]
vis_sublabels = [6]

[key0]
group = [0]
cycle = [2]
stompmode = [1]
led1 = [0x000000][0x000000][0x000000]
led2 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [OFF]
label2 = [ON]
key1dn = [1][CC][50][0]
key2dn = [1][CC][50][127]
```

Each sublabel cell is 105px tall with 48pt font — large and readable from a distance.

### Small main label with 12 sublabels

Show a compact main label with all 12 keys visible, including 6 virtual keys driven by an external footswitch:

```ini
[page]
page_name = [FULL]
vis_mainlabel_size = [1]
vis_sublabels = [12]

[key0]
stompmode = [1]
cycle = [2]
led1 = [0x000000][][]
led2 = [0x00ff00][][]
label1 = [COMP]
label2 = [COMP]
key1dn = [1][CC][50][0]
key2dn = [1][CC][50][127]

; ... keys 1-5 similarly ...

[key6]
; virtual key — triggered via ext_capture_cc
stompmode = [1]
cycle = [2]
led1 = [0x000000][][]
led2 = [0x0000ff][][]
label1 = [DLY]
label2 = [DLY]
key1dn = [1][CC][2][0]
key2dn = [1][CC][2][127]

; ... keys 7-11 similarly ...
```

Each sublabel cell is 44px tall with 32pt font. The main label uses 24pt and sits just below the page bar.

### Bigger main label (default sublabels)

Make the main label more prominent using a 64pt font, while keeping the standard 6-key sub-grid:

```ini
[page]
page_name = [PRESET]
vis_mainlabel_size = [4]
vis_sublabels = [6]
```

The main label fills more of the center area with the larger font. Sublabels remain at the standard 38px / 24pt size.
