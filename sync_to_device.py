"""
Sync E:/dev/ultramidi (git repo) -> G: (CircuitPython device)
Watches for file changes on E: and deploys them to G:.

Usage:
  python sync_to_device.py          # watch mode (continuous)
  python sync_to_device.py --once   # one-shot sync
"""

import sys
import os
import time
import shutil
import hashlib
import configparser
from pathlib import Path

_cfg = configparser.ConfigParser()
_cfg_path = Path(__file__).parent / "sync_config.ini"
if not _cfg_path.is_file():
    print(f"Config not found: {_cfg_path}")
    print("Copy sync_config.ini.example to sync_config.ini and edit it.")
    sys.exit(1)
_cfg.read(_cfg_path)

SRC = Path(_cfg["paths"]["src"])
DST = Path(_cfg["paths"]["dst"])

EXCLUDE_DIRS = {
    "__pycache__", ".claude", ".fseventsd",
    "System Volume Information", ".git", ".Trashes", ".vscode",
    "docs"
}
EXCLUDE_FILES = {
    ".dropbox.device", ".git", ".gitignore",
    "sync_to_device.py", "sync_from_device.py",
    "sync_config.ini", "sync_config.ini.example",
    "README.md"
}


def device_available():
    """Check if the CircuitPython device is actually reachable."""
    try:
        return (DST / "boot_out.txt").is_file()
    except OSError:
        return False


def wait_for_device():
    """Block until the device is available. Interruptible with Ctrl+C."""
    print("Device not available, waiting for reconnection...")
    while not device_available():
        time.sleep(2)
    print("Device reconnected!")


def file_hash(path):
    """Quick hash to detect changes."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def get_src_files():
    """Return dict of {relative_path: absolute_path} for all source files."""
    files = {}
    for root, dirs, filenames in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f in EXCLUDE_FILES:
                continue
            src_path = Path(root) / f
            rel = src_path.relative_to(SRC)
            files[rel] = src_path
    return files


def free_space():
    """Return free space on DST as a human-readable string."""
    usage = shutil.disk_usage(DST)
    kb = usage.free / 1024
    return f"{kb:.1f} KB free"


def sync(verbose=True):
    """One-shot sync from E: to G:. Returns number of files changed."""
    changed = 0
    src_files = get_src_files()

    # Copy new/modified files
    for rel, src_path in src_files.items():
        dst_path = DST / rel
        if dst_path.exists():
            if file_hash(src_path) == file_hash(dst_path):
                continue
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        changed += 1
        if verbose:
            print(f"  -> {rel}")

    return changed


def watch(interval=2):
    """Watch E: for changes and sync to G: continuously."""
    print(f"Watching {SRC} -> {DST} (every {interval}s)")
    print("Press Ctrl+C to stop.\n")

    initial = True

    while True:
        try:
            if not device_available():
                wait_for_device()

            n = sync()
            if n:
                if initial:
                    print(f"Initial sync: {n} file(s) deployed. {free_space()}\n")
                else:
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] Deployed {n} file(s) to device. {free_space()}")
            elif initial:
                print(f"Already in sync. {free_space()}\n")

            initial = False
            time.sleep(interval)

        except OSError:
            # Device disconnected mid-sync -- loop back to wait for it
            continue
        except KeyboardInterrupt:
            print("\nStopped.")
            break


if __name__ == "__main__":
    if "--once" in sys.argv:
        if not device_available():
            print("Device not connected.")
            sys.exit(1)
        try:
            n = sync()
            print(f"Done. {n} file(s) deployed. {free_space()}")
        except OSError:
            print("Device disconnected during sync.")
            sys.exit(1)
    else:
        watch()
