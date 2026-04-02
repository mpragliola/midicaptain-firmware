Review the config page files under ultrasetup/ for correctness.

For each config directory under ultrasetup/, read its page*.txt files and check:
- Bracket syntax: values must be `[value]` with no nesting
- MIDI channels must be 1-16
- CC numbers must be 0-127
- PC values must be 0-127
- Key references in [KEY] commands must be valid (0-31)
- CMD references must be 1-9
- Cycle counts must be > 0
- LED color values must be valid hex (0xRRGGBB) or `-`
- No circular CMD/KEY references

Cross-reference against the command syntax in ultrasetup/page-template.txt and docs/COMMANDS.md. Report any issues found.
