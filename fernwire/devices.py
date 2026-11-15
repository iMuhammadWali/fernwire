"""Finding audio output devices and deciding which ones are targets."""

import warnings
from dataclasses import dataclass

warnings.filterwarnings("ignore")

import soundcard as sc  # noqa: E402  (after the warnings filter on purpose)

# Substrings (case-insensitive) that identify built-in laptop speakers.
BUILTIN_KEYWORDS = ["speakers (realtek", "speakers (high definition"]
# Substrings that identify virtual / software devices.
VIRTUAL_KEYWORDS = ["virtual"]

BUILTIN, VIRTUAL, EXTERNAL = "builtin", "virtual", "external"


@dataclass(frozen=True)
class DeviceInfo:
    id: str
    name: str
    kind: str          # BUILTIN, VIRTUAL or EXTERNAL
    is_default: bool   # the Windows default output


def classify(name: str) -> str:
    """Classify an output device by its name."""
    low = name.lower()
    if any(kw in low for kw in VIRTUAL_KEYWORDS):
        return VIRTUAL
    if any(kw in low for kw in BUILTIN_KEYWORDS):
        return BUILTIN
    return EXTERNAL


def list_devices() -> list[DeviceInfo]:
    """All active output devices right now."""
    try:
        default_id = str(sc.default_speaker().id)
    except Exception:  # noqa: BLE001
        default_id = None
    return [
        DeviceInfo(id=str(s.id), name=s.name, kind=classify(s.name), is_default=str(s.id) == default_id)
        for s in sc.all_speakers()
    ]


def snapshot():
    """Hashable summary (device ids, default id) used to notice connects, disconnects and default changes."""
    devices = list_devices()
    default = next((d.id for d in devices if d.is_default), None)
    return tuple(sorted(d.id for d in devices)), default


def choose_targets(devices, source_id, include_virtual=False) -> list[DeviceInfo]:
    """Devices to mirror to: external (optionally virtual), never the source, never the laptop speakers."""
    allowed = {EXTERNAL} | ({VIRTUAL} if include_virtual else set())
    return [d for d in devices if d.kind in allowed and d.id != source_id]


def find_speaker(device_id: str):
    return sc.get_speaker(device_id)


def open_loopback(device_id: str, name: str = ""):
    """Microphone object that records what a speaker is playing. Tries id first, then name."""
    mic = sc.get_microphone(id=str(device_id), include_loopback=True)
    if mic is None and name:
        mic = sc.get_microphone(id=str(name), include_loopback=True)
    if mic is None:
        raise RuntimeError("Could not open loopback capture for this device")
    return mic
