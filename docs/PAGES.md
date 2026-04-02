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

Each page has a **configuration file** inside its **config subfolder** 
(see [Multiple Configurations](#multiple-configurations) below).
Starting from `page0.txt`, then `page1.txt` and so on.  
Page 0 holds also global configurations.

Simply add, remove or modify the `pageX.txt` files to add, remove or
modify pages.

> See comments in `page-template.txt` for a complete spec.

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

Alternate between page 0 and 1 using key5's long press:

`page0.txt`:

```
[key5]
key1dn = [PAGE][1]
```

`page1.txt`:

```
[key5]
key1dn = [PAGE][0]
```

### Use cases

---

## Multiple Configurations

A **configuration** is a named set of pages. Each configuration lives in its
own subfolder under `ultrasetup/`:

```
ultrasetup/
  aliases.txt          <-- global aliases, shared by all configs
  page-template.txt    <-- reference template (not loaded by firmware)
  init/
    page0.txt
    page1.txt
    ...
  live_rig/
    page0.txt
    ...
  rehearsal/
    page0.txt
    ...
```

Each subfolder is an independent configuration with its own set of
`page0.txt`, `page1.txt`, etc. The `aliases.txt` file is **global** and
shared across all configurations — it stays at the `ultrasetup/` root level,
not inside any config subfolder.

### Startup rule

On boot the firmware scans `ultrasetup/` for subdirectories and picks the
active config:

1. If a subfolder named **`init`** exists, it is loaded.
2. Otherwise, the **first subfolder alphabetically** is loaded.
3. If no subfolders exist at all, the firmware starts with an empty default
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
- **Confirm** (SWC): loads the selected config's `page0.txt`, resets all key
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
   subfolder (e.g. `ultrasetup/my_setup/`).
3. Copy `page0.txt` (and any other pages) from an existing config into the
   new subfolder.
4. Edit the files as needed.
5. Safely eject and reboot.
6. Use Explorer Mode (SW3+SWA hold) to switch to the new config at runtime.

### Migration from single-config firmware (breaking change)

> **Warning:** This is a breaking change. The old flat structure
> (`ultrasetup/page0.txt`, `ultrasetup/page1.txt`, ...) is no longer supported.

Steps:

1. Boot in USB mode (hold SW1 while powering on).
2. Inside `ultrasetup/`, create a subfolder named `init/`.
3. Move all `page*.txt` files into `ultrasetup/init/`.
4. Leave `aliases.txt` where it is — it remains at `ultrasetup/aliases.txt`.
5. Safely eject and reboot.
