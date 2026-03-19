# Configuration examples

## Grouping PCs

Sometimes you want buttons to be mutually exclusive.
This is common with Program Changes (PC) on the same
device: as only one program is selected at a time, it
makes no sense to leave the LEDs on for any program
that is not currently selected.
By assigning the buttons to the same `group` (from 1
to number of buttons-1) we can obtain this effect.

```ini
[key0]
group = [1]
led1 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [Foo]
key1up = [1][PC][1]

[key1]
group = [1]
led1 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [Bar]
key1up = [1][PC][2]
```

---

## Cycling through states

A single button can cycle through multiple states.
Set `cycle` to the number of steps, then define
`ledN`, `labelN`, and `keyNdn`/`keyNup` for each step N.

```ini
[key0]
cycle = [3]
led1 = [0x00ff00][0x00ff00][0x00ff00]
led2 = [0xffff00][0xffff00][0xffff00]
led3 = [0xff0000][0xff0000][0xff0000]
label1 = [Clean]
label2 = [Crunch]
label3 = [Lead]
key1up = [1][PC][1]
key2up = [1][PC][2]
key3up = [1][PC][3]
```

---

## Long press

Buttons can have an independent long-press cycle.
Set `longcycle` to the number of long-press steps.
Use `ledNl`, `labelNl`, and `keyNldn`/`keyNlup`
for the long-press behavior.

This example uses the main press to select a preset
and long press to toggle delay on/off:

```ini
[key0]
cycle = [1]
longcycle = [2]
led1 = [0x00ff00][0x00ff00][]
led1l = [][][0x0000ff]
led2l = [][][0x000000]
label1 = [Clean]
label1l = [DLY ON]
label2l = [DLY OFF]
key1up = [1][PC][1]
key1ldn = [1][CC][2][127]
key2ldn = [1][CC][2][0]
```

---

## Long press grouping

Use `longgroup` to make long-press cycles mutually
exclusive across keys, like `group` does for main
cycles. When a key in a long group is long-pressed,
other keys in the same long group reset their long
cycle.

```ini
[key0]
group = [1]
longgroup = [1]
longcycle = [2]
led1l = [][][0x0000ff]
led2l = [][][0x000000]
label1l = [DLY ON]
label2l = [DLY OF]
key1ldn = [1][CC][2][127]
key2ldn = [1][CC][2][0]

[key1]
group = [1]
longgroup = [1]
longcycle = [2]
led1l = [][][0xff0000]
led2l = [][][0x000000]
label1l = [REV ON]
label2l = [REV OF]
key1ldn = [1][CC][3][127]
key2ldn = [1][CC][3][0]
```

Long-pressing key0 to enable delay will reset key1's
long cycle (turning off reverb), and vice versa.

---

## Multi-line labels

Use a colon (`:`) in the label text to create a
two-line label. Each line supports up to 8 characters.

```ini
[key0]
label1 = [Clean:chorus]
```

---

## Stomp mode

Use `stompmode` to reflect the button state in its
corresponding sub-panel on the display:

- `stompmode = [1]` reflects the main cycle
- `stompmode = [2]` reflects the long-press cycle

The sub-panel background color is taken from the first
non-null LED color in the definition. Labels in
sub-panels are limited to 5 characters.

```ini
[key0]
cycle = [2]
stompmode = [1]
led1 = [0x000000][0x000000][0x000000]
led2 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [OFF]
label2 = [ON]
key1dn = [1][CC][50][0]
key2dn = [1][CC][50][127]
```

---

## Command macros

Define reusable command sequences using `cmd1`–`cmd9`.
Macros can be defined in `[global]` (shared across all
pages) or in `[page]` (page-specific, overrides global).
Invoke them with `[CMD][N]`.

```ini
[global]
; global macro: reset delay and compressor
cmd1 = [1][CC][2][0] [1][CC][18][0]

[page]
; page macro overrides global cmd2 for this page only
cmd2 = [1][CC][50][0]

[key0]
group = [1]
label1 = [Clean]
key1up = [CMD][1] [1][PC][36]

[key1]
group = [1]
label1 = [Lead]
key1up = [CMD][1] [1][PC][47]
```

Both buttons first reset delay and compressor via the
global macro, then select their respective preset.

---

## Page switching

Use `[PAGE][N]` to switch to a different page.
Typically the last button is reserved for navigation.

```ini
[key5]
longcycle = [2]
led1 = [0xffffff][0xffffff][0xffffff]
key1dn = [PAGE][1]
key1ldn = [PAGE][2]
key2ldn = [PAGE][3]
```

Short press goes to page 1. Long press cycles between
pages 2 and 3.

---

## Init commands

Execute commands automatically when a page loads using
`init_commands`. Use `[KEY][n][c][lc]` to simulate
pressing a key on load (this replaces the old `init_key`).

```ini
[page]
page_name = [MAIN]
; send a bank select + program change on page load,
; then simulate pressing key 0 at cycle step 1
init_commands = [1][CC][32][2] [1][PC][0] [KEY][0][1][]
```

---

## Group cycle pause

By default, switching between keys in a group resets
the cycle to step 1. Set `group_cycleN = [1]` to
pause the cycle instead, so each key remembers its
last step when you return to it.

```ini
[page]
group_cycle1 = [1]

[key0]
group = [1]
cycle = [2]
label1 = [Amp A:clean]
label2 = [Amp A:drive]
key1up = [1][PC][1]
key2up = [1][PC][2]

[key1]
group = [1]
cycle = [2]
label1 = [Amp B:clean]
label2 = [Amp B:drive]
key1up = [1][PC][3]
key2up = [1][PC][4]
```

