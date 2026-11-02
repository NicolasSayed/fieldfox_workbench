"""Recover short partition tails without shifting later sweeps or inventing time."""
import csv
import json
import struct
import warnings
import zlib

import numpy as np
import pytest
from scipy.io import loadmat

from fieldfox_recording import FieldFoxRecording, RecordingError
from fieldfox_recording.__main__ import main
from fieldfox_recording.spectrogram import load_section, plot_section
from .fixtures import TICKS, make_session, trace_bytes


def rpx(total=500, nominal=500, deviations=()):
    def item(tag, body):
        return struct.pack('<iB', len(body), tag)+body
    def chunk(tag, body):
        return struct.pack('<i', len(body))+tag+body+struct.pack('<I', zlib.crc32(tag+body))
    body = item(10, b'TRC')+b''.join(item(t, struct.pack('<i', v)) for t, v in
                                      [(11,total),(12,5000),(13,nominal)])
    raw = b'FFRPINDX'+struct.pack('<H',1)+chunk(b'FDAT',body)
    if deviations:
        body = item(10,b'TRC')+item(12,b''.join(struct.pack('<ii', *pair) for pair in deviations))
        raw += chunk(b'fDEV',body)
    return raw


def short_session(root, *, indexed=True, next_file=False):
    session = make_session(root)
    trace = next(session.glob('dTRC*/*.TRC'))
    trace.write_bytes(b''.join(trace_bytes(trace_id=i,ticks=TICKS+i*10_000_000,
                                          values=(-70+i/1000,-60,-50)) for i in range(497)))
    if indexed:
        (session/'TRC.rpx').write_bytes(rpx())
    if next_file:
        trace.with_name('00000001.TRC').write_bytes(b''.join(
            trace_bytes(trace_id=i, ticks=TICKS+i*10_000_000,values=(-90,-80,-70)) for i in range(500,503)))
    return session


def recover(path, **options):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        return FieldFoxRecording.open(path,recover_incomplete=True,**options)


def test_expected_500_read_497(tmp_path):
    session = short_session(tmp_path/'session')
    original = {p:p.read_bytes() for p in session.rglob('*') if p.is_file()}
    with pytest.raises(RecordingError,match='record count 500.*497'):
        FieldFoxRecording.open(session)
    with pytest.warns(RuntimeWarning,match='Recovering 3'):
        rec = FieldFoxRecording.open(session,recover_incomplete=True)
    assert len(rec)==500 and rec.recovery['zero_filled_sweeps']==3
    rows = list(rec.iter_sweeps(496))
    assert [s.trace_id for s in rows]==[496,497,498,499]
    assert rows[0].ticks==TICKS+496*10_000_000
    for row in rows[1:]:
        np.testing.assert_array_equal(row.power_dbm_traces,[[0,0,0]])
        assert row.ticks==0 and row.timestamp=='' and row.trace_mask==0
        assert row.header['zero_filled'] and not row.header['timestamp_valid']
    assert sum(1 for _ in rec)==500
    assert all(p.read_bytes()==b for p,b in original.items())


def test_gap_from_next_partition_preserves_later_indices_and_random_access(tmp_path):
    rec = recover(short_session(tmp_path/'session',indexed=False,next_file=True))
    assert len(rec)==503
    rows = list(rec.iter_sweeps(495,503,2))
    assert [s.trace_id for s in rows]==[495,497,499,501]
    assert rows[1].ticks==rows[2].ticks==0
    np.testing.assert_array_equal(rows[-1].power_dbm_traces,[[-90,-80,-70]])
    assert rows[-1].ticks==TICKS+501*10_000_000


def test_no_index_does_not_guess_final_count(tmp_path):
    path=short_session(tmp_path/'session',indexed=False)
    assert len(recover(path))==497
    assert len(recover(path,expected_sweeps=500))==500
    with pytest.raises(RecordingError,match='less than'):
        recover(path,expected_sweeps=495)


