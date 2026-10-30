"""Synthetic reconstruction tests. No recording-validated claim is made."""
import csv
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
import pytest

from fieldfox_recording import FieldFoxRecording, RecordingError, UnsupportedFormatError
from fieldfox_recording.parser import parse_state, parse_trace, trace_record_size, ticks_to_iso, inspect_path
from .fixtures import TICKS, make_session, state_bytes, trace_bytes


@pytest.mark.parametrize("version", range(1, 19))
def test_layout_all_reconstructed_versions(version):
    state = parse_state(state_bytes(version=version))
    record = trace_bytes(version=version)
    assert len(record) == (44 if version >= 4 else 32) + 4*(8 if version >= 16 else 3)
    assert trace_record_size(state) == len(record)
    sweep = parse_trace(record, state)
    np.testing.assert_array_equal(sweep.power_dbm, [-70, -60, -50])
    np.testing.assert_array_equal(state.frequency_hz, [999e6, 1e9, 1001e6])
    assert state.state_id == sweep.state.state_id == 0
    assert sweep.timestamp == "2024-01-01T00:00:00.1234567"
    assert state.settings["reserved_prefix_hex"] == "aabbccdd"
    assert state.auxiliary_count == (5 if version >= 16 else 0)
    assert state.settings["reference_level_raw"] == (10 if version >= 13 else 0)
    assert sweep.header.get("measurement_conditions") == (0x13 if version >= 12 else None)


@pytest.mark.parametrize("version", [1, 4, 5, 7, 11, 12, 16, 18])
@pytest.mark.parametrize("flat", [False, True])
def test_stream_partitions_and_api(tmp_path, version, flat):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", version=version, flat=flat, split=True))
    assert len(rec) == 3
    assert [s.trace_id for s in rec] == [0, 1, 2]
    assert rec.power_dbm.shape == (3, 3)
    assert rec.timestamps.shape == (3,)
    assert rec.timestamp_ticks.tolist() == [TICKS, TICKS+10_000_000, TICKS+20_000_000]
    assert inspect_path(rec.path)["verified_trace_records"] == 3


