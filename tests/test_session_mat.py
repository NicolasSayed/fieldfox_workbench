"""Full-session MAT exports preserve unselected sweeps, slots and boundaries."""
import json
import struct
import threading

import numpy as np
import pytest
from scipy.io import loadmat

from fieldfox_recording import FieldFoxRecording
from fieldfox_recording.__main__ import main
from fieldfox_recording.parser import RecordingError
from .fixtures import TICKS, make_session, state_bytes, trace_bytes


def parts(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    return manifest, [loadmat(folder / p['file']) for p in manifest['parts']]


@pytest.mark.parametrize('flat,split,version,application', [
    (False, True, 18, 1), (True, False, 1, 1), (False, False, 8, 2),
])
def test_all_rows_exact_times_and_no_thinning(tmp_path, flat, split, version, application):
    rec = FieldFoxRecording.open(make_session(tmp_path/'session', flat=flat, split=split,
                                              version=version, application=application))
    output = tmp_path/'mat'
    progress = []
    rec.to_mat(output, chunk_sweeps=2, progress=lambda done, total: progress.append((done, total)))
    manifest, data = parts(output)
    assert manifest['complete'] and manifest['index_base'] == 0
    assert progress == [(2, 3), (3, 3)]
    assert [p['n_sweeps'] for p in manifest['parts']] == [2, 1]
    power = np.concatenate([p['power_dbm_traces'] for p in data])
    np.testing.assert_array_equal(power, [[[-70, -60, -50]]]*3)
    assert power.dtype == np.float32
    np.testing.assert_array_equal(np.concatenate([p['sweep_indices'] for p in data]).ravel(), [0, 1, 2])
    np.testing.assert_array_equal(np.concatenate([p['elapsed_s'] for p in data]).ravel(), [0, 1, 2])
    assert data[0]['timestamp_ticks'].dtype == np.int64
    assert data[0]['timestamp_ticks'][0, 0] == TICKS
    assert data[0]['timestamp_ticks_utc'][0, 0] == TICKS + 5*3600*10_000_000
    assert data[0]['timestamp_utc'][0, 0][0] == '2024-01-01T05:00:00.1234567Z'
    assert data[1]['timestamp_est'][0, 0][0] == '2024-01-01T00:00:02.1234567-05:00'
    assert json.loads(data[0]['trace_headers_json'][0, 0][0])
    assert data[0]['frequency_hz'].shape == (3, 1)


def test_every_slot_auxiliary_and_changed_axis(tmp_path):
    session = make_session(tmp_path/'session', traces=2, changed_axis=True, split=True)
    files = sorted(session.glob('dTRC*/*.TRC'))
    for index, file in enumerate(files):
        rows = [0] if index == 0 else [1, 2]
        file.write_bytes(b''.join(trace_bytes(trace_id=i, state_id=int(i>0),
            values=(-70+i, -60+i, -50+i, -90-i, -80-i, -70-i),
            auxiliary=(i, 2, 3, 4, 5), ticks=TICKS+i*10_000_000, mask=3) for i in rows))
    rec = FieldFoxRecording.open(session)
    rec.to_mat(tmp_path/'mat', chunk_sweeps=100)
    manifest, data = parts(tmp_path/'mat')
    assert [(p['start_sweep'], p['stop_sweep']) for p in manifest['parts']] == [(0, 1), (1, 3)]
    assert data[0]['frequency_hz'][0, 0] == 999_000_000
    assert data[1]['frequency_hz'][0, 0] == 1_999_000_000
    np.testing.assert_array_equal(data[1]['power_dbm_traces'][1, 1], [-92, -82, -72])
    np.testing.assert_array_equal(data[1]['auxiliary_values'][:, 0], [1, 2])
    np.testing.assert_array_equal(data[1]['trace_masks'].ravel(), [3, 3])
    np.testing.assert_array_equal(data[1]['state_ids'].ravel(), [1, 1])
    np.testing.assert_array_equal(data[1]['trace_slot_indices'].ravel(), [0, 1])


def test_zero_span_axis(tmp_path):
    session = make_session(tmp_path/'session')
    next(session.glob('dSTA*/*.STA')).write_bytes(state_bytes(span=0))
    FieldFoxRecording.open(session).to_mat(tmp_path/'mat')
    _, data = parts(tmp_path/'mat')
    assert 'frequency_hz' not in data[0]
    np.testing.assert_allclose(data[0]['time_axis_s'].ravel(), [.01, .135, .26])


def test_budget_splits_and_invalid_options_leave_no_output(tmp_path):
    rec = FieldFoxRecording.open(make_session(tmp_path/'session'))
    rec.to_mat(tmp_path/'small', max_part_mib=.0015)
    manifest, _ = parts(tmp_path/'small')
    assert [p['n_sweeps'] for p in manifest['parts']] == [1, 1, 1]
    for options in ({'chunk_sweeps': 0}, {'chunk_sweeps': 1.5}, {'chunk_sweeps': True},
                    {'max_part_mib': float('nan')}, {'max_part_mib': 513},
                    {'max_part_mib': .000001}, {'source_timezone': 'invalid/zone'}):
        with pytest.raises((RecordingError, ValueError)):
            rec.to_mat(tmp_path/'bad', **options)
        assert not (tmp_path/'bad').exists()
        assert not list(tmp_path.glob('.fieldfox-mat-*'))


def test_originals_existing_output_and_cancellation(tmp_path):
    session = make_session(tmp_path/'session')
    original = {p: p.read_bytes() for p in session.rglob('*') if p.is_file()}
    rec = FieldFoxRecording.open(session)
    existing = tmp_path/'existing'; existing.mkdir(); (existing/'keep').write_text('keep')
    for target in (existing, session/'export'):
        with pytest.raises(RecordingError):
            rec.to_mat(target)
    event = threading.Event(); rec.cancel_event = event
    with pytest.raises(RecordingError, match='cancelled'):
        rec.to_mat(tmp_path/'cancelled', chunk_sweeps=1, progress=lambda *_: event.set())
    assert not (tmp_path/'cancelled').exists()
    assert not list(tmp_path.glob('.fieldfox-mat-*'))
    assert (existing/'keep').read_text() == 'keep'
    assert all(p.read_bytes() == content for p, content in original.items())


def test_bad_record_in_later_part_removes_incomplete_export(tmp_path):
    session = make_session(tmp_path/'session')
    trace = next(session.glob('dTRC*/*.TRC'))
    content = bytearray(trace.read_bytes()); stride = len(content)//3
    struct.pack_into('<i', content, 2*stride+4, 99)
    trace.write_bytes(content)
    with pytest.raises(RecordingError):
        FieldFoxRecording.open(session).to_mat(tmp_path/'bad', chunk_sweeps=1)
    assert not (tmp_path/'bad').exists()
    assert not list(tmp_path.glob('.fieldfox-mat-*'))


def test_cli_mat(tmp_path, capsys):
    session = make_session(tmp_path/'session')
    output = tmp_path/'mat'
    assert main(['export', str(session), '--format', 'mat', '--output', str(output),
                 '--chunk-sweeps', '1', '--source-timezone', 'UTC']) == 0
    assert 'Exported 3 sweeps' in capsys.readouterr().out
    manifest, data = parts(output)
    assert len(manifest['parts']) == 3
    assert data[0]['timestamp_ticks_utc'][0, 0] == TICKS
