"""Selection and plotting verification using synthetic recording bytes."""
from pathlib import Path
import os
import subprocess
import sys

import numpy as np
import pytest

from fieldfox_recording import FieldFoxRecording, RecordingError
from fieldfox_recording.spectrogram import load_section, plot_section
from .fixtures import TICKS, make_session, state_bytes, trace_bytes


def test_section_crops_sweeps_and_frequency_without_reading_earlier_partition(tmp_path, monkeypatch):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", split=True))
    earlier = rec.trace_files[0]
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != earlier, "Viewer read a partition outside the selected section"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    section = load_section(rec, start_sweep=1, stop_sweep=3, freq_min_hz=999e6, freq_max_hz=1e9)
    np.testing.assert_array_equal(section.sweep_indices, [1, 2])
    np.testing.assert_array_equal(section.elapsed_s, [0, 1])
    np.testing.assert_array_equal(section.frequency_hz, [999e6, 1e9])
    np.testing.assert_array_equal(section.power_dbm, [[-70, -60], [-70, -60]])
    assert section.first_timestamp == "2024-01-01T00:00:01.1234567"


def test_max_rows_and_step_preserve_original_samples(tmp_path):
    root = make_session(tmp_path / "session")
    trace_file = root / "dTRC00000" / "00000000.TRC"
    trace_file.write_bytes(b"".join(trace_bytes(trace_id=i, ticks=TICKS+i*10_000_000,
                          values=(-70+i, -60+i, -50+i)) for i in range(10)))
    section = load_section(FieldFoxRecording.open(root), step=2, max_sweeps=3)
    np.testing.assert_array_equal(section.sweep_indices, [0, 4, 8])
    np.testing.assert_array_equal(section.elapsed_s, [0, 4, 8])
    np.testing.assert_array_equal(section.power_dbm[:, 0], [-70, -66, -62])
    assert section.effective_step == 4


def test_plot_memory_guard_runs_before_matrix_allocation(tmp_path, monkeypatch):
    import fieldfox_recording.spectrogram as module
    monkeypatch.setattr(module, "MAX_PLOT_CELLS", 4)
    rec = FieldFoxRecording.open(make_session(tmp_path / "session"))
    with pytest.raises(RecordingError, match="memory limit"):
        load_section(rec)


def test_trace_slot_selection(tmp_path):
    root = make_session(tmp_path / "session", traces=2)
    (root / "dTRC00000" / "00000000.TRC").write_bytes(b"".join(
        trace_bytes(trace_id=i, values=(-70, -60, -50, -40, -30, -20), ticks=TICKS+i*10_000_000)
        for i in range(3)))
    section = load_section(FieldFoxRecording.open(root), trace_slot=1)
    np.testing.assert_array_equal(section.power_dbm[0], [-40, -30, -20])
    assert section.trace_slot == 1


def test_section_can_start_after_axis_change(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", changed_axis=True))
    with pytest.raises(RecordingError, match="axis changes"):
        load_section(rec)
    section = load_section(rec, start_sweep=1)
    assert section.frequency_hz[1] == 2e9


@pytest.mark.parametrize("options", [
    {"start_sweep": -1}, {"stop_sweep": 4}, {"start_sweep": 2, "stop_sweep": 1},
    {"step": 0}, {"max_sweeps": 1}, {"trace_slot": 1}, {"stop_sweep": 1},
    {"freq_min_hz": 2e9}, {"freq_min_hz": 2e9, "freq_max_hz": 1e9}, {"freq_min_hz": float("nan")},
])
def test_invalid_selection_is_clear(tmp_path, options):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session"))
    with pytest.raises(RecordingError):
        load_section(rec, **options)


def test_zero_span_is_not_presented_as_frequency_spectrogram(tmp_path):
    root = make_session(tmp_path / "session")
    (root / "dSTA00000" / "00000000.STA").write_bytes(state_bytes(span=0))
    with pytest.raises(RecordingError, match="Zero-span"):
        load_section(FieldFoxRecording.open(root))


def test_repeated_timestamps_are_not_given_fake_time_spacing(tmp_path):
    root = make_session(tmp_path / "session")
    (root / "dTRC00000" / "00000000.TRC").write_bytes(b"".join(trace_bytes(trace_id=i) for i in range(3)))
    with pytest.raises(RecordingError, match="strictly increasing"):
        load_section(FieldFoxRecording.open(root))


def test_partial_seek_checks_selected_trace_id(tmp_path):
    root = make_session(tmp_path / "session")
    (root / "dTRC00000" / "00000000.TRC").write_bytes(trace_bytes() + trace_bytes(trace_id=9) + trace_bytes(trace_id=2))
    rec = FieldFoxRecording.open(root)
    with pytest.raises(RecordingError, match="expected trace 1"):
        list(rec.iter_sweeps(1, 3))


def test_iter_sweeps_steps_across_partition_boundary(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", split=True))
    assert [s.trace_id for s in rec.iter_sweeps(0, 3, 2)] == [0, 2]
    assert list(rec.iter_sweeps(3, 3)) == []
    with pytest.raises(RecordingError):
        list(rec.iter_sweeps(0, 4))


def test_plot_labels_and_values(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    section = load_section(FieldFoxRecording.open(make_session(tmp_path / "session")))
    fig, ax = plot_section(section, vmin=-90, vmax=-20)
    try:
        assert ax.get_xlabel() == "Frequency (MHz)"
        assert "Elapsed time" in ax.get_ylabel()
        np.testing.assert_array_equal(ax.collections[0].get_array().reshape(section.power_dbm.shape), section.power_dbm)
        assert fig.axes[1].get_ylabel() == "Recorded power (dBm)"
    finally:
        plt.close(fig)


def test_plot_cli_saves_png_and_protects_inputs(tmp_path):
    pytest.importorskip("matplotlib")
    root = make_session(tmp_path / "session")
    output = tmp_path / "section.png"
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    command = [sys.executable, "-m", "fieldfox_recording", "plot", str(root), "--start-sweep", "1",
               "--stop-sweep", "3", "--freq-min-hz", "999e6", "--freq-max-hz", "1e9", "--output"]
    result = subprocess.run(command + [str(output)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "2 sweeps x 2 frequency bins" in result.stdout
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    blocked = subprocess.run(command + [str(root / "inside.png")], env=env, capture_output=True, text=True)
    assert blocked.returncode == 2
    assert "outside the original" in blocked.stderr
    assert not (root / "inside.png").exists()
