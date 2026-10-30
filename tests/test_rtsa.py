"""RTSA trace-layout reconstruction tests; all recording bytes are synthetic."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from fieldfox_recording import FieldFoxRecording, UnsupportedFormatError
from fieldfox_recording.parser import inspect_path, parse_state, parse_trace
from fieldfox_recording.spectrogram import load_section
from .fixtures import make_session, state_bytes, trace_bytes


@pytest.mark.parametrize("version", range(8, 19))
def test_rtsa_uses_shared_binary_layout_and_explicit_application(version):
    state = parse_state(state_bytes(version=version, application=2))
    sweep = parse_trace(trace_bytes(version=version), state)
    assert state.application == 2
    assert state.as_dict()["application_name"] == "RTSA"
    np.testing.assert_array_equal(sweep.power_dbm, [-70, -60, -50])
    np.testing.assert_array_equal(state.frequency_hz, [999e6, 1e9, 1001e6])
    assert sweep.header["result_sweep_time_s"] == .25


@pytest.mark.parametrize("flat", [False, True])
def test_rtsa_session_export_and_section(tmp_path, flat):
    root = make_session(tmp_path / "arbitrary_auto_session", application=2, flat=flat, split=True)
    rec = FieldFoxRecording.open(root)
    assert rec.metadata["application_name"] == "RTSA"
    assert rec.metadata["format"] == "FieldFox RTSA Record/Playback"
    assert rec.metadata["recording_content"] == "recorded scalar spectrum traces"
    assert inspect_path(root)["supported"] is True
    assert rec.power_dbm.shape == (3, 3)
    section = load_section(rec, start_sweep=1, stop_sweep=3)
    assert section.power_dbm.shape == (2, 3)
    rec.to_csv(tmp_path / "rtsa.csv")
    with (tmp_path / "rtsa.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 9
    assert float(rows[0]["power_dbm"]) == -70
    rec.to_npz(tmp_path / "rtsa.npz")
    with np.load(tmp_path / "rtsa.npz", allow_pickle=False) as data:
        assert json.loads(str(data["metadata_json"]))["application"] == 2
        np.testing.assert_array_equal(data["power_dbm_traces"][:, 0], rec.power_dbm)


def test_multiple_rtsa_blocks_remain_unsupported(tmp_path):
    root = make_session(tmp_path / "rtsa", application=2, traces=2)
    with pytest.raises(UnsupportedFormatError, match="multiple data blocks"):
        FieldFoxRecording.open(root)
    assert inspect_path(root)["states"][0]["trace_count"] == 2


def test_rtsa_zero_span_does_not_invent_time_axis(tmp_path):
    root = make_session(tmp_path / "rtsa", application=2)
    (root / "dSTA00000" / "00000000.STA").write_bytes(state_bytes(application=2, span=0))
    with pytest.raises(UnsupportedFormatError, match="zero-span axis"):
        FieldFoxRecording.open(root)
    state = parse_state(state_bytes(application=2, span=0))
    with pytest.raises(UnsupportedFormatError, match="Only GPSA"):
        _ = state.time_axis_s


def test_mixed_application_session_is_rejected(tmp_path):
    root = make_session(tmp_path / "mixed", changed_axis=True)
    states = state_bytes() + state_bytes(state_id=1, first_trace=1, application=2)
    (root / "dSTA00000" / "00000000.STA").write_bytes(states)
    with pytest.raises(UnsupportedFormatError, match="Changing application"):
        FieldFoxRecording.open(root)


def test_point_count_is_not_used_to_guess_rtsa_mode():
    assert parse_state(state_bytes(points=821, application=1)).application == 1
    assert parse_state(state_bytes(points=561, application=1)).application == 1


def test_rtsa_cli_exports_and_plots(tmp_path):
    pytest.importorskip("matplotlib")
    root = make_session(tmp_path / "rtsa", application=2)
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    for operation, suffix in [("export", "csv"), ("plot", "png")]:
        command = [sys.executable, "-m", "fieldfox_recording", operation, str(root)]
        if operation == "export":
            command += ["--format", "csv"]
        command += ["--output", str(tmp_path / f"section.{suffix}")]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
    assert (tmp_path / "section.png").read_bytes().startswith(b"\x89PNG")
