"""
Sync git repo -> CircuitPython device
Watches for file changes and deploys them automatically.

Usage:
  python sync_to_device.py          # watch mode (continuous)
  python sync_to_device.py --once   # one-shot sync
  python sync_to_device.py --debug  # debug device discovery
"""

import sys
import os
import time
import shutil
import hashlib
from pathlib import Path

DEBUG = "--debug" in sys.argv
SRC = Path(__file__).parent


def find_device():
    """Scan all drives for CircuitPython device (boot_out.txt present)."""
    devices = []
    try:
        # Windows: scan all drive letters
        for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{drive_letter}:/")
            if not drive.exists():
                continue
            boot_out = drive / "boot_out.txt"
            if boot_out.is_file():
                if DEBUG:
                    print(f"[DEBUG] Found device: {drive}")
                devices.append(drive)
            elif DEBUG:
                print(f"[DEBUG] Scanned {drive} - no boot_out.txt")
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Scan error: {e}")
    if DEBUG:
        print(f"[DEBUG] Device discovery complete: {len(devices)} device(s) found")
    return devices


def get_device():
    """Get the CircuitPython device path, prompting if multiple found."""
    devices = find_device()
    if not devices:
        print("Error: CircuitPython device not found.")
        print("Ensure it's connected and mounted as a USB drive.")
        sys.exit(1)
    if len(devices) == 1:
        if DEBUG:
            print(f"[DEBUG] Selected device: {devices[0]}")
        return devices[0]
    # Multiple devices found -- prompt user
    if DEBUG:
        print(f"[DEBUG] Multiple devices found, prompting user...")
    print("Multiple CircuitPython devices found:")
    for i, d in enumerate(devices, 1):
        print(f"  {i}) {d}")
    while True:
        try:
            choice = int(input("Select device (number): "))
            if 1 <= choice <= len(devices):
                selected = devices[choice - 1]
                if DEBUG:
                    print(f"[DEBUG] User selected: {selected}")
                return selected
        except ValueError:
            pass
        print("Invalid choice.")

DST = get_device()

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


def sync(verbose=True, synced_src_hashes=None):
    """One-shot sync from E: to G:. Returns number of files changed.

    synced_src_hashes: optional dict {rel: src_hash} of files already synced
    this session. Files whose source hash hasn't changed since last sync are
    skipped even if the device modified them (e.g. line-ending normalization).
    """
    changed = 0
    src_files = get_src_files()

    # Detect stale files in ultrasetup/ (present on device but not in source)
    dst_ultrasetup = DST / "ultrasetup"
    src_ultrasetup_rels = {rel for rel in src_files if rel.parts[0] == "ultrasetup"}
    stale = False
    if dst_ultrasetup.is_dir():
        for dst_path in dst_ultrasetup.rglob("*"):
            if dst_path.is_file():
                rel = dst_path.relative_to(DST)
                if rel not in src_ultrasetup_rels:
                    stale = True
                    break

    if stale:
        shutil.rmtree(dst_ultrasetup)
        if synced_src_hashes is not None:
            # Force re-sync of all ultrasetup files since we wiped the dir
            for rel in list(synced_src_hashes):
                if rel.parts[0] == "ultrasetup":
                    del synced_src_hashes[rel]
        if verbose:
            print("  Cleared ultrasetup/ (stale files removed)")

    # Copy new/modified files
    for rel, src_path in src_files.items():
        src_h = file_hash(src_path)
        dst_path = DST / rel
        # Skip if source hasn't changed since we last synced it AND file is present
        if synced_src_hashes is not None and synced_src_hashes.get(rel) == src_h and dst_path.exists():
            continue
        if dst_path.exists() and file_hash(dst_path) == src_h:
            # Device content matches source -- record and skip copy
            if synced_src_hashes is not None:
                synced_src_hashes[rel] = src_h
            continue
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        if synced_src_hashes is not None:
            synced_src_hashes[rel] = src_h
        changed += 1
        if verbose:
            print(f"  -> {rel}")

    return changed


def watch(interval=2):
    """Watch E: for changes and sync to G: continuously."""
    print(f"Watching {SRC} -> {DST} (every {interval}s)")
    print("Press Ctrl+C to stop.\n")

    initial = True
    # Track source hashes of files we've already synced to avoid re-syncing
    # files that the device modifies after writing (e.g. line-ending normalization).
    synced_src_hashes = {}

    while True:
        try:
            if not device_available():
                wait_for_device()
                synced_src_hashes.clear()

            n = sync(synced_src_hashes=synced_src_hashes)
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
            synced_src_hashes.clear()
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
