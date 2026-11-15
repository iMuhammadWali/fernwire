"""Window tests, run headless (no screen needed)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fernwire.ui.demo import FakeEngine, MemorySettings, demo_devices  # noqa: E402
from fernwire.ui.tokens import theme  # noqa: E402
from fernwire.ui.widgets import LinkButton  # noqa: E402
from fernwire.ui.window import MainWindow  # noqa: E402

SOUNDCORE, SOUNDPEATS, AIRPODS = "Soundcore Liberty 4 NC", "SoundPeats T3 Pro", "AirPods Pro"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    w = MainWindow(MemorySettings(), list_fn=demo_devices, engine_factory=FakeEngine, monitor_interval=600)
    w.show()
    w.on_devices(demo_devices())
    app.processEvents()
    yield w
    w.close()


def heights(w):
    return [w.src_row.height()] + [w.rows[n].height() for n in (SOUNDCORE, SOUNDPEATS, AIRPODS)]


def test_row_heights_are_fixed_and_never_change_with_state(win, app):
    ready = heights(win)
    assert ready == [71, 83, 83, 83]
    win.toggle_sharing(); app.processEvents()
    assert heights(win) == ready                                   # starting does not resize rows
    win.rows[SOUNDCORE].switch.click(); app.processEvents()
    assert heights(win) == ready                                   # switching a device off does not either
    win.rows[SOUNDCORE].switch.click()
    win.rows[SOUNDPEATS].slider.setValue(0); app.processEvents()   # weight 600 -> 400 on the link
    assert heights(win) == ready
    win.toggle_sharing(); app.processEvents()
    assert heights(win) == ready                                   # stopping does not


def test_link_keeps_its_width_when_emphasis_changes(app):
    link = LinkButton("+40 ms delay")
    link.set_emphasis(False); app.processEvents(); a = (link.width(), link.height())
    link.set_emphasis(True); app.processEvents(); b = (link.width(), link.height())
    assert a == b and link.height() >= 24


def test_keyboard_focus_survives_updates(win, app):
    row = win.rows[SOUNDPEATS]
    row.switch.setFocus(Qt.FocusReason.TabFocusReason)
    row.switch.click(); app.processEvents()
    win.refresh(); win.on_devices(demo_devices()); app.processEvents()
    assert win.rows[SOUNDPEATS] is row                 # same widget, updated in place
    assert row.switch.hasFocus()


def test_trunk_passes_by_an_off_device_and_stops_at_last_active(win, app):
    win.toggle_sharing()
    win.rows[SOUNDCORE].switch.click()                 # first device off, second still on
    win.refresh(snap=True); app.processEvents()
    lit, dim = theme.color("accent"), theme.color("rail")
    off, on, absent = win.rows[SOUNDCORE], win.rows[SOUNDPEATS], win.rows[AIRPODS]
    assert win.src_row._cols["down"] == lit            # trunk leaves the source lit
    assert off._cols["up"] == lit and off._cols["down"] == lit   # ...passes the off device...
    assert off._cols["elbow"] == dim                              # ...whose own branch stays dim
    assert on._cols["up"] == lit and on._cols["elbow"] == lit
    assert on._cols["down"] == dim                     # nothing active below the last active device
    assert absent._cols["up"] == dim


def test_lost_device_is_dashed_and_can_still_be_switched_off(win, app):
    win.toggle_sharing()
    win.lost.add(SOUNDPEATS); win.refresh(); app.processEvents()
    row = win.rows[SOUNDPEATS]
    assert row.lost and row.dashed and not row.is_on
    assert row.switch.isEnabled()
    assert "reconnecting" in win.status.text()
    win.engineEvent.emit("target_ready", {"id": win.known_ids[SOUNDPEATS]}); app.processEvents()
    assert not row.lost and not row.dashed


def test_absent_remembered_device_is_disabled_with_a_reason(win):
    row = win.rows[AIRPODS]
    assert not row.present and not row.switch.isEnabled()
    assert "Not connected" in row.sub.text()


def test_empty_state(app):
    w = MainWindow(MemorySettings(empty=True), list_fn=lambda: demo_devices(True), engine_factory=FakeEngine,
                   monitor_interval=600)
    w.show(); w.on_devices(demo_devices(True)); app.processEvents()
    assert not w.empty.isHidden() and w.src_row.last
    assert not w.go.isEnabled()
    w.close()


def test_both_themes_apply(win, app):
    for name in ("light", "dark"):
        theme.set(name); app.processEvents()
        assert theme.name == name and name in ("light", "dark")


def test_switching_a_device_off_while_sharing_reaches_the_engine(win, app):
    win.toggle_sharing()
    soundcore_id = win.known_ids[SOUNDCORE]
    assert soundcore_id in win.engine._targets
    win.rows[SOUNDCORE].switch.click(); app.processEvents()
    assert soundcore_id not in win.engine._targets          # engine stopped playing to it
    win.rows[SOUNDCORE].switch.click(); app.processEvents()
    assert soundcore_id in win.engine._targets              # ...and resumes when switched back on


def test_delay_changes_reach_the_engine_while_sharing(win, app):
    win.toggle_sharing()
    win.rows[SOUNDPEATS].slider.setValue(30); app.processEvents()   # 150 ms
    assert win.engine._targets[win.known_ids[SOUNDPEATS]] == 150


# ── icon ──────────────────────────────────────────────────────────
def test_icon_draws_at_every_size_and_lit_differs_from_dim(app):
    from fernwire.ui.icon import SIZES, app_icon, draw_icon
    for size in SIZES:
        img = draw_icon(size)
        assert img.width() == size and img.height() == size and not img.isNull()
    assert draw_icon(32, True) != draw_icon(32, False)
    assert not app_icon().isNull() and not app_icon(False).isNull()


PNG_SIGNATURE = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])


@pytest.mark.parametrize("name", ["icon.ico", "icon_light.ico"])
def test_ico_file_is_valid_and_has_png_frames(name):
    import struct
    from pathlib import Path
    data = (Path(__file__).resolve().parent.parent / "fernwire" / "assets" / name).read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1) and count == 7
    for i in range(count):
        _w, _h, _c, _r, planes, bits, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i: 22 + 16 * i])
        assert planes == 1 and bits == 32
        assert data[offset: offset + 8] == PNG_SIGNATURE and offset + size <= len(data)


def test_light_and_dark_icons_differ_and_window_icon_follows_theme(win, app):
    from fernwire.ui.icon import draw_icon
    assert draw_icon(48, True, "light") != draw_icon(48, True, "dark")
    theme.set("light"); app.processEvents()
    light_key = win.windowIcon().cacheKey()
    theme.set("dark"); app.processEvents()
    assert win.windowIcon().cacheKey() != light_key