def test_csv_npz_preserve_values_axes_and_ticks(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session"))
    csv_path, npz_path = tmp_path / "session.csv", tmp_path / "session.npz"
    rec.to_csv(csv_path)
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 9
    assert [float(row["frequency_hz"]) for row in rows[:3]] == rec.frequency_hz.tolist()
    assert rows[0]["timestamp_local_unspecified"] == "2024-01-01T00:00:00.1234567"
    assert int(rows[-1]["timestamp_ticks"]) == TICKS + 20_000_000
    rec.to_npz(npz_path)
    with np.load(npz_path, allow_pickle=False) as data:
        np.testing.assert_array_equal(data["power_dbm_traces"][:, 0], rec.power_dbm)
        np.testing.assert_array_equal(data["auxiliary_values"][0], [1, 2, 3, 4, 5])
        np.testing.assert_array_equal(data["axes_by_state"][0], rec.frequency_hz)
        assert data["timestamp_ticks"][0] == TICKS
        assert json.loads(str(data["metadata_json"]))["version"] == 18
        assert json.loads(data["trace_headers_json"][0])["gps_j_raw"] == 123456


def test_changing_axis_is_explicit(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", changed_axis=True))
    with pytest.raises(UnsupportedFormatError, match="changes frequency"):
        _ = rec.frequency_hz
    sweeps = list(rec)
    assert sweeps[1].state.frequency_hz[1] == 2e9
    rec.to_npz(tmp_path / "changing.npz")
    with np.load(tmp_path / "changing.npz") as data:
        assert data["state_ids"].tolist() == [0, 1, 1]
        assert data["axes_by_state"].shape == (2, 3)


def test_multiple_trace_slots_remain_separate(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session", traces=2))
    assert rec.power_dbm_traces.shape == (3, 2, 3)
    with pytest.raises(UnsupportedFormatError, match="Multiple traces"):
        _ = rec.power_dbm
    assert list(rec)[0].auxiliary_values.shape == (5,)


def test_zero_span_uses_seconds_not_frequency():
    state = parse_state(state_bytes(span=0))
    with pytest.raises(UnsupportedFormatError, match="Zero-span"):
        _ = state.frequency_hz
    np.testing.assert_allclose(state.time_axis_s, [.01, .135, .26])


@pytest.mark.parametrize("length", [0, 1, 16, 40, 92, 103, 105])
def test_state_truncation_or_extra_bytes(length):
    with pytest.raises(RecordingError, match="104 bytes"):
        parse_state((state_bytes() + b"extra")[:length])


@pytest.mark.parametrize("version", [0, 19, 127, -1])
def test_unknown_version_rejected(version):
    with pytest.raises(UnsupportedFormatError, match="version"):
        parse_state(state_bytes(version=version))


@pytest.mark.parametrize("ticks", [0, -1, 3155378976000000000])
def test_invalid_ticks_not_replaced_by_current_time(ticks):
    with pytest.raises(RecordingError, match="timestamp"):
        ticks_to_iso(ticks)


def test_truncated_trace_and_bad_link():
    state = parse_state(state_bytes())
    with pytest.raises(RecordingError, match="requires"):
        parse_trace(trace_bytes()[:-1], state)
    with pytest.raises(RecordingError, match="state link"):
        parse_trace(trace_bytes(state_id=1), state)


def test_wrong_endian_dimensions_not_accepted():
    raw = bytearray(state_bytes(version=8))
    struct.pack_into(">i", raw, 8, 3)
    with pytest.raises(RecordingError, match="allocation guard"):
        parse_state(raw)


def test_nonfinite_setting_is_reported_as_corruption():
    raw = bytearray(state_bytes())
    struct.pack_into("<f", raw, 48, float("nan"))
    with pytest.raises(RecordingError, match="Non-finite state settings"):
        parse_state(raw)


@pytest.mark.parametrize("field,value", [("points", 0), ("points", -1), ("traces", 0)])
def test_invalid_dimensions(field, value):
    with pytest.raises(RecordingError, match="dimensions"):
        parse_state(state_bytes(**{field: value}))


def test_unknown_application_metadata_survives_unsupported_decode(tmp_path):
    root = make_session(tmp_path / "unknown", application=3)
    with pytest.raises(UnsupportedFormatError, match="application 3"):
        FieldFoxRecording.open(root)
    result = inspect_path(root)
    assert result["supported"] is False
    assert result["states"][0]["application"] == 3


def test_unsupported_capture_and_unknown_prefix(tmp_path):
    path = tmp_path / "capture.vita49"
    path.write_bytes(b"\x18\x00\x00\x01IQunknown")
    with pytest.raises(UnsupportedFormatError, match="IQ/VITA"):
        FieldFoxRecording.open(path)
    result = inspect_path(path)
    assert result["supported"] is False
    assert result["prefix_hex"].startswith("18000001")


def test_corrupt_partition_trace_ids_and_atomic_export(tmp_path):
    root = make_session(tmp_path / "session")
    trace = root / "dTRC00000" / "00000000.TRC"
    trace.write_bytes(trace_bytes(trace_id=1))
    rec = FieldFoxRecording.open(root)
    target = tmp_path / "failed.csv"
    with pytest.raises(RecordingError, match="expected trace 0"):
        rec.to_csv(target)
    assert not target.exists()
    assert not list(tmp_path.glob(".fieldfox-*"))


def test_no_silent_truncated_session(tmp_path):
    root = make_session(tmp_path / "session")
    trace = root / "dTRC00000" / "00000000.TRC"
    trace.write_bytes(trace.read_bytes()[:-1])
    with pytest.raises(RecordingError, match="stride"):
        FieldFoxRecording.open(root)


def test_missing_partition(tmp_path):
    root = make_session(tmp_path / "session", split=True)
    (root / "dTRC00000" / "00000001.TRC").rename(root / "dTRC00000" / "00000002.TRC")
    with pytest.raises(RecordingError, match="partition"):
        FieldFoxRecording.open(root)


def test_input_and_existing_output_protected(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path / "session"))
    with pytest.raises(RecordingError, match="outside"):
        rec.to_csv(rec.path / "new.csv")
    output = tmp_path / "existing.csv"
    output.write_text("original")
    with pytest.raises(RecordingError, match="already exists"):
        rec.to_csv(output)
    assert output.read_text() == "original"


def test_cli(tmp_path):
    root = make_session(tmp_path / "session")
    inspect = subprocess.run([sys.executable, "-m", "fieldfox_recording", "inspect", str(root)], capture_output=True, text=True)
    assert inspect.returncode == 0, inspect.stderr
    assert json.loads(inspect.stdout)["metadata"]["n_sweeps"] == 3
    export = subprocess.run([sys.executable, "-m", "fieldfox_recording", "export", str(root), "--format", "csv", "--output", str(tmp_path / "cli.csv")], capture_output=True, text=True)
    assert export.returncode == 0, export.stderr
    assert "Exported 3 sweeps, 3 points, 1 trace(s)" in export.stdout


@pytest.mark.skipif(not os.environ.get("FIELDFOX_TEST_SESSION"), reason="No real recording supplied; set FIELDFOX_TEST_SESSION")
def test_local_instrument_recording():
    rec = FieldFoxRecording.open(os.environ["FIELDFOX_TEST_SESSION"])
    assert sum(1 for _ in rec) == len(rec) > 0
