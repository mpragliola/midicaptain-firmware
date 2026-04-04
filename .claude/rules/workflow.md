# Development Workflow

1. Edit code locally in `E:/dev/ultramidi/`
2. `sync_to_device.py` watches and copies changes to device at `G:/`
3. Device executes `.py` files directly — no compilation step
4. Hot-reload: hold SW1+SW3 for 1s to reload current page config without reboot
5. Debug: set `DEBUG = True` in `state.py` for console logging

## Commit Style

Use imperative mood. Describe the *what* and *why*. Examples:
- "Implement validator. It will check among other things also recursion..."
- "Sync script: show free space. Space is an important constraint..."
- "Guard against division by zero in _compute_vis_layout"

## Documentation Maintenance

Docs live in `docs/`. Key files:
- `ARCHITECTURE.md` — hardware pins, MCU specs, firmware internals
- `COMMANDS.md` — command reference
- `PAGES.md` — page system and Explorer Mode
- `CONFIGURATION.md` — config file format
- `VISUALIZATIONS.md` — display layout modes

When making structural changes to the firmware, update `docs/ARCHITECTURE.md`.
When changing config format or commands, update the relevant doc and `ultrasetup/config-template.txt`.

Note: `docs/` also contains user-facing documentation. Keep Claude Code instructions in `.claude/rules/`, not in `docs/`.
