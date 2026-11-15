"""Command-line front end: the same behaviour as the original script, built on the engine."""

import sys
import threading
import time

from .devices import BUILTIN, EXTERNAL, VIRTUAL, choose_targets, list_devices
from .engine import Engine

TAGS = {BUILTIN: "LAPTOP", VIRTUAL: "VIRTUAL", EXTERNAL: "EXTERNAL"}


def run_session(include_virtual: bool) -> bool:
    """One mirroring session. Returns True if it should restart, False to exit."""
    devices = list_devices()
    source = next((d for d in devices if d.is_default), None)
    if source is None:
        print("\n  No audio output devices found.")
        return False

    print(f"\n  Source (Windows default): {source.name}")
    print("  Detected devices:")
    for d in devices:
        flag = " *DEFAULT*" if d.id == source.id else ""
        print(f"    [{TAGS[d.kind]:>8}]{flag}  {d.name}")

    targets = choose_targets(devices, source.id, include_virtual)
    if not targets:
        print("\n  No target devices detected.")
        print("  Connect headphones, earbuds, or a Bluetooth device and re-run.")
        if not include_virtual:
            print("  TIP: Use --virtual to also mirror to virtual devices.")
        return False

    changed = threading.Event()

    def on_event(kind, **data):
        if kind in ("devices_changed", "target_lost", "source_lost"):
            changed.set()

    engine = Engine(on_event)
    engine.start(source.id, {d.id: 0 for d in targets})
    time.sleep(0.3)

    print(f"\n  [ACTIVE] Mirroring to {len(targets)} device(s):")
    for d in targets:
        print(f"    -> {d.name}")
    if source.kind == BUILTIN:
        print("\n  WARNING: Your Windows default output is your laptop speakers.")
        print("           Audio WILL play from laptop speakers (Windows controls this).")
        print("           To fix: change your Windows default to an external device,")
        print("           then restart this script.")
    print("\n  Press Ctrl+C to stop.\n")

    try:
        while not changed.is_set():
            peak = max(engine.levels().values(), default=0.0)
            bars = min(int(peak * 30), 30)
            sys.stdout.write(f"\r  Volume: [{'#' * bars}{'-' * (30 - bars)}] {min(int(peak * 100), 100):3d}%  ")
            sys.stdout.flush()
            time.sleep(0.2)
        print("\n\n  [!] Audio devices changed or a device was lost. Restarting...")
        return True
    except KeyboardInterrupt:
        print("\n\n  Stopped by user.")
        return False
    finally:
        engine.stop()


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    include_virtual = "--virtual" in argv
    print("=" * 52)
    print("  Fernwire - Automatic Mode")
    print("=" * 52)
    while run_session(include_virtual):
        print("  Reconnecting in 2 seconds...\n")
        time.sleep(2)
    print("  Bye!")
