"""Per-device delay: hold audio back by N milliseconds so a fast device lines up with a slow one."""

import threading

import numpy as np


class DelayLine:
    """FIFO that delays a stream of audio chunks by an adjustable number of frames.

    Every call to ``process`` returns exactly as many frames as it was given, so it can sit
    between a capture loop and a player without changing block sizes.
    """

    def __init__(self, channels: int, rate: int, max_ms: int = 1000):
        self._channels = channels
        self._rate = rate
        self._max_frames = int(rate * max_ms / 1000)
        self._buf = np.zeros((0, channels), dtype=np.float32)
        self._lock = threading.Lock()

    @property
    def delay_frames(self) -> int:
        with self._lock:
            return len(self._buf)

    def set_delay_ms(self, ms: float) -> None:
        """Change the delay. Growing it inserts silence; shrinking it skips ahead."""
        frames = max(0, min(self._max_frames, int(round(self._rate * ms / 1000))))
        with self._lock:
            have = len(self._buf)
            if frames > have:
                pad = np.zeros((frames - have, self._channels), dtype=np.float32)
                self._buf = np.concatenate([pad, self._buf])
            elif frames < have:
                self._buf = self._buf[have - frames:]

    def process(self, chunk: np.ndarray) -> np.ndarray:
        with self._lock:
            if len(self._buf) == 0:
                return chunk
            joined = np.concatenate([self._buf, chunk])
            n = len(chunk)
            self._buf = joined[n:]
            return joined[:n]
