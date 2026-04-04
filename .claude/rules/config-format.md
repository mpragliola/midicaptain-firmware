---
paths:
  - "ultrasetup/**"
---

# Config File Format

Config files are `.txt` files under `ultrasetup/` (e.g. `init.txt`, `live_rig.txt`).
The filename (without `.txt`) is the config name shown in Explorer Mode.
`aliases.txt` and `config-template.txt` are excluded from config discovery.

## Structure

Each file has one `[global]` section, then one or more `[page]` sections (numbered from 0),
each followed by its `[keyN]` sections.

- Sections: `[global]`, `[page]` (repeatable), `[key0]`–`[key31]` (per page)
- Values are bracket-delimited: `[channel][CC][control][value]`
- Cycle steps are 1-based in config files, 0-based internally
- Colors: hex `0xRRGGBB`, `-` = unchanged, `0x000000` = off
- Global aliases: `ultrasetup/aliases.txt`
- Full option reference: `ultrasetup/config-template.txt`

## Key Naming

| Name    | Index | Type                        |
|---------|-------|-----------------------------|
| SW1–SW3 | 0–2   | Physical footswitches       |
| SWA–SWC | 3–5   | Physical footswitches       |
| V6–V31  | 6–31  | Virtual keys (MIDI CC input)|
