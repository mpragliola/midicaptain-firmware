# config.py — page config parsing (no hardware dependencies)

import os
import state as S

# =============================================================================
# ALIASES — loaded once from ultrasetup/aliases.txt
# 
# We can define aliases in ultrasetup/aliases.txt; if a bracketed value is
# equal to an alias, it will be substituted as suck. Aliases have mostly two
# use cases:
# - use them as "variable". 
#   You define only once in one place the MIDI Channel of your target device. 
#   Then you use the alias instead of explicitly mentioning the channel. If 
#   one day you decide that the target must receive on a new channel, you can
#   change the value only once instead of having to update every command.
# - use them as "device mappings".
#   Usually devices come with a MIDI implementation chart so you know which
#   messages are needed to control the device itself. You can add device 
#   specific mapping as mnemonic.
#
# Important: the substitutions are "stupid", make sure you choose an alias
# that is unlikely to be matched by unrelated values, f. ex. by using prefixes.
# =============================================================================
_aliases = {}
try:
    with open("ultrasetup/aliases.txt") as _af:
        for _line in _af:
            _line = _line.strip()
            if not _line or _line.startswith(";"):
                continue
            if "=" in _line:
                _ak, _, _av = _line.partition("=")
                _ak = _ak.strip()
                _av = _av.partition(";")[0].strip()
                try:
                    _aliases[_ak] = int(_av)
                except ValueError:
                    pass
except OSError:
    pass


def _resolve(s):
    """Resolve a config value token to an integer.
    Checks _aliases first, then falls back to int().
    Returns 0 for empty / '-' tokens.
    """
    if not s or s == "-":
        return 0
    if s in _aliases:
        return _aliases[s]
    return int(s)


