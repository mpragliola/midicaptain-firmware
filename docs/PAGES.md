# Pages

It is possible to define different sets of assignments for the footswitches,
subdivided in different **pages**. 

Each page will have:
* a name
* a distinctive color 
* a set of button configurations

The color and name will be reflected in the top
bar of the display.

Navigating between pages is fully customizable.

![Alt text](pages.png)

Pages are defined as successive `[page]` sections within a config file
(see [Multiple Configurations](#multiple-configurations) below).
They are numbered progressively from 0 in the order they appear.
The `[global]` section (at the top of the file) holds shared settings
that apply to all pages.

Simply add, remove or modify `[page]` sections (and their `[keyN]` sections)
to add, remove or modify pages.

> See comments in `config-template.txt` for a complete spec.

### Page navigation

Contrary to the original firmware, **page navigation is completely 
assignable**. 
* the advantage is that we can freely choose which actions will 
trigger page changes for each page and also delegate the function to
external controllers.
* the compromise is that without any explicit configuration, other pages
than 0 are unreachable and navigation must be explicitly implemented on
any page.

#### Example configuration

Alternate between page 0 and 1 using key5's press. Both pages are in the
same config file:

```
[page]
page_name = [MAIN]
...

[key5]
key1dn = [PAGE][1]

[page]
page_name = [LEAD]
...

[key5]
key1dn = [PAGE][0]
```

### Use cases

---

## Multiple Configurations

A **configuration** is a named set of pages stored in a single `.txt` file
under `ultrasetup/`:

```
ultrasetup/
  aliases.txt            <-- global aliases, shared by all configs
  config-template.txt    <-- reference template (not loaded by firmware)
  init.txt
  live_rig.txt
  rehearsal.txt
```

Each file is an independent configuration containing all its pages. The
filename (without `.txt`) is the config name shown in Explorer Mode.
The `aliases.txt` file is **global** and shared across all configurations.

### Startup rule

On boot the firmware scans `ultrasetup/` for `.txt` config files and picks
the active config:

1. If a file named **`init.txt`** exists, it is loaded.
2. Otherwise, the **first config file alphabetically** is loaded.
3. If no config files exist at all, the firmware starts with an empty default
   config (no pages, no commands — the display will show "PAGE 0").

### Explorer Mode — switching configs at runtime

Explorer Mode is a full-screen config browser that lets you switch between
configurations without connecting to a computer.

#### Entering Explorer Mode

Hold **SW3 + SWA** (keys 2 and 3) **simultaneously for 0.5 seconds**.

When activated:
- The performance display is replaced by a scrollable text list
- All 6 LEDs switch to role-colored indicators (see table below)
- Normal key functions (MIDI, page switching, etc.) are suspended
- The reload combo (SW1+SW3) and reboot combo (SW1+SW3+SWA+SWC)
  are disabled to prevent accidental triggers

#### Display layout

```
+---------------------------+
|      SELECT CONFIG        |   <-- title (24pt, centered)
|            ^              |   <-- scroll-up indicator (shown if more above)
|    init                   |
|  > live_rig               |   <-- ">" marks the cursor
|    rehearsal              |
|                           |
|                           |
|                           |
|            v              |   <-- scroll-down indicator (shown if more below)
+---------------------------+
```

Up to **6 config names** are visible at once. Scroll indicators `^` and `v`
appear when there are more entries above or below the visible window.

#### Key mapping

| Key | Function | LED color |
|-----|----------|-----------|
| SW1 (key 0) | Cursor up | Purple (dim) |
| SW2 (key 1) | Page up (scroll 6 items) | Cyan (dim) |
| SW3 (key 2) | **Cancel** — exit, no change | Red (dim) |
| SWA (key 3) | Cursor down | Purple (dim) |
| SWB (key 4) | Page down (scroll 6 items) | Cyan (dim) |
| SWC (key 5) | **Confirm** — load selected config | Green (dim) |

LEDs are shown at **half intensity** while idle and go to **full intensity**
momentarily when the key is pressed, providing visual feedback.

#### Text color coding

| Color | Meaning |
|-------|---------|
| White | Cursor position |
| Green | Currently loaded (active) config |
| Yellow | Cursor on the currently loaded config |
| Grey | Other configs |

#### Exiting Explorer Mode

- **Cancel** (SW3): returns to performance mode with the previous config
  unchanged. The display, LEDs, and init_commands are re-applied as they were.
- **Confirm** (SWC): loads the selected config's first page, resets all key
  state, applies the page layout, and runs init_commands. You are now in
  performance mode with the new config active.

#### Notes

- The cursor starts on the currently active config when explorer opens.
- Releasing SW3/SWA after the activation combo does **not** trigger cancel or
  cursor-down — those releases are suppressed.
- The explorer display is a separate `displayio.Group` — the performance
  display (S.splash) is untouched during browsing.

### Creating a new configuration

1. Boot in USB mode (hold SW1 while powering on).
2. Inside the `ultrasetup/` folder on the MIDICAPTAIN drive, create a new
   `.txt` file (e.g. `ultrasetup/my_setup.txt`).
3. Add a `[global]` section, then one or more `[page]` sections with their
   `[keyN]` sections. You can copy from an existing config file as a starting
   point.
4. Edit the file as needed.
5. Safely eject and reboot.
6. Use Explorer Mode (SW3+SWA hold) to switch to the new config at runtime.
