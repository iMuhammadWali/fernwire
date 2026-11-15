"""The audio engine: capture one device's output and play it on several others.

No printing and no UI here. Callers get things done through methods and hear about changes
through the ``on_event(kind, **data)`` callback, which is called from background threads.

Events:
  devices_changed            a device appeared, disappeared, or the Windows default moved
  target_ready   id          a target started playing
  target_lost    id, error   a target dropped out; the engine keeps retrying it
  source_lost    error       capture failed; the engine keeps retrying it
  source_ready               capture (re)started
"""

import queue
import threading

import numpy as np

from .delay import DelayLine
from .devices import find_speaker, list_devices, open_loopback, snapshot

RATE = 48000
CHANNELS = 2
BLOCK = 480          # ~10 ms per chunk at 48 kHz
MAX_QUEUE = 2        # keeps mirror latency around ~20 ms
POLL_INTERVAL = 3.0  # seconds between device-change checks


class _Target:
    def __init__(self, device_id: str, name: str, delay_ms: int):
        self.id = device_id
        self.name = name
        self.queue: "queue.Queue" = queue.Queue(maxsize=MAX_QUEUE)
        self.delay = DelayLine(CHANNELS, RATE)
        self.delay.set_delay_ms(delay_ms)
        self.stop = threading.Event()
        self.thread = None
        self.alive = False
        self.level = 0.0


def _offer(q: "queue.Queue", chunk) -> None:
    """Put a chunk in a queue, dropping the oldest one if the player is behind."""
    if q.full():
        try:
            q.get_nowait()
        except queue.Empty:
            pass
    try:
        q.put_nowait(chunk)
    except queue.Full:
        pass


class Engine:
    def __init__(self, on_event=None, poll_interval: float = POLL_INTERVAL):
        self._emit = on_event or (lambda kind, **data: None)
        self._poll = poll_interval
        self._lock = threading.RLock()
        self._targets: dict[str, _Target] = {}
        self._source_id = None
        self._source_name = ""
        self._stop = threading.Event()
        self._capture = None
        self._capture_alive = False
        self._watcher = None
        self._running = False

    # ── public API ────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return self._running

    def start(self, source_id: str, targets: dict) -> None:
        """Start mirroring. ``targets`` maps device id -> delay in ms."""
        if self._running:
            raise RuntimeError("Engine is already running")
        names = {d.id: d.name for d in list_devices()}
        with self._lock:
            self._source_id = source_id
            self._source_name = names.get(source_id, "")
            self._stop = threading.Event()
            self._targets = {}
            self._running = True
        self._spawn_capture()
        self.set_targets(targets)
        self._watcher = threading.Thread(target=self._watch_loop, args=(self._stop,), daemon=True)
        self._watcher.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._stop.set()
        with self._lock:
            targets = list(self._targets.values())
            self._targets = {}
            self._running = False
        for t in targets:
            self._halt(t)
        for th in (self._capture, self._watcher):
            if th is not None and th.is_alive():
                th.join(timeout=2)
        for t in targets:
            if t.thread is not None and t.thread.is_alive():
                t.thread.join(timeout=2)

    def set_targets(self, targets: dict) -> None:
        """Make the running set of targets match ``targets`` (id -> delay ms)."""
        names = {d.id: d.name for d in list_devices()}
        to_halt = []
        to_spawn = []
        with self._lock:
            if not self._running:
                return
            for did in list(self._targets):
                if did not in targets:
                    to_halt.append(self._targets.pop(did))
            for did, ms in targets.items():
                if did in self._targets:
                    self._targets[did].delay.set_delay_ms(ms)
                else:
                    t = _Target(did, names.get(did, ""), ms)
                    self._targets[did] = t
                    to_spawn.append(t)
        for t in to_halt:
            self._halt(t)
        for t in to_spawn:
            self._spawn_player(t)

    def set_delay(self, device_id: str, ms: int) -> None:
        with self._lock:
            t = self._targets.get(device_id)
        if t is not None:
            t.delay.set_delay_ms(ms)

    def levels(self) -> dict:
        """Latest peak (0..1) per target."""
        with self._lock:
            return {did: t.level for did, t in self._targets.items()}

    def is_target_alive(self, device_id: str) -> bool:
        with self._lock:
            t = self._targets.get(device_id)
        return bool(t and t.alive)

    # ── internals ─────────────────────────────────────────────────
    def _halt(self, t: _Target) -> None:
        t.stop.set()
        try:
            t.queue.put_nowait(None)
        except queue.Full:
            pass

    def _spawn_capture(self) -> None:
        self._capture = threading.Thread(target=self._capture_loop, args=(self._stop,), daemon=True)
        self._capture.start()

    def _spawn_player(self, t: _Target) -> None:
        t.stop.clear()
        t.thread = threading.Thread(target=self._player_loop, args=(t,), daemon=True)
        t.thread.start()

    def _capture_loop(self, stop: threading.Event) -> None:
        try:
            mic = open_loopback(self._source_id, self._source_name)
            with mic.recorder(samplerate=RATE, channels=CHANNELS, blocksize=BLOCK) as rec:
                self._capture_alive = True
                self._emit("source_ready")
                while not stop.is_set():
                    data = rec.record(numframes=BLOCK)
                    if data.dtype != np.float32:
                        data = data.astype(np.float32)
                    np.clip(data, -1.0, 1.0, out=data)
                    with self._lock:
                        targets = list(self._targets.values())
                    for t in targets:
                        _offer(t.queue, data)
        except Exception as e:  # noqa: BLE001 - any audio failure means the source is gone
            if not stop.is_set():
                self._emit("source_lost", error=str(e))
        finally:
            self._capture_alive = False

    def _player_loop(self, t: _Target) -> None:
        try:
            speaker = find_speaker(t.id)
            with speaker.player(samplerate=RATE, channels=CHANNELS, blocksize=BLOCK) as out:
                t.alive = True
                self._emit("target_ready", id=t.id)
                while not t.stop.is_set():
                    try:
                        chunk = t.queue.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if chunk is None:
                        break
                    t.level = float(np.max(np.abs(chunk)))
                    out.play(t.delay.process(chunk))
        except Exception as e:  # noqa: BLE001
            if not t.stop.is_set():
                self._emit("target_lost", id=t.id, error=str(e))
        finally:
            t.alive = False
            t.level = 0.0

    def _watch_loop(self, stop: threading.Event) -> None:
        def safe_snapshot():
            try:
                return snapshot()
            except Exception:  # noqa: BLE001
                return None

        last = safe_snapshot()
        while not stop.wait(self._poll):
            cur = safe_snapshot()
            if cur is None:
                continue
            if cur != last:
                last = cur
                self._emit("devices_changed")
            present = set(cur[0])
            with self._lock:
                targets = list(self._targets.values())
                source = self._source_id
            for t in targets:
                dead = not t.alive and (t.thread is None or not t.thread.is_alive())
                if dead and not t.stop.is_set() and t.id in present:
                    self._spawn_player(t)
            if source in present and not self._capture_alive and (
                    self._capture is None or not self._capture.is_alive()):
                self._spawn_capture()
