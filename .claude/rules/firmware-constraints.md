---
paths:
  - "*.py"
---

# CircuitPython Firmware Constraints

Runtime: CircuitPython 7.3.1 on RP2040 (264 KB RAM, 2 MB flash).

- Never use f-strings — not supported in CP 7.3.1. Use `.format()` or `%` formatting.
- No type hints — `typing` module is unavailable.
- No `dataclasses`, `enum`, `pathlib`, or other CPython-only stdlib modules.
- Keep imports minimal — each import costs RAM.
- Avoid adding new `.py` files unless absolutely necessary — each module has import overhead.
- Avoid unnecessary object allocations, list comprehensions over large data, or string concatenation in loops. Prefer pre-allocated buffers and in-place mutation.
- `gc.collect()` calls are deliberate — do not remove them.
- No `time.sleep()` in the async event loop — use `await asyncio.sleep(0)` to yield.
- No automated tests — firmware is tested on hardware only.
