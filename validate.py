# validate.py — page config validator (runs on-device at page load)
#
# Call validate_cfg(cfg, page_num) after load_page() to get a list of
# error strings. Empty list means the config is valid.
#
# Error strings use "context:detail" format — the colon is intentional:
# engine.py's disp_task replaces ":" with newline in the status label,
# producing a clean two-line display. Sub-labels show the truncated string.

_MAX_ERRORS = 8  # stop collecting after this many


def _try_int(v):
    """Return (int_value, True) or (None, False) for a string token."""
    if not v or v == "-":
        return None, False
    try:
        return int(v), True
    except (ValueError, TypeError):
        return None, False


def _check_cmd(a, b, c, d, ctx, errs):
    """Validate a single (a, b, c, d) command tuple."""
    if a == "CMD":
        n, ok = _try_int(b)
        if not ok or not (1 <= n <= 9):
            errs.append("{}:CMD?{}".format(ctx, (b or "")[:4]))
        return

    if a == "PAGE":
        if b and b.lower() not in ("inc", "dec"):
            n, ok = _try_int(b)
            if not ok:
                errs.append("{}:PAGE?{}".format(ctx, b[:4]))
            elif n < 0:
                errs.append("{}:PAGE<0".format(ctx))
        return

    if a == "KEY":
        n, ok = _try_int(b)
        if not ok or not (0 <= n <= 31):
            errs.append("{}:KEY?{}".format(ctx, (b or "")[:4]))
        return

    # MIDI command: a=channel, b=type, c=val1, d=val2
    ch, ok = _try_int(a)
    if not ok:
        errs.append("{}:ch?{}".format(ctx, str(a)[:4]))
        return
    if not (1 <= ch <= 16):
        errs.append("{}:ch{}".format(ctx, ch))

    mt = b.upper() if b else ""

    if mt == "PC":
        if c and c.lower() not in ("inc", "dec"):
            v, ok = _try_int(c)
            if ok and not (0 <= v <= 127):
                errs.append("{}:PC{}".format(ctx, v))
        if d:
            v, ok = _try_int(d)
            if ok and v < 1:
                errs.append("{}:PCstep{}".format(ctx, v))

    elif mt == "CC":
        v, ok = _try_int(c)
        if ok and not (0 <= v <= 127):
            errs.append("{}:CC#{}".format(ctx, v))
        v, ok = _try_int(d)
        if ok and not (0 <= v <= 127):
            errs.append("{}:CCv{}".format(ctx, v))

    elif mt == "NT":
        v, ok = _try_int(c)
        if ok and not (0 <= v <= 127):
            errs.append("{}:NT{}".format(ctx, v))
        if d:
            v, ok = _try_int(d)
            if ok and not (0 <= v <= 127):
                errs.append("{}:NTv{}".format(ctx, v))

    elif mt:
        errs.append("{}:?{}".format(ctx, mt[:4]))


def _check_cmds(cmds, ctx, errs):
    for cmd in cmds:
        if len(errs) >= _MAX_ERRORS:
            return
        _check_cmd(cmd[0], cmd[1], cmd[2], cmd[3], ctx, errs)


def _check_cmd_cycles(cfg, errs):
    """Detect cyclic CMD macro references using Kahn's algorithm (iterative)."""
    # Unified lookup: page macros override global macros (mirrors runtime resolution)
    all_cmds = {}
    for cid, cmds in cfg.get("global_cmds", {}).items():
        all_cmds[cid] = cmds
    for cid, cmds in cfg.get("cmds", {}).items():
        all_cmds[cid] = cmds
    if not all_cmds:
        return

    # Build adjacency: deps[a] = set of cmd IDs that macro a calls
    deps = {}
    for cid, cmds in all_cmds.items():
        refs = set()
        for cmd in cmds:
            if cmd[0] == "CMD":
                n, ok = _try_int(cmd[1])
                if ok and n in all_cmds:
                    refs.add(n)
        deps[cid] = refs

    # Kahn's: count incoming edges for each node
    in_deg = {cid: 0 for cid in deps}
    for refs in deps.values():
        for ref in refs:
            if ref in in_deg:
                in_deg[ref] += 1

    queue = [cid for cid, d in in_deg.items() if d == 0]
    while queue:
        node = queue.pop()
        for neighbor in deps.get(node, ()):
            if neighbor in in_deg:
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

    # Any node still with in_deg > 0 is part of a cycle
    for cid, d in in_deg.items():
        if d > 0 and len(errs) < _MAX_ERRORS:
            errs.append("cmd{}:cycle".format(cid))


