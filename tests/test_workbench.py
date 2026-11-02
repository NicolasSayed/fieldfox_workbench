import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import numpy as np
import pytest

from fieldfox_browser.client import FieldFoxClient, BrowserError
from fieldfox_workbench.instrument import capture_file, read_sa_trace, apply_sa_settings, sweep_action
from fieldfox_workbench.traces import Trace, read_csv, table_trace, export_traces
from fieldfox_workbench.diagnostics import synthetic_session
from .browser.fake_instrument import instrument, ROOT, SESSION


def test_csv_metadata_mapping_limits_and_markers(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text('Instrument,N9917B\nPoints,3\nFrequency (MHz),Power (dBm),Other\n1,-70,-3\n2,-60,-2\n3,-50,-1\nEND\n')
    table = read_csv(path); trace = table_trace(table, x_scale=1e6)
    np.testing.assert_equal(trace.x, [1e6, 2e6, 3e6])
    assert trace.marker(1.9e6) == (1, 2e6, -60.)
    stats = trace.statistics(lower=-65, upper=-55)
    assert stats["limit_result"] == "FAIL" and stats["failed_points"] == 2
    assert trace.statistics()["limit_result"] == "UNTESTED"
    assert trace.statistics(lower=-70, upper=-50)["limit_result"] == "PASS"
    with pytest.raises(ValueError): trace.statistics(lower=1, upper=-1)


@pytest.mark.parametrize("contents", ["nothing\n", "a,b\n1,nan\n2,inf\n", "a,b\n1,2\n", "a,b\n1,2\n3,4\n5,6\n"])
def test_csv_bad_or_bounded_inputs(tmp_path, contents):
    path = tmp_path / "bad.csv"; path.write_text(contents)
    with pytest.raises(ValueError): read_csv(path, max_rows=2)


def test_csv_decimal_exponents_and_tab_header(tmp_path):
    path = tmp_path / "data.tsv"; path.write_text("X\tY\n1D3\t-7d1\n2D3\t-6d1\n")
    np.testing.assert_equal(read_csv(path).values, [[1000, -70], [2000, -60]])


def test_csv_and_mat_overlay_roundtrip_and_no_overwrite(tmp_path):
    from scipy.io import loadmat
    traces = [Trace("same", [1, 2, 3], [-70, -60, -50], "Frequency (Hz)", "dBm"),
              Trace("same", [4, 5, 6], [-40, -30, -20], "Frequency (Hz)", "dBm")]
    output = tmp_path / "overlays.csv"; export_traces(traces, output)
    np.testing.assert_equal(read_csv(output, trace_slot=1).values[:, 1], traces[1].y)
    with pytest.raises(FileExistsError): export_traces(traces, output)
    mat = tmp_path / "data.mat"; export_traces(traces, mat, upper=-55)
    data = loadmat(mat, simplify_cells=True)
    np.testing.assert_equal(data["trace_1"]["y"], traces[0].y)
    assert data["trace_1"]["upper_limit"] == -55
    assert json.loads(data["trace_1"]["metadata_json"]) == {}


def test_decoder_csv_sweep_and_slot(tmp_path):
    from fieldfox_recording import FieldFoxRecording
    path = synthetic_session(tmp_path / "session"); rec = FieldFoxRecording.open(path)
    output = tmp_path / "session.csv"; rec.to_csv(output)
    table = read_csv(output, sweep=2)
    np.testing.assert_equal(table.values[:, 1], [-68, -58, -48])
    assert table.columns == ("frequency_hz", "power_dbm")
    with pytest.raises(ValueError): read_csv(output, sweep=999)


@pytest.mark.parametrize("kind", ["png", "csv"])
def test_capture_creates_fetches_and_removes_only_owned_file(tmp_path, kind):
    with instrument() as fake:
        original = dict(fake.files)
        result = capture_file(FieldFoxClient("127.0.0.1", fake.port, 1), tmp_path / f"capture.{kind}", kind=kind)
        assert result["warning"] is None and fake.files == original
        assert any(command.startswith("MMEM:STOR:") for command in fake.commands)
        assert sum(command.startswith("MMEM:DEL ") for command in fake.commands) == 1
        data = (tmp_path / f"capture.{kind}").read_bytes()
        assert data.startswith(b"\x89PNG") if kind == "png" else b"Power (dBm)" in data


def test_capture_failure_removes_remote_and_partial_local(tmp_path):
    with instrument() as fake:
        original = dict(fake.files); fake.fault = "truncated"
        with pytest.raises(BrowserError): capture_file(FieldFoxClient("127.0.0.1", fake.port, .3), tmp_path / "bad.png")
        assert fake.files == original and not list(tmp_path.iterdir())


def test_capture_cleanup_failure_reports_exact_path(tmp_path):
    with instrument() as fake:
        fake.fail_cleanup = True
        result = capture_file(FieldFoxClient("127.0.0.1", fake.port, .3), tmp_path / "capture.png")
        assert "ffwb_" in result["warning"] and result["remote_path"] in fake.files


def test_capture_missing_and_overwrite(tmp_path):
    with instrument() as fake:
        fake.capture_missing = True
        client = FieldFoxClient("127.0.0.1", fake.port, .3)
        with pytest.raises(BrowserError, match="not created"): capture_file(client, tmp_path / "missing.png")
        output = tmp_path / "keep.png"; output.write_bytes(b"original")
        before = len(fake.commands)
        with pytest.raises(FileExistsError): capture_file(client, output)
        assert len(fake.commands) == before and output.read_bytes() == b"original"


def test_live_trace_real_axis_units_and_format_restore():
    with instrument() as fake:
        trace = read_sa_trace(FieldFoxClient("127.0.0.1", fake.port, 1), slot=2)
        np.testing.assert_equal(trace.x, [999e6, 1e9, 1001e6]); np.testing.assert_equal(trace.y, [-70, -60, -50])
        assert trace.y_label == "Power (dBm)" and fake.data_format == "REAL,32"
        assert not any(command.startswith("INIT") for command in fake.commands)


def test_live_trace_rejects_mode_and_changing_axis_restores_format():
    with instrument() as fake:
        client = FieldFoxClient("127.0.0.1", fake.port, 1)
        fake.mode = "NA"
        with pytest.raises(BrowserError, match="SA mode"): read_sa_trace(client)
        fake.mode = "SA"; fake.axis_changing = True
        with pytest.raises(BrowserError, match="changed"): read_sa_trace(client)
        assert fake.data_format == "REAL,32"


def test_explicit_settings_and_single_sweep_sequence():
    with instrument() as fake:
        client = FieldFoxClient("127.0.0.1", fake.port, 1)
        settings = apply_sa_settings(client, center_hz=2e9, span_hz=1e6, rbw_hz=2000)
        assert settings == {"center_hz": 2e9, "span_hz": 1e6, "rbw_hz": 2000}
        sweep_action(client, "Single")
        assert fake.commands[-4:] == ["INIT:CONT 0", "*OPC?", "INIT:IMM", "*OPC?"]
        fake.settings_error = True
        with pytest.raises(BrowserError, match="Some settings may have changed"):
            apply_sa_settings(client, center_hz=1e9, span_hz=2e6, rbw_hz=1000)
        before = len(fake.commands)
        with pytest.raises(ValueError): apply_sa_settings(client, center_hz=float("nan"), span_hz=1, rbw_hz=1)
        assert len(fake.commands) == before


@pytest.fixture
def desktop(monkeypatch):
    import tkinter as tk
    from tkinter import messagebox
    from fieldfox_workbench.app import Workbench
    try: root = tk.Tk(); root.withdraw()
    except tk.TclError as error:
        if sys.platform == "win32": raise
        pytest.skip(f"No Tk display: {error}")
    errors = []; monkeypatch.setattr(messagebox, "showerror", lambda *args, **kwargs: errors.append(args[1]))
    app = Workbench(root, persist=False)
    def finish():
        deadline = time.monotonic()+8
        while app.jobs.busy and time.monotonic() < deadline:
            root.update(); time.sleep(.01)
        root.update()
        assert not app.jobs.busy and not errors, errors
    yield app, errors, finish
    app.live.stop(); app.playback.stop(); root.destroy()


def test_unified_download_load_playback_and_report(desktop, tmp_path, monkeypatch):
    from tkinter import filedialog, simpledialog
    app, errors, finish = desktop
    source = synthetic_session(tmp_path / "synthetic")
    with instrument() as fake:
        fake.files = {SESSION+"\\"+str(path.relative_to(source)).replace("/", "\\"): path.read_bytes() for path in source.rglob("*") if path.is_file()}
        app.browser.host.set("127.0.0.1"); app.browser.port.set(str(fake.port)); app.browser.timeout.set("1")
        app.browser.path.set(SESSION); app.browser.browse(); finish()
        monkeypatch.setattr(filedialog, "askdirectory", lambda **_: str(tmp_path))
        monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "downloaded")
        app.browser.download_current(); finish()
        # Job completion opens a second, sequential decoding job automatically.
        finish(); assert app.viewer.section.power_dbm.shape == (3, 3)
        app.playback.index.set(2); app.playback.show()
        assert app.plots.traces[0].metadata["timestamp_est"].endswith("-05:00")
        assert "UTC" in app.playback.status.get()
        app.playback.summary("Power mean")
        expected = 10*np.log10(np.mean(10**(np.array([-70., -69., -68.])/10)))
        assert app.plots.traces[-1].y[0] == pytest.approx(expected)
        app.plots.write_report(tmp_path / "report.pdf")
        assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF")
        assert not errors


