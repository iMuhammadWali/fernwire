"""
Audio Splitter - Automatic Mode

Automatically detects external audio devices (Bluetooth, USB, headphone jack)
and mirrors your PC audio to them. No user interaction needed.

Rules:
  - Built-in laptop speakers are always ignored as targets.
  - Audio is captured from the Windows default output (loopback).
  - Mirrors to all connected external devices that aren't the default.
  - Watches for device changes (connect/disconnect/default switch) and
    auto-restarts the session.

Setup:  pip install soundcard numpy
Run:    python main.py              # mirror to external devices only
        python main.py --virtual    # also mirror to virtual devices
"""

import queue
import sys
import threading
import time
import warnings

import numpy as np
import soundcard as sc

warnings.filterwarnings("ignore")

# ─── Audio settings ───────────────────────────────────────────────
RATE = 48000
CHANNELS = 2
BLOCK = 480        # ~10 ms per chunk at 48 kHz
MAX_QUEUE = 2      # keeps mirror latency around ~20 ms
POLL_INTERVAL = 3  # seconds between device-change checks

SILENCE = np.zeros((BLOCK, CHANNELS), dtype=np.float32)

# ─── Device classification ────────────────────────────────────────
# Substrings (case-insensitive) that identify built-in laptop speakers
BUILTIN_KEYWORDS = ["speakers (realtek", "speakers (high definition"]
# Substrings that identify virtual / software devices to skip
VIRTUAL_KEYWORDS = ["virtual"]


def classify(name):
    """Classify an audio device as 'builtin', 'virtual', or 'external'."""
    low = name.lower()
    if any(kw in low for kw in VIRTUAL_KEYWORDS):
        return "virtual"
    if any(kw in low for kw in BUILTIN_KEYWORDS):
        return "builtin"
    return "external"


# ─── Player thread ────────────────────────────────────────────────
def player_worker(speaker, q, name, error_event):
    """Pull audio chunks from the queue and play them on one device."""
    try:
        with speaker.player(samplerate=RATE, channels=CHANNELS,
                            blocksize=BLOCK) as out:
            while True:
                try:
                    chunk = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                out.play(chunk)
    except Exception as e:
        print(f"\n  [!] Player '{name}' lost: {e}")
        error_event.set()


def device_snapshot():
    """Return a hashable snapshot of device IDs + the current default ID."""
    all_spk = sc.all_speakers()
    default = sc.default_speaker()
    device_ids = tuple(sorted(s.id for s in all_spk))
    return device_ids, default.id


# ─── Main loop ────────────────────────────────────────────────────
def mirror_session():
    """
    Run one mirroring session.
    Returns True  if it should restart (devices changed).
    Returns False if the user pressed Ctrl+C (should exit).
    """
    source = sc.default_speaker()
    source_id = source.id
    all_spk = sc.all_speakers()

    # ── Print device map ──
    print(f"\n  Source (Windows default): {source.name}")
    print(f"  Detected devices:")
    for s in all_spk:
        kind = classify(s.name)
        tag = {"builtin": "LAPTOP", "virtual": "VIRTUAL", "external": "EXTERNAL"}[kind]
        is_default = " *DEFAULT*" if s.id == source_id else ""
        print(f"    [{tag:>8}]{is_default}  {s.name}")

    # ── Pick targets ──
    # Mirror to all non-builtin devices that aren't the source.
    # With --virtual flag, also include virtual devices.
    include_virtual = "--virtual" in sys.argv
    allowed_kinds = {"external"}
    if include_virtual:
        allowed_kinds.add("virtual")

    targets = [s for s in all_spk
               if classify(s.name) in allowed_kinds and s.id != source_id]

    if not targets:
        candidates = [s for s in all_spk if classify(s.name) in allowed_kinds]
        if not candidates:
            print("\n  No target devices detected.")
            print("  Connect headphones, earbuds, or a Bluetooth device and re-run.")
            if not include_virtual:
                print("  TIP: Use --virtual flag to also mirror to virtual devices.")
        else:
            print(f"\n  '{source.name}' is the only target device (already playing).")
            print("  Connect a second device to mirror, or just enjoy :)")
        return False

    # ── Loopback capture from source ──
    # Try by ID first (reliable), fall back to name.
    mic = sc.get_microphone(id=str(source_id), include_loopback=True)
    if mic is None:
        mic = sc.get_microphone(id=str(source.name), include_loopback=True)
    if mic is None:
        print(f"\n  [!] Could not open loopback capture for '{source.name}'.")
        return False

    # ── Start player threads ──
    error_event = threading.Event()
    queues = []
    target_names = []
    for spk in targets:
        q = queue.Queue(maxsize=MAX_QUEUE)
        threading.Thread(
            target=player_worker,
            args=(spk, q, spk.name, error_event),
            daemon=True,
        ).start()
        queues.append(q)
        target_names.append(spk.name)

    time.sleep(0.3)

    source_is_builtin = classify(source.name) == "builtin"
    print(f"\n  [ACTIVE] Mirroring to {len(targets)} device(s):")
    for name in target_names:
        print(f"    -> {name}")

    if source_is_builtin:
        print("\n  WARNING: Your Windows default output is your laptop speakers.")
        print("           Audio WILL play from laptop speakers (Windows controls this).")
        print("           To fix: change your Windows default to an external device,")
        print("           then restart this script.")

    print("\n  Press Ctrl+C to stop.\n")

    # ── Capture → distribute loop ──
    snapshot = device_snapshot()
    last_device_check = time.time()
    last_meter = 0

    try:
        with mic.recorder(samplerate=RATE, channels=CHANNELS,
                          blocksize=BLOCK) as rec:
            while True:
                now = time.time()

                # Check for device changes (connect/disconnect/default switch)
                if now - last_device_check > POLL_INTERVAL:
                    last_device_check = now
                    current = device_snapshot()
                    if current != snapshot:
                        print("\n\n  [!] Audio devices or default changed. Restarting...")
                        return True

                # Check if a player thread crashed
                if error_event.is_set():
                    print("\n  [!] A player device was lost. Restarting...")
                    return True

                data = rec.record(numframes=BLOCK)
                if data.dtype != np.float32:
                    data = data.astype(np.float32)
                np.clip(data, -1.0, 1.0, out=data)

                for q in queues:
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        q.put_nowait(data)
                    except queue.Full:
                        pass

                # Volume meter (~5 Hz update)
                if now - last_meter > 0.2:
                    last_meter = now
                    peak = float(np.max(np.abs(data)))
                    bars = int(peak * 30)
                    meter = "#" * min(bars, 30) + "-" * (30 - min(bars, 30))
                    pct = min(int(peak * 100), 100)
                    sys.stdout.write(f"\r  Volume: [{meter}] {pct:3d}%  ")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\n  Stopped by user.")
        return False
    except RuntimeError as e:
        print(f"\n\n  [!] Audio error: {e}")
        print("  Device was likely disconnected. Restarting...")
        return True
    finally:
        for q in queues:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        time.sleep(0.1)


def main():
    print("=" * 52)
    print("  Audio Splitter - Automatic Mode")
    print("=" * 52)

    while True:
        should_restart = mirror_session()
        if not should_restart:
            break
        print("  Reconnecting in 2 seconds...\n")
        time.sleep(2)

    print("  Bye!")


if __name__ == "__main__":
    main()