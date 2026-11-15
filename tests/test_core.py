import numpy as np

from fernwire.delay import DelayLine
from fernwire.devices import BUILTIN, EXTERNAL, VIRTUAL, DeviceInfo, choose_targets, classify

RATE, CH = 48000, 2


def chunk(values):
    """Mono signal repeated on both channels, as float32 (frames, 2)."""
    a = np.asarray(values, dtype=np.float32)
    return np.stack([a, a], axis=1)


# ── classification ────────────────────────────────────────────────
def test_classify():
    assert classify("Speakers (Realtek(R) Audio)") == BUILTIN
    assert classify("Speakers (High Definition Audio Device)") == BUILTIN
    assert classify("Virtual Speakers (Virtual Speakers for AudioRelay)") == VIRTUAL
    assert classify("Headphones (JBL TUNE570BT)") == EXTERNAL
    assert classify("Soundcore Liberty 4 NC") == EXTERNAL


def _devs():
    return [
        DeviceInfo("a", "Speakers (Realtek(R) Audio)", BUILTIN, False),
        DeviceInfo("b", "Headphones (JBL)", EXTERNAL, True),
        DeviceInfo("c", "Soundcore", EXTERNAL, False),
        DeviceInfo("v", "Virtual Speakers", VIRTUAL, False),
    ]


def test_targets_skip_source_builtin_and_virtual():
    assert [d.id for d in choose_targets(_devs(), "b")] == ["c"]


def test_targets_can_include_virtual():
    assert [d.id for d in choose_targets(_devs(), "b", include_virtual=True)] == ["c", "v"]


# ── delay line ────────────────────────────────────────────────────
def test_zero_delay_is_passthrough():
    d = DelayLine(CH, RATE)
    x = chunk(np.arange(10))
    assert np.array_equal(d.process(x), x)


def test_delay_shifts_audio_by_exact_frames():
    d = DelayLine(CH, RATE)
    d.set_delay_ms(10)                       # 480 frames
    n = 480
    assert d.delay_frames == n
    impulse = chunk([1.0] + [0.0] * (n - 1))
    first = d.process(impulse)               # silence while the impulse waits
    assert not first.any()
    second = d.process(chunk(np.zeros(n)))   # impulse comes out exactly n frames later
    assert second[0, 0] == 1.0 and not second[1:].any()


def test_output_length_always_matches_input():
    d = DelayLine(CH, RATE)
    d.set_delay_ms(37)
    for size in (480, 480, 100, 960):
        assert len(d.process(chunk(np.zeros(size)))) == size


def test_changing_delay_clamps_and_keeps_length():
    d = DelayLine(CH, RATE, max_ms=100)
    d.set_delay_ms(1000)
    assert d.delay_frames == int(RATE * 0.1)     # clamped to the maximum
    d.set_delay_ms(20)
    assert d.delay_frames == 960
    d.set_delay_ms(-5)
    assert d.delay_frames == 0
    assert len(d.process(chunk(np.zeros(480)))) == 480


def test_delay_preserves_signal_content():
    d = DelayLine(CH, RATE)
    d.set_delay_ms(5)                        # 240 frames
    ramp = np.arange(1, 961, dtype=np.float32)
    out = np.concatenate([d.process(chunk(ramp[i:i + 480])) for i in (0, 480)])
    assert np.array_equal(out[:240, 0], np.zeros(240, dtype=np.float32))
    assert np.array_equal(out[240:, 0], ramp[:720])