def test_unified_screen_and_csv_capture_handoff(desktop, tmp_path, monkeypatch):
    from tkinter import filedialog
    app, errors, finish = desktop
    with instrument() as fake:
        app.browser.host.set("127.0.0.1"); app.browser.port.set(str(fake.port)); app.browser.timeout.set("1")
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "screen.png"))
        app.screen.capture("png"); finish()
        assert app.screen.image_path == tmp_path / "screen.png"
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "trace.csv"))
        app.screen.capture("csv"); finish(); finish()
        assert len(app.plots.traces) == 1 and not errors


def test_recovered_session_gui_playback_and_full_export(desktop, tmp_path, monkeypatch):
    from tkinter import filedialog
    from scipy.io import loadmat
    app, errors, finish = desktop
    path = synthetic_session(tmp_path / 'short_session')
    trace = path / 'dTRC00000' / '00000000.TRC'
    content = trace.read_bytes(); trace.write_bytes(content[:2*(len(content)//3)+15])
    assert app.viewer.recover.get()
    app.open_path(path); finish()
    assert app.viewer.section.power_dbm.shape == (3, 3)
    assert 'zero-filled' in app.viewer.status.get()
    assert 'sweep index' in app.viewer.figure.axes[0].get_ylabel()
    app.playback.index.set(2); app.playback.show()
    assert not errors and 'ZERO-FILLED' in app.playback.status.get()
    assert 'unknown' in app.playback.status.get()
    np.testing.assert_array_equal(app.plots.traces[0].y, [0, 0, 0])
    assert app.plots.traces[0].metadata['zero_filled']
    monkeypatch.setattr(filedialog, 'askdirectory', lambda **_: str(tmp_path))
    app.viewer.export_session_mat(); finish()
    data = loadmat(tmp_path / 'short_session_MAT' / 'part_000001.mat')
    assert data['zero_filled'][2, 0] and data['timestamp_ticks'][2, 0] == 0
    np.testing.assert_array_equal(data['power_dbm_traces'][2, 0], [0, 0, 0])


def test_one_worker_cancel_and_recording_cancel(desktop, tmp_path):
    from fieldfox_recording import FieldFoxRecording, RecordingError
    app, errors, finish = desktop
    done = []
    assert app.jobs.submit(lambda: app.jobs.cancel.wait(2), done.append, "waiting")
    assert not app.jobs.submit(lambda: None, done.append, "second")
    app.cancel(); finish(); assert done == [True]
    with pytest.raises(RecordingError, match="cancelled"):
        FieldFoxRecording.open(synthetic_session(tmp_path / "session"), cancel_event=app.jobs.cancel)


def test_source_frozen_diagnostics_entrypoint(tmp_path):
    output = tmp_path / "result.json"
    result = subprocess.run([sys.executable, "-m", "fieldfox_workbench", "--self-test", str(output)], capture_output=True, text=True, timeout=35)
    if "no display name" in result.stderr: pytest.skip("No Tk display")
    assert result.returncode == 0, result.stderr + (output.read_text() if output.exists() else "")
    data = json.loads(output.read_text()); assert data["ok"] and data["tabs"] == 5


def test_playback_bar_on_trace_page_updates_plot_and_keeps_cursor_in_sync(desktop, tmp_path):
    app, errors, finish = desktop
    app.open_path(synthetic_session(tmp_path / "session")); finish()
    assert app.playback.outer.master is app.plots.playback_frame
    assert "Session playback" not in [app.tabs.tab(tab, "text") for tab in app.tabs.tabs()]
    app.tabs.select(app.trace_tab)
    app.playback.slider.set(2); app.root.update()
    np.testing.assert_array_equal(app.plots.traces[0].y, [-68, -58, -48])
    assert "sweep 2" in app.playback.status.get() and "EST" in app.playback.status.get()
    app.playback.move(-1)
    assert app.playback.index.get() == 1 and app.plots.traces[0].name == "Sweep 1"
    app.playback.index.set(0); app.playback.show(); app.playback.delay.set("100")
    app.playback.toggle()
    assert app.playback.playing and app.playback.play_button.cget("text") == "Pause"
    assert app.playback.index.get() == 0 and app.plots.traces[0].name == "Sweep 0"
    deadline = time.monotonic()+2
    while app.playback.playing and time.monotonic() < deadline:
        app.root.update(); time.sleep(.01)
    assert not app.playback.playing and app.playback.index.get() == 2
    assert app.plots.traces[0].name == "Sweep 2" and app.playback.play_button.cget("text") == "Play"
    assert not errors
