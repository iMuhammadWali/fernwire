"""Small JSON settings file: theme choice and per-device choices."""

import json
import os
from pathlib import Path


def default_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "AudioSplitter" / "settings.json"


class Settings:
    """theme: "auto" | "dark" | "light".  devices: {device name: {"enabled": bool, "delay": ms}}."""

    def __init__(self, path=None):
        self.path = Path(path) if path else default_path()
        self.theme = "auto"
        self.devices: dict = {}
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.get("theme") in ("auto", "dark", "light"):
            self.theme = data["theme"]
        devices = data.get("devices")
        if isinstance(devices, dict):
            for name, info in devices.items():
                if isinstance(info, dict):
                    self.devices[str(name)] = {
                        "enabled": bool(info.get("enabled", True)),
                        "delay": max(0, min(1000, int(info.get("delay", 0)))),
                    }

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"theme": self.theme, "devices": self.devices}, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # settings are a convenience; never crash over them

    def device(self, name: str) -> dict:
        return self.devices.setdefault(name, {"enabled": True, "delay": 0})
