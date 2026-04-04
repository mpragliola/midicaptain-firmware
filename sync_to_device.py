"""
Sync E:/dev/ultramidi -> MIDICAPTAIN (CircuitPython foot controller).

Waits for the MIDICAPTAIN drive to appear, checks writability, then syncs:
  fonts/  lib/  license  ultrasetup/  wallpaper/  *.py (root only)

After sync, watches for source changes and re-syncs automatically.
Press Ctrl+C to stop.
"""

import sys
import time
import shutil
import hashlib
import ctypes
from pathlib import Path

SRC = Path(__file__).parent

SYNC_DIRS = ["fonts", "lib", "ultrasetup", "wallpaper"]
SYNC_EXTRA = ["license"]   # root-level file or dir (handled generically)


# ---------------------------------------------------------------------------
# Drive detection
# ---------------------------------------------------------------------------

def _volume_label(drive: Path) -> str:
    buf = ctypes.create_unicode_buffer(256)
    try:
        ctypes.windll.kernel32.GetVolumeInformationW(
            str(drive) + "\\", buf, len(buf), None, None, None, None, 0
        )
        return buf.value
    except Exception:
        return ""


def find_midicaptain() -> Path | None:
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = Path(f"{letter}:/")
        try:
            if drive.exists() and _volume_label(drive) == "MIDICAPTAIN":
                return drive
        except OSError:
            pass
    return None


def is_readonly(drive: Path) -> bool:
    probe = drive / ".sync_probe"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return False
    except OSError:
        return True


def drive_present(drive: Path) -> bool:
    try:
        return drive.exists()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------

def _collect_src() -> dict:
    """Return {rel_path: abs_path} for all files that should be on the device."""
    files = {}

    # Root *.py files only
    for p in SRC.glob("*.py"):
        files[p.relative_to(SRC)] = p

    # Directories and extra items
    for name in SYNC_DIRS + SYNC_EXTRA:
        item = SRC / name
        if item.is_file():
            files[Path(name)] = item
        elif item.is_dir():
            for p in item.rglob("*"):
                if p.is_file():
                    files[p.relative_to(SRC)] = p

    return files


def _collect_dst(dst: Path) -> set:
    """Return {rel_path} for all files on device within our sync scope."""
    files = set()
    for p in dst.glob("*.py"):
        files.add(p.relative_to(dst))
    for name in SYNC_DIRS + SYNC_EXTRA:
        item = dst / name
        if item.is_file():
            files.add(Path(name))
        elif item.is_dir():
            for p in item.rglob("*"):
                if p.is_file():
                    files.add(p.relative_to(dst))
    return files


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def _hash(path: Path) -> str | None:
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def full_sync(dst: Path, synced: dict) -> int:
    """
    Sync SRC -> dst.  Updates `synced` {rel: src_hash} in-place.
    Returns count of files changed.

    `synced` is used to avoid re-copying files whose source hash hasn't
    changed — this prevents update loops caused by the device FAT driver
    modifying timestamps or line endings after a write.
    """
    src_files = _collect_src()
    dst_files = _collect_dst(dst)
    changed = 0

    # --- Delete files present on device but gone from source ---
    for rel in sorted(dst_files - set(src_files)):
        dst_path = dst / rel
        try:
            dst_path.unlink()
            print(f"  D {rel}")
            changed += 1
            synced.pop(rel, None)
            # Remove empty parent dirs
            try:
                dst_path.parent.rmdir()
            except OSError:
                pass
        except OSError as e:
            print(f"  ! Cannot delete {rel}: {e}")

    # --- Copy new or changed files ---
    for rel, src_path in sorted(src_files.items()):
        src_h = _hash(src_path)

        # Source unchanged since last successful sync and file still on device → skip
        if synced.get(rel) == src_h and (dst / rel).exists():
            continue

        dst_path = dst / rel
        is_new = not dst_path.exists()

        # Device already has the right content (e.g. after reconnect) → record and skip
        if not is_new and _hash(dst_path) == src_h:
            synced[rel] = src_h
            continue

        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            synced[rel] = src_h
            tag = "A" if is_new else "U"
            print(f"  {tag} {rel}")
            changed += 1
        except OSError as e:
            print(f"  ! Cannot copy {rel}: {e}")

    return changed


def _needs_sync(src_files: dict, synced: dict) -> bool:
    """Check source-side only (no device I/O) whether anything changed."""
    # New or modified files
    for rel, src_path in src_files.items():
        if synced.get(rel) != _hash(src_path):
            return True
    # Deleted files (still tracked in synced but gone from source)
    for rel in synced:
        if rel not in src_files:
            return True
    return False


def free_space(dst: Path) -> str:
    try:
        kb = shutil.disk_usage(dst).free / 1024
        return f"{kb:.1f} KB free"
    except OSError:
        return "? KB free"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    dst = None

    print("Waiting for MIDICAPTAIN drive...")

    while True:
        try:
            # ------------------------------------------------------------------
            # Phase 1: wait for the drive
            # ------------------------------------------------------------------
            while dst is None:
                dst = find_midicaptain()
                if dst is None:
                    time.sleep(2)
                    continue

                print(f"Found MIDICAPTAIN at {dst}")

                if is_readonly(dst):
                    print("Filesystem is READ-ONLY — cannot sync.")
                    print("Reconnect device in normal (non-BOOTSEL) mode.")
                    dst = None
                    time.sleep(5)
                else:
                    print("Filesystem is writable.")

            # ------------------------------------------------------------------
            # Phase 2: initial sync
            # ------------------------------------------------------------------
            print("\nSyncing...")
            synced = {}
            n = full_sync(dst, synced)
            if n:
                print(f"\n{n} file(s) synced. {free_space(dst)}")
            else:
                print(f"Already up to date. {free_space(dst)}")
            print("Watching for changes. Press Ctrl+C to stop.\n")

            # ------------------------------------------------------------------
            # Phase 3: watch
            # ------------------------------------------------------------------
            while True:
                time.sleep(2)

                if not drive_present(dst):
                    print("\nMIDICAPTAIN disconnected. Waiting...")
                    dst = None
                    synced.clear()
                    break

                src_files = _collect_src()
                if not _needs_sync(src_files, synced):
                    continue

                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] Changes detected:")
                n = full_sync(dst, synced)
                print(f"  {n} file(s) synced. {free_space(dst)}\n")

        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)
        except OSError as e:
            print(f"\nDevice error: {e}. Reconnecting...")
            dst = None
            synced = {}
            time.sleep(2)


if __name__ == "__main__":
    main()