def validate_cfg(cfg, page_num):
    """Validate a parsed page config dict.

    Returns a list of error strings (empty = valid). Errors use
    'context:detail' format for display on the device screen.
    """
    errs = []
    pn = str(page_num)

    # --- Global settings (only meaningful from page 0) ---
    b = cfg["led_brightness"]
    if not (0 <= b <= 100):
        errs.append("p{}:brt={}".format(pn, b))
    b = cfg["screen_brightness"]
    if not (0 <= b <= 100):
        errs.append("p{}:scr={}".format(pn, b))

    # --- Global and page macros ---
    for cid, cmds in cfg["global_cmds"].items():
        if len(errs) >= _MAX_ERRORS:
            break
        _check_cmds(cmds, "gc{}".format(cid), errs)
    for cid, cmds in cfg["cmds"].items():
        if len(errs) >= _MAX_ERRORS:
            break
        _check_cmds(cmds, "pc{}".format(cid), errs)
    _check_cmd_cycles(cfg, errs)

    # --- Init commands ---
    if cfg["init_commands"]:
        _check_cmds(cfg["init_commands"], "init", errs)

    # --- Per-key checks ---
    for idx in range(len(cfg["keys"])):
        if len(errs) >= _MAX_ERRORS:
            break
        kc = cfg["keys"][idx]
        pfx = "k{}".format(idx)

        g = kc["group"]
        if not (0 <= g <= 31):
            errs.append("{}:grp={}".format(pfx, g))

        g = kc["longgroup"]
        if not (0 <= g <= 31):
            errs.append("{}:lgrp={}".format(pfx, g))

        sm = kc["stompmode"]
        if sm not in (0, 1, 2):
            errs.append("{}:stomp={}".format(pfx, sm))

        cy = kc["cycle"]
        lcy = kc["longcycle"]
        if cy < 1:
            errs.append("{}:cy={}".format(pfx, cy))
        if lcy < 0:
            errs.append("{}:lcy={}".format(pfx, lcy))

        # LED count vs cycle
        nl = len(kc["leds"])
        if nl > cy:
            errs.append("{}:{}leds>cy{}".format(pfx, nl, cy))
        if kc["leds_l"] and lcy == 0:
            errs.append("{}:ledl,lcy=0".format(pfx))
        elif lcy > 0 and len(kc["leds_l"]) > lcy:
            errs.append("{}:{}ledl>lcy{}".format(pfx, len(kc["leds_l"]), lcy))

        # Label count vs cycle
        if len(kc["labels"]) > cy:
            errs.append("{}:{}lbl>cy{}".format(pfx, len(kc["labels"]), cy))
        if kc["labels_l"] and lcy == 0:
            errs.append("{}:lbll,lcy=0".format(pfx))

        # Command step vs cycle
        for (step, act), cmds in kc["commands"].items():
            if len(errs) >= _MAX_ERRORS:
                break
            if act in ("dn", "up") and step > cy:
                errs.append("{}:s{}>cy{}".format(pfx, step, cy))
            elif act in ("ldn", "lup"):
                ref = lcy if lcy > 0 else cy
                if step > ref:
                    errs.append("{}:ls{}>lcy{}".format(pfx, step, ref))
            _check_cmds(cmds, "{}{}{}".format(pfx, step, act[:2]), errs)

    return errs