@pytest.mark.parametrize('available',[0,3,15,43,44,48,50,52,55,75])
def test_partial_headers_and_torn_float_zero_fill(tmp_path,available):
    path=make_session(tmp_path/'session')
    trace=next(path.glob('dTRC*/*.TRC'))
    full=trace.read_bytes(); stride=len(full)//3
    trace.write_bytes(full[:2*stride+available])
    rec=recover(path,expected_sweeps=3)
    row=list(rec)[-1]
    assert row.trace_id==2 and row.header['zero_filled']
    if available<44:
        assert row.ticks==0 and row.header['recorded_value_count']==0
        np.testing.assert_array_equal(row.power_dbm_traces,[[0,0,0]])
    else:
        assert row.ticks==TICKS+2*10_000_000
        count=(available-44)//4
        assert row.header['recorded_value_count']==count
        expected=np.array([-70,-60,-50,1,2,3,4,5],np.float32)
        expected[count:]=0
        np.testing.assert_array_equal(row.power_dbm_traces.ravel(),expected[:3])
        np.testing.assert_array_equal(row.auxiliary_values,expected[3:])


def test_rpx_file_deviations_do_not_pad_legitimate_short_partition(tmp_path):
    path=short_session(tmp_path/'session',indexed=False)
    first=next(path.glob('dTRC*/*.TRC'))
    first.with_name('00000001.TRC').write_bytes(b''.join(trace_bytes(trace_id=i,
        ticks=TICKS+i*10_000_000) for i in range(497,500)))
    (path/'TRC.rpx').write_bytes(rpx(deviations=[(0,497),(1,3)]))
    rec=recover(path)
    assert len(rec)==500 and rec.recovery['zero_filled_sweeps']==0
    assert [s.trace_id for s in rec.iter_sweeps(496)]==[496,497,498,499]


def test_corruption_is_not_treated_as_missing_data(tmp_path):
    path=make_session(tmp_path/'session')
    trace=next(path.glob('dTRC*/*.TRC'))
    content=bytearray(trace.read_bytes()); struct.pack_into('<i',content,len(content)//3+4,99)
    trace.write_bytes(content)
    with pytest.raises(RecordingError,match='expected trace 1'):
        list(recover(path))
    (path/'TRC.rpx').write_bytes(rpx(total=3,nominal=3)[:-1]+b'\0')
    with pytest.raises(RecordingError,match='CRC'):
        recover(path)


def test_recovered_exports_missing_times_and_plot_axis(tmp_path):
    rec=recover(short_session(tmp_path/'session'))
    rec.to_mat(tmp_path/'mat',chunk_sweeps=250)
    data=loadmat(tmp_path/'mat'/'part_000002.mat')
    assert data['power_dbm_traces'].shape==(250,1,3)
    assert data['zero_filled'][-3:].all() and not data['timestamp_valid'][-3:].any()
    assert not data['timestamp_ticks_utc'][-3:].any()
    assert data['timestamp_est'][-1,0].size==0  # MATLAB empty char
    assert np.isnan(data['elapsed_s'][-3:]).all()
    section=load_section(rec,start_sweep=495,max_sweeps=10)
    assert len(section.power_dbm)==5 and section.zero_filled[-3:].all()
    figure,axis=plot_section(section)
    assert 'sweep index' in axis.get_ylabel()
    import matplotlib.pyplot as plt
    plt.close(figure)
    rec.to_npz(tmp_path/'all.npz')
    with np.load(tmp_path/'all.npz') as data:
        assert data['zero_filled'].sum()==3 and not data['timestamp_valid'][-3:].any()
    rec.to_csv(tmp_path/'all.csv')
    with (tmp_path/'all.csv').open(newline='') as stream:
        last=list(csv.DictReader(stream))[-1]
    assert last['zero_filled']=='1' and last['timestamp_valid']=='0' and last['power_dbm']=='0'


def test_cli_recovery(tmp_path,capsys):
    path=short_session(tmp_path/'session',indexed=False)
    with pytest.warns(RuntimeWarning):
        assert main(['inspect',str(path),'--recover-incomplete','--expected-sweeps','500'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['metadata']['recovery']['zero_filled_sweeps']==3
