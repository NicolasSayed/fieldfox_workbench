import json
import time

import numpy as np
import pytest

from fieldfox_workbench.playback import RunningHolds
from fieldfox_workbench.traces import Trace, export_traces
from fieldfox_workbench.diagnostics import synthetic_session
from .test_workbench import desktop


VALUES = np.array([[-70, -30, -80], [-20, -90, -65], [-60, -40, -10], [-80, -20, -75]], dtype=np.float32)


def test_forward_hold_includes_intervening_rows_and_uses_only_point_buffers():
    hold = RunningHolds(VALUES)
    hold.update(0); maximum, minimum = hold.update(2)
    np.testing.assert_array_equal(maximum, [-20, -30, -10])
    np.testing.assert_array_equal(minimum, [-70, -90, -80])
    assert np.shares_memory(hold.values, VALUES)
    assert hold.maximum.shape == hold.minimum.shape == (VALUES.shape[1],)


def test_backward_seek_removes_future_peaks_and_reset_reanchors():
    hold = RunningHolds(VALUES); hold.update(3)
    maximum, minimum = hold.update(0)
    np.testing.assert_array_equal(maximum, VALUES[0]); np.testing.assert_array_equal(minimum, VALUES[0])
    hold.update(2); maximum, minimum = hold.reset(2)
    np.testing.assert_array_equal(maximum, VALUES[2]); np.testing.assert_array_equal(minimum, VALUES[2])
    maximum, minimum = hold.update(3)
    np.testing.assert_array_equal(maximum, np.max(VALUES[2:4], axis=0))
    np.testing.assert_array_equal(minimum, np.min(VALUES[2:4], axis=0))
    hold.update(1)
    assert hold.start_row == 1
    np.testing.assert_array_equal(hold.maximum, VALUES[1]); np.testing.assert_array_equal(hold.minimum, VALUES[1])


@pytest.mark.parametrize("data", [np.empty((0, 3)), np.empty((3, 0)), np.arange(3)])
def test_invalid_hold_dimensions(data):
    with pytest.raises(ValueError): RunningHolds(data)


def test_invalid_rows_and_repeated_rows():
    hold = RunningHolds(VALUES)
    maximum, minimum = hold.update(1)
    hold.update(1)
    np.testing.assert_array_equal(hold.maximum, maximum); np.testing.assert_array_equal(hold.minimum, minimum)
    with pytest.raises(ValueError): hold.update(-1)
    with pytest.raises(ValueError): hold.reset(4)


def load_section(app, tmp_path, finish):
    app.open_path(synthetic_session(tmp_path / "session")); finish()
    # Nonmonotonic rows make skipped peaks and future-data leakage observable.
    app.viewer.section.power_dbm[:] = VALUES[:3]
    app.playback.loaded(app.viewer.rec, app.viewer.section)


def by_name(app, name):
    return next(t for t in app.plots.traces if t.name == name)


def test_both_holds_update_during_playback_and_pause(desktop, tmp_path):
    app, errors, finish = desktop; load_section(app, tmp_path, finish)
    app.playback.max_hold.set(True); app.playback.min_hold.set(True)
    np.testing.assert_array_equal(by_name(app, "Max hold").y, VALUES[0])
    np.testing.assert_array_equal(by_name(app, "Min hold").y, VALUES[0])
    app.playback.delay.set("100"); app.playback.toggle()
    assert app.playback.playing  # Enabling either hold never stops playback.
    app.playback.min_hold.set(False); app.playback.min_hold.set(True)
    assert app.playback.playing
    deadline = time.monotonic()+3
    while app.playback.playing and time.monotonic() < deadline:
        app.root.update(); time.sleep(.01)
    assert not app.playback.playing and app.playback.index.get() == 2
    np.testing.assert_array_equal(by_name(app, "Max hold").y, VALUES[:3].max(axis=0))
    np.testing.assert_array_equal(by_name(app, "Min hold").y, VALUES[:3].min(axis=0))
    assert [t.name for t in app.plots.playback_traces] == ["Sweep 2", "Max hold", "Min hold"]
    assert not errors


def test_hold_seek_reset_toggle_and_new_section_preserve_overlays(desktop, tmp_path):
    app, errors, finish = desktop; load_section(app, tmp_path, finish)
    overlay = Trace("Reference", app.viewer.section.frequency_hz, [-50, -50, -50], "Frequency (Hz)", "Power (dBm)")
    app.plots.add_trace(overlay)
    app.playback.max_hold.set(True); app.playback.min_hold.set(True)
    app.playback.index.set(2)
    np.testing.assert_array_equal(by_name(app, "Max hold").y, VALUES[:3].max(axis=0))
    app.playback.index.set(0)
    np.testing.assert_array_equal(by_name(app, "Max hold").y, VALUES[0])
    app.playback.index.set(1); app.playback.reset_holds(); app.playback.index.set(2)
    np.testing.assert_array_equal(by_name(app, "Max hold").y, VALUES[1:3].max(axis=0))
    np.testing.assert_array_equal(by_name(app, "Min hold").y, VALUES[1:3].min(axis=0))
    assert by_name(app, "Max hold").metadata["hold_start_sweep"] == 1
    app.playback.max_hold.set(False)
    assert "Max hold" not in [t.name for t in app.plots.traces]
    assert by_name(app, "Reference") is overlay and by_name(app, "Min hold")
    app.playback.loaded(app.viewer.rec, app.viewer.section)
    assert app.playback.holds.start_row == 0
    np.testing.assert_array_equal(by_name(app, "Min hold").y, VALUES[0])
    assert not errors


def test_exported_hold_is_a_snapshot_and_contains_interval(desktop, tmp_path):
    from scipy.io import loadmat
    app, errors, finish = desktop; load_section(app, tmp_path, finish)
    app.playback.max_hold.set(True); app.playback.min_hold.set(True)
    app.playback.index.set(1)
    saved_traces = list(app.plots.traces)
    output = tmp_path / "holds.mat"; export_traces(saved_traces, output)
    app.playback.index.set(2)
    np.testing.assert_array_equal(saved_traces[1].y, VALUES[:2].max(axis=0))
    np.testing.assert_array_equal(saved_traces[2].y, VALUES[:2].min(axis=0))
    data = loadmat(output, simplify_cells=True)
    np.testing.assert_array_equal(data["trace_2"]["y"], VALUES[:2].max(axis=0))
    meta = json.loads(data["trace_2"]["metadata_json"])
    assert meta["hold_start_sweep"] == 0 and meta["hold_stop_sweep"] == 1
    assert not errors
