"""Cross-format values and explicit clock interpretation using synthetic bytes."""
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from fieldfox_recording import FieldFoxRecording, RecordingError
from fieldfox_recording.matlab import save_section_mat
from fieldfox_recording.spectrogram import load_section
from fieldfox_recording.timezones import convert_timestamps
from .fixtures import TICKS, make_session, trace_bytes


def clock_tick(text):
    delta = datetime.fromisoformat(text)-datetime(1,1,1)
    return np.array([(delta.days*86400+delta.seconds)*10_000_000+1_234_567], dtype=np.int64)


def test_est_default_conversion_preserves_all_seven_digits():
    times = convert_timestamps(np.array([TICKS]), "EST")
    assert times["timestamp_instrument"][0] == "2024-01-01T00:00:00.1234567"
    assert times["timestamp_utc"][0] == "2024-01-01T05:00:00.1234567Z"
    assert times["timestamp_est"][0] == "2024-01-01T00:00:00.1234567-05:00"
    assert times["timestamp_ticks_utc"][0] == TICKS+5*3600*10_000_000


def test_summer_fixed_est_and_eastern_are_distinct():
    times = convert_timestamps(clock_tick("2024-07-01T12:00:00"), "EST")
    assert times["timestamp_utc"][0] == "2024-07-01T17:00:00.1234567Z"
    assert times["timestamp_est"][0] == "2024-07-01T12:00:00.1234567-05:00"
    assert times["timestamp_eastern"][0] == "2024-07-01T13:00:00.1234567-04:00"
    eastern = convert_timestamps(clock_tick("2024-07-01T12:00:00"), "America/New_York")
    assert eastern["timestamp_utc"][0] == "2024-07-01T16:00:00.1234567Z"


def test_unspecified_clock_is_not_given_invented_utc():
    times = convert_timestamps(np.array([TICKS]))
    assert times["source_timezone"] == "unspecified"
    assert times["timestamp_utc"].tolist() == [""]
    assert times["timestamp_est"].tolist() == [""]
    assert times["timestamp_ticks_utc"].size == 0


@pytest.mark.parametrize("zone,expected", [("UTC", "2024-01-01T00:00:00.1234567Z"),
    ("+05:30", "2023-12-31T18:30:00.1234567Z"), ("-05:00", "2024-01-01T05:00:00.1234567Z")])
def test_source_offset_and_date_rollover(zone, expected):
    assert convert_timestamps(np.array([TICKS]),zone)["timestamp_utc"][0] == expected


@pytest.mark.parametrize("zone", ["Invalid/Zone", "+24:00", "-01:60"])
def test_invalid_zone_is_clear(zone):
    with pytest.raises(RecordingError):
        convert_timestamps(np.array([TICKS]), zone)


def test_dst_gap_and_ambiguous_hour_require_explicit_resolution():
    with pytest.raises(RecordingError, match="does not exist"):
        convert_timestamps(clock_tick("2024-03-10T02:30:00"), "America/New_York")
    ambiguous = clock_tick("2024-11-03T01:30:00")
    with pytest.raises(RecordingError, match="ambiguous"):
        convert_timestamps(ambiguous, "America/New_York")
    early = convert_timestamps(ambiguous,"America/New_York",0)
    late = convert_timestamps(ambiguous,"America/New_York",1)
    assert early["timestamp_utc"][0] == "2024-11-03T05:30:00.1234567Z"
    assert late["timestamp_utc"][0] == "2024-11-03T06:30:00.1234567Z"


def test_mat_export_matches_cropped_sampled_section_and_exact_ticks(tmp_path):
    io = pytest.importorskip("scipy.io")
    root = make_session(tmp_path / "RTAUTOsession01")
    (root/'dTRC00000/00000000.TRC').write_bytes(b''.join(
        trace_bytes(trace_id=i, ticks=TICKS+i*10_000_000, values=(-70+i,-60+i,-50+i)) for i in range(10)))
    rec = FieldFoxRecording.open(root)
    section = load_section(rec, start_sweep=1, step=2, max_sweeps=3, freq_min_hz=999e6, freq_max_hz=1e9)
    target = tmp_path/'section.mat'
    save_section_mat(rec, section, target)
    data = io.loadmat(target)
    np.testing.assert_array_equal(data['power_dbm'],section.power_dbm)
    assert data['power_dbm'].dtype == np.float32
    np.testing.assert_array_equal(data['sweep_indices'].ravel(),[1,5,9])
    np.testing.assert_array_equal(data['frequency_hz'].ravel(),[999e6,1e9])
    np.testing.assert_array_equal(data['timestamp_ticks'].ravel(),section.timestamp_ticks)
    assert data['timestamp_ticks'].dtype == np.int64
    assert data['timestamp_utc'][0,0][0] == '2024-01-01T05:00:01.1234567Z'
    assert data['source_timezone'][0] == 'EST'
    with pytest.raises(RecordingError, match='already exists'):
        save_section_mat(rec,section,target)
    with pytest.raises(RecordingError, match='outside the original'):
        save_section_mat(rec,section,root/'inside.mat')


def test_bad_timezone_leaves_no_export_file(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path/'session'))
    target=tmp_path/'bad.mat'
    with pytest.raises(RecordingError):
        save_section_mat(rec,load_section(rec),target,source_timezone='missing/timezone')
    assert not target.exists()


@pytest.mark.parametrize('option',['--export-mat','--output'])
def test_cli_mat_export_does_not_need_a_plot_window(tmp_path,option):
    io=pytest.importorskip('scipy.io')
    root=make_session(tmp_path/'RTAUTOsession03');target=tmp_path/'section.mat'
    result=subprocess.run([sys.executable,'-m','fieldfox_recording','plot',str(root),
        '--start-sweep','1','--stop-sweep','3',option,str(target)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert '2 sweeps x 3 frequency bins' in result.stdout
    assert io.loadmat(target)['power_dbm'].shape==(2,3)


def test_cli_can_save_image_and_mat_together(tmp_path):
    pytest.importorskip('scipy.io');pytest.importorskip('matplotlib')
    root=make_session(tmp_path/'session');target=tmp_path/'section.mat';image=tmp_path/'plot.png'
    result=subprocess.run([sys.executable,'-m','fieldfox_recording','plot',str(root),
        '--export-mat',str(target),'--output',str(image)],capture_output=True,text=True,
        env=os.environ|{'MPLBACKEND':'Agg'})
    assert result.returncode==0,result.stderr
    assert target.exists() and image.read_bytes().startswith(b'\x89PNG')
