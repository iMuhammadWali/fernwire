"""Demo mode: fake devices and a fake engine, so the window can be developed and screenshotted
without any Bluetooth hardware. Used by ``python -m audio_splitter.ui --demo``."""

import math
import time

from ..devices import BUILTIN, EXTERNAL, DeviceInfo
from ..settings import Settings


def demo_devices(empty: bool = False):
    devs = [DeviceInfo("realtek", "Speakers (Realtek(R) Audio)", BUILTIN, False)]
    if not empty:
        devs += [
            DeviceInfo("jbl", "JBL TUNE570BT", EXTERNAL, True),
            DeviceInfo("soundcore", "Soundcore Liberty 4 NC", EXTERNAL, False),
            DeviceInfo("soundpeats", "SoundPeats T3 Pro", EXTERNAL, False),
        ]
    else:
        devs = [DeviceInfo("realtek", "Speakers (Realtek(R) Audio)", BUILTIN, True)]
    return devs


class MemorySettings(Settings):
    """Settings that never touch the disk."""

    def __init__(self, empty: bool = False):
        self.path = None
        self.theme = "auto"
        self.devices = {}
        if not empty:
            self.devices = {
                "Soundcore Liberty 4 NC": {"enabled": True, "delay": 0},
                "SoundPeats T3 Pro": {"enabled": True, "delay": 40},
                "AirPods Pro": {"enabled": False, "delay": 0},
            }

    def load(self) -> None:
        pass

    def save(self) -> None:
        pass


class FakeEngine:
    """Same interface as audio_splitter.engine.Engine, with a made-up signal."""

    def __init__(self, on_event=None, **_):
        self._targets = {}
        self.running = False

    def start(self, source_id, targets):
        self.running = True
        self._targets = dict(targets)

    def stop(self):
        self.running = False
        self._targets = {}

    def set_targets(self, targets):
        self._targets = dict(targets)

    def set_delay(self, device_id, ms):
        self._targets[device_id] = ms

    def levels(self):
        t = time.monotonic()
        return {did: max(0.0, min(1.0, 0.45 + 0.22 * math.sin(t * 2.4 + i * 1.3) + 0.12 * math.sin(t * 7 + i)))
                for i, did in enumerate(self._targets)}

    def is_target_alive(self, device_id):
        return self.running and device_id in self._targets
