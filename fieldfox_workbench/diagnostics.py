"""A bounded offline smoke test also usable inside the frozen executable."""
from pathlib import Path
import json
import struct
import tempfile
import time
import traceback
import sys


def synthetic_session(path):
    """Three unmistakably synthetic GPSA v18 sweeps; no supplied recording."""
    path = Path(path); (path / "dSTA00000").mkdir(parents=True); (path / "dTRC00000").mkdir()
    ticks = 638396640001234567
    state = struct.pack("<bbHihBB", 18, 1, 0, 0, 3, 1, 5) + bytes(4)
    state += struct.pack("<qdd10f", ticks, 1e9, 2e6, 10, 10, 1000, -100, .25, .01, -20, .02, 3, 4)
    state += bytes(4) + struct.pack("<hhh", 7, 8, 9) + bytes(2) + bytes([1, 0, 3, 11, 1, 2, 3, 4, 5, 6, 7, 8])
    assert len(state) == 104
    (path / "dSTA00000" / "00000000.STA").write_bytes(state)
    records = []
    for i in range(3):
        record = struct.pack("<HHiq", 0, 0, i, ticks+i*10_000_000)
        record += struct.pack("<iihh", 123456, -234567, 42, 100) + bytes([0, 0, 0x13, 1]) + struct.pack("<id", 0, .25)
        records.append(record + struct.pack("<8f", -70+i, -60+i, -50+i, 1, 2, 3, 4, 5))
    (path / "dTRC00000" / "00000000.TRC").write_bytes(b"".join(records))
    return path


