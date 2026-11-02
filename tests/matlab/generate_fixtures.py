"""Generate synthetic cross-language fixtures outside the source checkout.

Run: python -m tests.matlab.generate_fixtures NEW_OUTPUT_FOLDER
Then: MATLAB test_full_session('NEW_OUTPUT_FOLDER')
"""
from pathlib import Path
import argparse
import struct

from fieldfox_recording import FieldFoxRecording
from tests.fixtures import make_session, state_bytes, trace_bytes, TICKS
from tests.test_recovery import short_session, recover, rpx, overlapping_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    root = parser.parse_args().output.resolve()
    root.mkdir()  # Never replace previous fixtures or results.
    cases = {'multi': dict(traces=2, changed_axis=True, split=True),
             'rtsa': dict(application=2), 'old': dict(version=1, flat=True),
             'zero': dict()}
    for name, options in cases.items():
        session = make_session(root/f'session_{name}', **options)
        if name == 'multi':
            for i, path in enumerate(sorted(session.glob('dTRC*/*.TRC'))):
                rows = [0] if i == 0 else [1, 2]
                path.write_bytes(b''.join(trace_bytes(trace_id=j, state_id=int(j>0), mask=3,
                    values=(-70+j, -60+j, -50+j, -90-j, -80-j, -70-j),
                    ticks=TICKS+j*10_000_000) for j in rows))
        if name == 'zero':
            next(session.glob('dSTA*/*.STA')).write_bytes(state_bytes(span=0))
        FieldFoxRecording.open(session).to_mat(root/f'python_{name}', chunk_sweeps=2)
    for name in ('short_index', 'short_next', 'partial', 'short_explicit', 'empty', 'header', 'deviated'):
        options = {}
        if name.startswith('short'):
            session = short_session(root/f'session_{name}', indexed=name=='short_index',
                                    next_file=name=='short_next')
            if name=='short_explicit': options['expected_sweeps']=500
        elif name=='deviated':
            session = short_session(root/f'session_{name}',indexed=False)
            trace = next(session.glob('dTRC*/*.TRC'))
            trace.with_name('00000001.TRC').write_bytes(b''.join(
                trace_bytes(trace_id=i,ticks=TICKS+i*10_000_000) for i in range(497,500)))
            (session/'TRC.rpx').write_bytes(rpx(deviations=[(0,497),(1,3)]))
        else:
            session = make_session(root/f'session_{name}',traces=2)
            trace = next(session.glob('dTRC*/*.TRC'))
            content = trace.read_bytes(); stride = len(content)//3
            if name=='partial': trace.write_bytes(content[:2*stride+54])
            elif name=='header': trace.write_bytes(content[:2*stride+15])
            else:
                trace.write_bytes(b''); options['expected_sweeps']=3
        recover(session,**options).to_mat(root/f'python_{name}',chunk_sweeps=250)
    for name in ('overlap','padding','indexed_overlap','repeated'):
        options = {} if name=='overlap' else dict(boundary=5)
        if name=='padding': options.update(tail='bytes',extra=200)
        if name=='indexed_overlap': options['indexed']=True
        session=overlapping_session(root/f'session_{name}',**options)
        if name=='repeated':
            second=session/'dTRC00000'/'00000001.TRC'
            data=second.read_bytes(); second.write_bytes(data[:len(data)//3])
            second.with_name('00000002.TRC').write_bytes(data)
        recover(session).to_mat(root/f'python_{name}',chunk_sweeps=5000)
    bad = make_session(root/'session_bad')
    trace = next(bad.glob('dTRC*/*.TRC'))
    content = bytearray(trace.read_bytes()); stride = len(content)//3
    struct.pack_into('<i', content, 2*stride+4, 99)
    trace.write_bytes(content)
    print(root)


if __name__ == '__main__':
    main()