def parse_brackets(s):
    """Extract all [value] tokens from a string into a list of strings."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "[":
            j = s.find("]", i)
            if j < 0:
                if S.DEBUG:
                    print("[ERR] parse_brackets: missing ']' in: {}".format(s))
                break
            result.append(s[i + 1:j])
            i = j + 1
        else:
            i += 1
    return result


def parse_commands(s):
    """Parse a command string into a list of (a, b, c, d) tuples."""
    cmds = []
    for part in s.split(" "):
        part = part.strip()
        if not part:
            continue
        vals = parse_brackets(part)
        if not vals:
            continue
        while len(vals) < 4:
            vals.append("")
        cmds.append(tuple(vals[:4]))
    return cmds


def parse_led_color(s):
    """Parse a hex color string into (r, g, b).
    Returns None for null tokens, (0,0,0) for explicit black.
    """
    s = s.strip()
    if s == "" or s == "-":
        return None
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    v = int(s, 16)
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def parse_color_int(s):
    """Parse a hex color token into an integer. Returns 0 for null/empty."""
    s = s.strip()
    if s == "" or s == "-":
        return 0
    if s.startswith("0x") or s.startswith("0X"):
        return int(s[2:], 16)
    return int(s, 16)


def load_page(page_num):
    """Load and parse ultrasetup/page{page_num}.txt into a cfg dict."""
    filename = "ultrasetup/page{}.txt".format(page_num)

    cfg = {
        "page_name": "PAGE {}".format(page_num),
        "page_color": 0xF84848,
        "page_bgcolor": None,
        "page_bg": 0x000000,
        "page_bg_img": None,
        "global_cmds": {},
        "cmds": {},
        "init_commands": [],
        "led_brightness": 30,
        "screen_brightness": 50,
        "group_cycle": {},
        "capture_ch": -1,
        "capture_cc": -1,
        "midi_thru": False,
        "vis_mainlabel_size": 3,
        "vis_sublabels": 6,
        "keys": [
            {
                "group": 0, "longgroup": 0, "cycle": 1, "longcycle": 0, "stompmode": 0,
                "leds": [], "leds_l": [],
                "labels": [], "labels_l": [],
                "labels_d": [], "labels_u": [],
                "commands": {},
            }
            for _ in range(S.NUM_TOTAL_KEYS)
        ],
    }

    try:
        os.stat(filename)
    except OSError:
        return cfg

    current_section = None
    with open(filename, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";"):
                continue

            if line.startswith("[") and line.endswith("]") and "=" not in line:
                current_section = line[1:-1]
                continue

            if "=" not in line:
                continue

            k, _, v = line.partition("=")
            k    = k.strip()
            v    = v.strip()
            vals = parse_brackets(v)

            # ---- [global] section ----------------------------------------
            if current_section == "global":
                if k == "led_brightness":
                    cfg["led_brightness"] = int(vals[0]) if vals else 30
                elif k == "screen_brightness":
                    cfg["screen_brightness"] = int(vals[0]) if vals else 50
                elif k == "page_bg":
                    cfg["page_bg"] = parse_color_int(vals[0]) if vals else 0
                elif k == "page_bg_img":
                    v0 = vals[0].strip() if vals else ""
                    cfg["page_bg_img"] = v0 if (v0 and v0 != "-") else None
                elif k == "ext_capture_cc":
                    if len(vals) >= 2:
                        cfg["capture_ch"] = int(vals[0]) - 1
                        cfg["capture_cc"] = int(vals[1])
                elif k == "midi_thru":
                    cfg["midi_thru"] = (vals[0] == "1") if vals else False
                elif k.startswith("cmd") and k[3:].isdigit():
                    cmd_id = int(k[3:])
                    cfg["global_cmds"][cmd_id] = parse_commands(v)

            # ---- [page] section -----------------------------------------
            elif current_section == "page":
                if k == "page_name":
                    cfg["page_name"] = vals[0] if vals else ""
                elif k == "init_commands":
                    cfg["init_commands"] = parse_commands(v)
                elif k == "color":
                    cfg["page_color"] = parse_color_int(vals[0]) if vals else 0xF84848
                elif k == "bgcolor":
                    v0 = vals[0].strip() if vals else ""
                    cfg["page_bgcolor"] = parse_color_int(v0) if (v0 and v0 != "-") else None
                elif k.startswith("cmd") and k[3:].isdigit():
                    cmd_id = int(k[3:])
                    cfg["cmds"][cmd_id] = parse_commands(v)
                elif k == "vis_mainlabel_size":
                    cfg["vis_mainlabel_size"] = max(0, min(4, int(vals[0]))) if vals else 3
                elif k == "vis_sublabels":
                    v0 = int(vals[0]) if vals else 6
                    cfg["vis_sublabels"] = 12 if v0 >= 12 else 6
                elif k.startswith("group_cycle"):
                    gid = int(k[len("group_cycle"):])
                    cfg["group_cycle"][gid] = (vals[0] == "1") if vals else False

            # ---- [keyN] section -----------------------------------------
            elif current_section is not None and current_section.startswith("key"):
                try:
                    idx = int(current_section[3:])
                except ValueError:
                    continue
                if idx < 0 or idx >= S.NUM_TOTAL_KEYS:
                    continue
                kc = cfg["keys"][idx]

                if k == "group":
                    kc["group"] = int(vals[0]) if vals else 0

                elif k == "longgroup":
                    kc["longgroup"] = int(vals[0]) if vals else 0

                elif k == "cycle":
                    _cv = int(vals[0]) if vals else 1
                    if _cv < 1:
                        if S.DEBUG:
                            print("[ERR] key{} cycle={} invalid, using 1".format(idx, _cv))
                        _cv = 1
                    kc["cycle"] = _cv

                elif k == "longcycle":
                    kc["longcycle"] = int(vals[0]) if vals else 0

                elif k == "stompmode":
                    kc["stompmode"] = int(vals[0]) if vals else 0

                elif k.startswith("led") and k.endswith("l") and k[3:-1].isdigit():
                    colors = [parse_led_color(c) for c in vals]
                    while len(colors) < 3:
                        colors.append(None)
                    kc["leds_l"].append(colors[:3])

                elif k.startswith("led") and k[3:].isdigit():
                    colors = [parse_led_color(c) for c in vals]
                    while len(colors) < 3:
                        colors.append(None)
                    kc["leds"].append(colors[:3])

                elif k.startswith("label") and k.endswith("l") and k[5:-1].isdigit():
                    kc["labels_l"].append(vals[0] if vals else "")

                elif k.startswith("label") and k[5:].isdigit():
                    kc["labels"].append(vals[0] if vals else "")

                elif k.startswith("label") and k.endswith("d") and k[5:-1].isdigit():
                    kc["labels_d"].append(vals[0] if vals else "")

                elif k.startswith("label") and k.endswith("u") and k[5:-1].isdigit():
                    kc["labels_u"].append(vals[0] if vals else "")

                elif k.startswith("key") and len(k) > 3:
                    rest = k[3:]
                    for action in ("ldn", "lup", "dn", "up"):
                        if rest.endswith(action):
                            step_str = rest[:-len(action)]
                            if step_str.isdigit():
                                step = int(step_str)
                                kc["commands"][(step, action)] = parse_commands(v)
                            break
    return cfg
