"""Synthetic byte fixtures written from the documented layout, never instrument data."""
from pathlib import Path
import struct

TICKS = 638396640001234567  # 2024-01-01T00:00:00.1234567 in .NET ticks


def state_bytes(version=18, state_id=0, first_trace=0, points=3, traces=1, auxiliary=5,
                center=1e9, span=2e6, application=1):
    # Deliberately compose independent field groups, not the production parser.
    prefix = struct.pack("<bbH", version, application, state_id)
    prefix += struct.pack("<HH", first_trace, 0) if version < 5 else struct.pack("<i", first_trace)
    if version >= 16:
        prefix += struct.pack("<hBB", points, traces, auxiliary)
    elif version >= 11:
        prefix += struct.pack("<hh", points, traces)
    else:
        prefix += struct.pack("<i", points)
    prefix += b"\xaa\xbb\xcc\xdd"
    numeric = struct.pack("<qdd10f", TICKS, center, span, 10, 10, 1000, -100, .25, .01, -20, .02, 3, 4)
    suffix = bytes.fromhex("11223344") + struct.pack("<hhh", 7, 8, 9) + b"\x00\x00"
    suffix += bytes([1, 0, 3, 11, 1, 2, 3, 4, 5, 6, 7, 8])
    assert len(prefix + numeric + suffix) == 104
    return prefix + numeric + suffix


def trace_bytes(version=18, trace_id=0, state_id=0, values=(-70., -60., -50.), auxiliary=(1., 2., 3., 4., 5.), ticks=TICKS, mask=1):
    prefix = (struct.pack("<HHi", 0, state_id, trace_id) if version >= 5
              else struct.pack("<HHi", trace_id, state_id, 0))
    prefix += struct.pack("<q", ticks)
    if version >= 4:
        prefix += struct.pack("<iih", 123456, -234567, 42)
        prefix += struct.pack("<h", 100) if version >= 7 else bytes([1, 0])
    prefix += bytes([0, 0, 0x13] if version >= 12 else [1, 0, 1])
    prefix += struct.pack("<B id", mask, 0, .25)
    payload = tuple(values) + (tuple(auxiliary) if version >= 16 else ())
    return prefix + struct.pack("<" + "f" * len(payload), *payload)


def make_session(root: Path, version=18, flat=False, changed_axis=False, split=False, traces=1, application=1):
    root.mkdir()
    states = state_bytes(version=version, traces=traces, application=application)
    if changed_axis:
        states += state_bytes(version=version, state_id=1, first_trace=1, center=2e9, traces=traces, application=application)
    values = (-70., -60., -50.) * traces
    records = [trace_bytes(version=version, trace_id=i, state_id=1 if changed_axis and i else 0,
                           values=values, ticks=TICKS+i*10_000_000) for i in range(3)]
    if flat:
        (root / "STA00000").write_bytes(states)
        trace_path = root / "TRC00000"
    else:
        (root / "dSTA00000").mkdir()
        (root / "dTRC00000").mkdir()
        (root / "dSTA00000" / "00000000.STA").write_bytes(states)
        trace_path = root / "dTRC00000" / "00000000.TRC"
    trace_path.write_bytes(b"".join(records[:1] if split else records))
    if split:
        next_path = root / "TRC00001" if flat else trace_path.with_name("00000001.TRC")
        next_path.write_bytes(b"".join(records[1:]))
    return root