Pressing key0 then key1 then key0 again will return
to whichever step key0 was on, instead of resetting
to step 1.

---

## Sub-labels on press/release

Use `labelNd` (shown on press) and `labelNu` (shown
on release) to display temporary feedback without
changing the main label.

```ini
[key4]
cycle = [2]
led1 = [0x000000][0x000000][0x000000]
led2 = [0x00ff00][0x00ff00][0x00ff00]
label1d = [FX ON]
label2d = [FX OFF]
key1dn = [1][CC][4][127]
key2dn = [1][CC][4][0]
```

---

## PC increment / decrement

Scroll through presets without assigning a button per
program. Use `inc` or `dec` as the PC parameter.

```ini
[key0]
label1 = [PREV]
led1 = [0xff0000][0xff0000][0xff0000]
key1up = [1][PC][dec][1]

[key1]
label1 = [NEXT]
led1 = [0x00ff00][0x00ff00][0x00ff00]
key1up = [1][PC][inc][1]
```

---

## Simulating another key press

Use `[KEY][N]` to trigger another button. Optionally
set its cycle step with the third parameter and its
long-press cycle step with the fourth.

```ini
; pressing key5 activates key0 at cycle step 1
[key5]
label1 = [RESET]
key1dn = [KEY][0][1][]
```

---

## Using aliases

If an `aliases.txt` file is present, you can use
human-readable names instead of raw CC numbers.

```ini
; aliases.txt defines: tx_gain = 102, tx_dly_pwr = 2
[key0]
key1up = [1][CC][tx_gain][100]
key1ldn = [1][CC][tx_dly_pwr][127]
```

---

## Global settings

Control LED and screen brightness, and set a background
color or image for the display.

```ini
[global]
led_brightness = [50]
screen_brightness = [80]
; solid background color
page_bg = [0x300000]
; or use a .bmp image (240x20) from the wallpaper/ folder
; page_bg_img = [wp1]
; global macros (shared across all pages)
cmd1 = [1][CC][2][0] [1][CC][18][0]
```

---

## External footswitch via virtual keys

Use `ext_capture_cc` to assign a MIDI channel and CC#
for incoming external control. Virtual keys (6-31) let
you configure actions for external switches just like
physical buttons, minus LED feedback.

This example adds two external footswitches as virtual
keys 6 and 7. Key 6 toggles delay; key 7 cycles through
three presets grouped with physical keys.

The external device must send on channel 1, CC#30:
- Key 6 press: value 6 - Key 6 up: value 70
- Key 7 press: value 7 - Key 7 up: value 71

```ini
[global]
ext_capture_cc = [1][30]

[key0]
group = [1]
led1 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [Clean]
key1up = [1][PC][1]

[key1]
group = [1]
led1 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [Lead]
key1up = [1][PC][2]

[key6]
; external footswitch toggles delay on/off
cycle = [2]
label1 = [DLY ON]
label2 = [DLY OF]
key1dn = [1][CC][2][127]
key2dn = [1][CC][2][0]

[key7]
; external footswitch selects presets (grouped with physical keys)
group = [1]
cycle = [3]
label1 = [Acou]
label2 = [Funk]
label3 = [Jazz]
key1up = [1][PC][10]
key2up = [1][PC][20]
key3up = [1][PC][30]
```

---

## Mixing physical and virtual keys in a group

Groups work across physical and virtual keys. When any
key in the group is activated, the others reset. This
lets an external footswitch participate in radio-button
behavior alongside the physical buttons.

```ini
[key0]
group = [1]
led1 = [0x00ff00][0x00ff00][0x00ff00]
label1 = [Amp A]
key1up = [1][PC][1]

[key1]
group = [1]
led1 = [0x0000ff][0x0000ff][0x0000ff]
label1 = [Amp B]
key1up = [1][PC][2]

[key6]
; external switch - same group as physical keys 0 and 1
group = [1]
label1 = [Amp C]
key1up = [1][PC][3]
```

Pressing the external switch (sending CC value 6) selects
Amp C and turns off keys 0 and 1. Pressing a physical
button turns off the virtual key's display state.

---

## Visualization modes

Use `vis_mainlabel_size` and `vis_sublabels` in the
`[page]` section to customize the display layout.
See `docs/VISUALIZATIONS.md` for the full reference.

### Stomp board (no main label, large sublabels)

Hide the main label to maximize sublabel size:

```ini
[page]
page_name = [STOMPS]
vis_mainlabel_size = [0]
vis_sublabels = [6]

[key0]
stompmode = [1]
cycle = [2]
led1 = [0x000000][][]
led2 = [0x00ff00][][]
label1 = [OFF]
label2 = [ON]
key1dn = [1][CC][50][0]
key2dn = [1][CC][50][127]
```

Each sublabel cell is 105px tall with 48pt font (3 chars max).

### 12 sublabels with compact main label

Show virtual keys 6-11 alongside physical keys:

```ini
[page]
page_name = [FULL]
vis_mainlabel_size = [2]
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

[key6]
stompmode = [1]
cycle = [2]
led1 = [0x000000][][]
led2 = [0x0000ff][][]
label1 = [DLY]
label2 = [DLY]
key1dn = [1][CC][2][0]
key2dn = [1][CC][2][127]
```

Sublabel cells are 42px tall with 32pt font (4 chars max).
Virtual key 6's `led1`/`led2` set sublabel background color
(no NeoPixels are driven for virtual keys).
