"""Generate synthetic cross-language fixtures outside the source checkout.

Run: python -m tests.matlab.generate_fixtures NEW_OUTPUT_FOLDER
Then: MATLAB test_full_session('NEW_OUTPUT_FOLDER')
"""
from pathlib import Path
import argparse
import struct

from fieldfox_recording import FieldFoxRecording
from tests.fixtures import make_session, state_bytes, trace_bytes, TICKS


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
    bad = make_session(root/'session_bad')
    trace = next(bad.glob('dTRC*/*.TRC'))
    content = bytearray(trace.read_bytes()); stride = len(content)//3
    struct.pack_into('<i', content, 2*stride+4, 99)
    trace.write_bytes(content)
    print(root)


if __name__ == '__main__':
    main()
