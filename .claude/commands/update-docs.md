Review and update project documentation to match the current state of the firmware code.

Read the firmware source files (code.py, engine.py, config.py, state.py, validate.py) and compare against:
- docs/ARCHITECTURE.md — hardware pins, async model, file map, behavioral model
- docs/COMMANDS.md — supported commands and syntax
- docs/CONFIGURATION.md — config file format and options
- docs/PAGES.md — page system, explorer mode
- docs/VISUALIZATIONS.md — display layout modes
- ultrasetup/page-template.txt — annotated config template

Flag any discrepancies where the docs don't match the code, and fix them. Focus on:
- New or removed config options
- Changed command behavior
- Updated constants or defaults
- New features not yet documented

Use GIT history to track changes.