def self_test(app, result_path):
    """Create all tabs, load data, render and round-trip MAT, then exit."""
    result = {"ok": False}; errors = []
    app.error = errors.append; app.jobs.on_error = errors.append
    try:
        import numpy as np
        from scipy.io import loadmat
        from fieldfox_recording.matlab import save_section_mat
        from .traces import read_csv, table_trace, export_traces
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix="fieldfox-workbench-selftest-") as name:
            base = Path(name); path = synthetic_session(base / "SYNTHETIC_RTAUTOsession")
            app.open_path(path)
            deadline = time.monotonic()+25
            while app.jobs.busy and time.monotonic() < deadline:
                app.root.update(); time.sleep(.01)
            if app.jobs.busy: raise TimeoutError("Session GUI load exceeded 25 seconds")
            if errors: raise RuntimeError(repr(errors))
            section = app.viewer.section
            assert section.power_dbm.shape == (3, 3)
            app.viewer.canvas.draw(); app.viewer.figure.savefig(base / "waterfall.png")
            save_section_mat(app.viewer.rec, section, base / "section.mat", source_timezone="EST")
            data = loadmat(base / "section.mat")
            np.testing.assert_array_equal(data["power_dbm"], section.power_dbm)
            assert "timestamp_utc" in data and "timestamp_est" in data
            manifest = app.viewer.rec.to_mat(base / "full_mat", chunk_sweeps=2)
            parts = [loadmat(base / "full_mat" / part["file"]) for part in manifest["parts"]]
            np.testing.assert_array_equal(np.concatenate([part["power_dbm_traces"][:, 0, :] for part in parts]), section.power_dbm)
            assert len(parts) == 2 and parts[1]["elapsed_s"][0, 0] == 2
            assert parts[0]["timestamp_ticks"].dtype == np.dtype("int64")
            # Reproduce 3 expected / 2 present without touching the intact session.
            short_path = synthetic_session(base / 'SYNTHETIC_SHORT_SESSION')
            short_trace = short_path / 'dTRC00000' / '00000000.TRC'
            content = short_trace.read_bytes(); short_trace.write_bytes(content[:len(content)*2//3])
            from fieldfox_recording import FieldFoxRecording
            short = FieldFoxRecording.open(short_path, recover_incomplete=True, expected_sweeps=3)
            short.to_mat(base / 'recovered_mat')
            recovered = loadmat(base / 'recovered_mat' / 'part_000001.mat')
            assert recovered['zero_filled'][2, 0] and not recovered['timestamp_valid'][2, 0]
            assert (recovered['power_dbm_traces'][2] == -300).all() and recovered['timestamp_ticks'][2, 0] == 0
            overlap_path = synthetic_session(base / 'SYNTHETIC_OVERLAP_SESSION')
            overlap_trace = overlap_path / 'dTRC00000' / '00000000.TRC'
            content = overlap_trace.read_bytes(); stride = len(content)//3
            overlap_trace.with_name('00000001.TRC').write_bytes(content[-stride:])
            overlap = FieldFoxRecording.open(overlap_path,recover_incomplete=True)
            from fieldfox_recording.spectrogram import load_section
            assert load_section(overlap).power_dbm.shape == (3,3)
            assert overlap.recovery['ignored_trailing_bytes'] == stride
            csv = base / "synthetic.csv"; csv.write_text("Frequency (Hz),Power (dBm)\n1,-70\n2,-60\n3,-50\n", encoding="utf-8")
            app.browser.open_local_preview(csv)
            deadline = time.monotonic()+5
            while app.jobs.busy and time.monotonic() < deadline:
                app.root.update(); time.sleep(.01)
            assert not app.jobs.busy and app.browser.preview_result.kind == "text"
            assert app.browser.preview_text.cget("state") == "disabled"
            app.show_help(); assert app.help_window.winfo_exists(); app.help_window.destroy()
            app.plots.clear(); app.plots.add_trace(table_trace(read_csv(csv)))
            app.plots.marker_x.set("2"); app.plots.add_marker(); app.plots.upper.set("-55"); app.plots.redraw()
            app.plots.canvas.draw(); export_traces(app.plots.traces, base / "trace.mat")
            assert loadmat(base / "trace.mat")["trace_1"].size == 1
            Image.new("RGB", (640, 480), "#24405a").save(base / "synthetic-screen.png")
            app.screen.open_image(base / "synthetic-screen.png")
            app.plots.write_report(base / "report.pdf")
            assert (base / "report.pdf").read_bytes().startswith(b"%PDF")
            app.tabs.select(app.trace_tab)
            assert app.playback.outer.master is app.plots.playback_frame
            app.playback.move(1)
            assert app.plots.traces[0].name == "Sweep 1"
            app.playback.max_hold.set(True); app.playback.min_hold.set(True)
            app.playback.move(1)
            held = {t.name: t for t in app.plots.traces}
            np.testing.assert_array_equal(held["Max hold"].y, section.power_dbm.max(axis=0))
            np.testing.assert_array_equal(held["Min hold"].y, section.power_dbm.min(axis=0))
            app.playback.reset_holds()
            np.testing.assert_array_equal(next(t for t in app.plots.traces if t.name == "Min hold").y, section.power_dbm[2])
            app.root.update()
            if errors: raise RuntimeError(repr(errors))
            result = {"ok": True, "tabs": len(app.tabs.tabs()), "session_shape": list(section.power_dbm.shape),
                      "checks": ["TkAgg rendering", "recording decoder", "CSV columns", "markers / limits", "MAT section UTC / EST",
                                 "MAT full session / chunk boundaries", "incomplete TRC -300 dBm fill / missing clocks", "overlapping TRC partition boundary / plot load", "MAT overlays", "Pillow screenshot", "PDF report", "playback controls on trace tab", "running max / min hold and reset",
                                 "read-only file preview", "Help button / dialog"],
                      "numpy": np.__version__, "python_version": sys.version.split()[0],
                      "frozen": bool(getattr(sys, "frozen", False)), "synthetic_data_only": True}
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        app.live.stop(); app.playback.stop()
        app.root.destroy()
    Path(result_path).parent.mkdir(parents=True, exist_ok=True)
    Path(result_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
