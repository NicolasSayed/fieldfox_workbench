"""Explicit recovery of short TRC partition tails; never edit the input files."""
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import struct
import warnings

import numpy as np

from .parser import RecordingError, Sweep, parse_trace, trace_record_size

MISSING_POWER_DBM = -300.0


@dataclass(frozen=True)
class TracePartition:
    path: Path
    start: int
    count: int
    size: int


def _same_prefix(rec, first, second, size):
    """Allow an identical repeated partition prefix, with bounded comparisons."""
    with first.open('rb') as left, second.open('rb') as right:
        while size:
            rec._check_cancel()
            block = left.read(min(65536, size))
            if not block or block != right.read(len(block)):
                return False
            size -= len(block)
    return True


def plan(rec, expected_sweeps=None):
    """Use verified RPX counts, next-file IDs, or an explicit final count.

    FDAT nominal counts + fDEV (file index, actual count) pairs follow
    Utility.dll apf.t, cases 11/15/5. No fixed 500-record assumption is made.
    """
    stride = trace_record_size(rec.states[0])
    header_bytes = stride-4*rec.states[0].value_count
    first_ids = rec.state_first_ids
    if first_ids[0] != 0 or any(b <= a for a, b in zip(first_ids, first_ids[1:])):
        raise RecordingError("Invalid state transition boundaries")
    if expected_sweeps is not None and (isinstance(expected_sweeps, bool) or
            not isinstance(expected_sweeps, int) or expected_sweeps < 1):
        raise RecordingError("expected_sweeps must be a positive integer")
    stores = [i['stores']['TRC'] for i in rec.indexes if 'TRC' in i['stores']]
    counts = None
    declared = None
    for store in stores:
        total, nominal = store.get('num_records'), store.get('nominal_records_per_file')
        if total is None or nominal is None or total < 1 or nominal < 1:
            raise RecordingError("Invalid RPX TRC total/nominal record count")
        # Allocate only per-file metadata, never a record-sized lookup table.
        if (total + nominal-1)//nominal > len(rec.trace_files):
            raise RecordingError("RPX describes missing TRC partitions; only existing short files can be recovered")
        candidate = [min(nominal, total-i*nominal) for i in range((total+nominal-1)//nominal)]
        for index, count in store.get('file_deviations', []):
            if not 0 <= index < len(rec.trace_files) or count < 0:
                raise RecordingError("Invalid RPX TRC file deviation")
            candidate.extend([nominal] * max(0, index+1-len(candidate)))
            candidate[index] = count
        if sum(candidate) != total or len(candidate) != len(rec.trace_files):
            raise RecordingError("RPX TRC partition counts are inconsistent with total/files")
        if counts is not None and candidate != counts:
            raise RecordingError("Conflicting RPX TRC partition counts")
        counts, declared = candidate, total
    if declared is not None and expected_sweeps not in (None, declared):
        raise RecordingError("expected_sweeps conflicts with the RPX TRC count")
    sizes = [p.stat().st_size for p in rec.trace_files]
    starts = []
    if counts is not None:
        source = 'RPX FDAT/fDEV counts'
        start = 0
        for count in counts:
            starts.append(start); start += count
    else:
        source = 'partition first sweep IDs / physical tail'
        for number, (path, size) in enumerate(zip(rec.trace_files, sizes)):
            rec._check_cancel()
            start = 0 if number == 0 else starts[-1] + (sizes[number-1]+stride-1)//stride
            if size >= 8:
                with path.open('rb') as stream:
                    prefix = stream.read(min(header_bytes, size))
                actual = struct.unpack_from('<i' if rec.states[0].version >= 5 else '<H', prefix,
                                            4 if rec.states[0].version >= 5 else 0)[0]
                repeated = number and actual == starts[-1]
                identical = repeated and (sizes[number-1] < header_bytes or
                    _same_prefix(rec, rec.trace_files[number-1], path, sizes[number-1]))
                if ((number == 0 and actual != 0) or (number and
                        (actual < starts[-1] or (repeated and not identical)))):
                    raise RecordingError(f"{path}: invalid first trace {actual}; expected trace 0 initially and increasing partition starts")
                if len(prefix) == header_bytes:
                    sid = struct.unpack_from('<H', prefix, 2)[0]
                    if sid >= len(rec.states) or sid != bisect_right(first_ids, actual)-1:
                        raise RecordingError(f"{path}: invalid first trace state link")
                    # Validate the header before using its ID as a boundary.
                    # Padding here is only for parsing the header; no data is exported.
                    parse_trace(prefix + bytes(stride-header_bytes), rec.states[sid])
                elif actual < start:
                    raise RecordingError(f"{path}: incomplete first header cannot establish an overlapping boundary")
                start = actual
            starts.append(start)
        end = starts[-1] + (sizes[-1]+stride-1)//stride
        if expected_sweeps is not None:
            if expected_sweeps < end:
                raise RecordingError("expected_sweeps is less than the available TRC data")
            end = expected_sweeps
            source += ' / explicit expected_sweeps'
        counts = [b-a for a, b in zip(starts, starts[1:] + [end])]
    partitions = []
    details = []
    for path, start, count, size in zip(rec.trace_files, starts, counts, sizes):
        partitions.append(TracePartition(path, start, count, size))
        usable = min(size, count*stride)
        full, partial = divmod(usable, stride)
        ignored = size-usable
        if full < count or ignored:
            details.append(dict(file=str(path), start_sweep=start, expected_sweeps=count,
                                complete_sweeps=full, partial_bytes=partial,
                                zero_filled_sweeps=count-full, ignored_trailing_bytes=ignored))
    total = sum(counts)
    if not total:
        raise RecordingError("Cannot infer the size of an empty TRC session; provide expected_sweeps")
    report = dict(enabled=True, count_source=source, zero_filled_sweeps=sum(
        d['zero_filled_sweeps'] for d in details), partitions=details,
        ignored_trailing_bytes=sum(d['ignored_trailing_bytes'] for d in details),
        power_fill_dbm=MISSING_POWER_DBM, auxiliary_fill_value=0,
        note='Missing power uses -300 dBm placeholders. Missing headers have ticks=0 and blank times. zero_filled is the legacy recovery flag name.')
    if details:
        warnings.warn(f"Recovering {report['zero_filled_sweeps']} incomplete/missing sweeps with -300 dBm power; "
                      f"ignoring {report['ignored_trailing_bytes']} trailing bytes beyond validated partition boundaries; "
                      "see metadata.recovery and zero_filled flags", RuntimeWarning, stacklevel=3)
    return partitions, report


def read_sweep(rec, partition, index, stream):
    """Retain complete float32 values; fill missing power with -300 dBm."""
    rec._check_cancel()
    first_ids = rec.state_first_ids
    state = rec.states[bisect_right(first_ids, index)-1]
    stride = trace_record_size(state)
    offset = (index-partition.start)*stride
    stream.seek(offset)
    raw = stream.read(min(stride, max(0, partition.size-offset)))
    header_bytes = stride-4*state.value_count
    if len(raw) < header_bytes:
        return Sweep(index, state, 0, 0,
                     np.full((state.trace_count, state.points), MISSING_POWER_DBM, dtype=np.float32),
                     np.zeros(state.auxiliary_count, dtype=np.float32),
                     dict(zero_filled=True, timestamp_valid=False, recorded_value_count=0,
                          missing_header=True, available_bytes=len(raw)), str(partition.path), offset)
    sid = struct.unpack_from('<H', raw, 2)[0]
    if sid != state.state_id:
        raise RecordingError(f"{partition.path}:{offset}: inconsistent state/trace link")
    recorded = (len(raw)-header_bytes)//4
    keep = header_bytes+4*recorded  # Do not reinterpret a torn float's remaining bytes.
    missing_power = max(0, state.points*state.trace_count-recorded)
    padding = np.full(missing_power, MISSING_POWER_DBM, dtype='<f4').tobytes()
    padding += bytes(4*(state.value_count-recorded-missing_power))
    sweep = parse_trace(raw[:keep] + padding, state)
    if sweep.trace_id != index:
        raise RecordingError(f"{partition.path}:{offset}: expected trace {index}, got {sweep.trace_id}")
    header = dict(sweep.header)
    if len(raw) < stride:
        header.update(zero_filled=True, timestamp_valid=True, recorded_value_count=recorded,
                      available_bytes=len(raw))
    return Sweep(**(vars(sweep) | dict(header=header, source=str(partition.path), offset=offset)))
