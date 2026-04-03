Review the config files under ultrasetup/ for correctness.

For each .txt config file under ultrasetup/ (excluding aliases.txt and config-template.txt), read it and check:
- Bracket syntax: values must be `[value]` with no nesting
- MIDI channels must be 1-16
- CC numbers must be 0-127
- PC values must be 0-127
- Key references in [KEY] commands must be valid (0-31)
- CMD references must be 1-9
- Cycle counts must be > 0
- LED color values must be valid hex (0xRRGGBB) or `-`
- No circular CMD/KEY references
- [page] sections are properly ordered with their [keyN] sections

Cross-reference against the command syntax in ultrasetup/config-template.txt and docs/COMMANDS.md. Report any issues found.
