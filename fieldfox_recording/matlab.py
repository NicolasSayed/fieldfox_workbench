"""MATLAB-compatible section export, with SciPy as an optional dependency."""
from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Callable

import numpy as np

from .export import _destination
from .parser import RecordingError
from .timezones import convert_timestamps, elapsed_seconds

if TYPE_CHECKING:
    from .parser import FieldFoxRecording
    from .spectrogram import SpectrogramSection


def save_section_mat(rec: FieldFoxRecording, section: SpectrogramSection,
                     path: str | Path, *, source_timezone: str | None = "EST",
                     dst_fold: int | None = None) -> None:
    """Save exactly the selected/thinned rows and frequency bins, not an image.

    Power is single precision, rows are sweeps, columns are frequency bins.
    All one-dimensional numeric arrays and timestamp cell arrays are columns.
    """
    try:
        from scipy.io import savemat
    except ImportError as error:
        raise RecordingError("MAT export requires SciPy: python -m pip install '.[mat]'") from error
    times = convert_timestamps(section.timestamp_ticks, source_timezone, dst_fold, allow_missing=rec.recovery['enabled'])
    payload = {"frequency_hz": section.frequency_hz, "elapsed_s": section.elapsed_s,
               "power_dbm": section.power_dbm, "sweep_indices": section.sweep_indices,
               "timestamp_ticks": section.timestamp_ticks,
               "trace_slot": section.trace_slot, "effective_step": section.effective_step,
               "metadata_json": json.dumps(rec.metadata), **times}
    if section.zero_filled is not None:
        payload['zero_filled'] = section.zero_filled
        payload['recorded_value_counts'] = section.recorded_value_counts
    for name, value in list(payload.items()):
        if isinstance(value, np.ndarray) and value.dtype.kind == "U":
            payload[name] = value.astype(object)  # MATLAB cell array of exact ISO strings
    with _destination(rec, path) as temporary:
        savemat(temporary, payload, appendmat=False, do_compression=True,
                long_field_names=True, oned_as="column")


def save_session_mat(rec: FieldFoxRecording, path: str | Path, *,
                     chunk_sweeps: int = 5000, max_part_mib: float = 128,
                     source_timezone: str | None = "EST", dst_fold: int | None = None,
                     progress: Callable[[int, int], None] | None = None) -> dict:
    """Export every sweep, trace slot and bin to a new folder of MAT files.

    Parts stop at state changes, chunk_sweeps, or the numeric payload budget.
    max_part_mib limits array payload, not peak process memory (SciPy also
    compresses and copies arrays). No plot selection/thinning is applied.
    Cancellation uses rec.cancel_event. The final folder appears only on success.
    """
    try:
        from scipy.io import savemat
    except ImportError as error:
        raise RecordingError("MAT export requires SciPy: python -m pip install '.[mat]'") from error

    if isinstance(chunk_sweeps, bool) or not isinstance(chunk_sweeps, int) or chunk_sweeps < 1:
        raise RecordingError("chunk_sweeps must be a positive integer")
    if not math.isfinite(max_part_mib) or not 0 < max_part_mib <= 512:
        raise RecordingError("max_part_mib must be positive and at most 512 MiB")
    target = Path(path).resolve()
    if target.is_relative_to(rec.path.resolve()):
        raise RecordingError("Export destination must be outside the original session directory")
    if target.exists():
        raise RecordingError(f"Export destination already exists: {target}")
    state = rec.states[0]
    # Include per-row numeric fields plus a reserve for timestamp/header strings.
    bytes_per_row = 4 * (state.trace_count * state.points + state.auxiliary_count) + 1024
    capacity = min(chunk_sweeps, int(max_part_mib * 1024**2) // bytes_per_row)
    if capacity < 1:
        raise RecordingError("MAT part budget is too small for one complete sweep")
    capacity = min(capacity, len(rec))
    manifest = {"schema_version": 1, "complete": True,
                "source_session": str(rec.path.resolve()), "metadata": rec.metadata,
                "source_timezone": source_timezone, "dst_fold": dst_fold,
                "power_dimensions": ["sweep", "trace_slot", "point"],
                "index_base": 0, "stop_sweep_exclusive": True, "parts": []}
    rec._check_cancel()
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent, prefix=".fieldfox-mat-") as staging:
        directory = Path(staging) / "session"
        directory.mkdir()
        power = np.empty((capacity, state.trace_count, state.points), dtype=np.float32)
        auxiliary = np.empty((capacity, state.auxiliary_count), dtype=np.float32)
        ticks = np.empty(capacity, dtype=np.int64)
        indices = np.empty(capacity, dtype=np.int64)
        masks = np.empty(capacity, dtype=np.uint8)
        filled = np.empty(capacity, dtype=bool)
        recorded_counts = np.empty(capacity, dtype=np.uint32)
        headers = []
        count = 0
        current_state = None
        first_tick = None

        def flush():
            rec._check_cancel()
            times = convert_timestamps(ticks[:count], source_timezone, dst_fold, allow_missing=rec.recovery['enabled'])
            axis_name = "time_axis_s" if current_state.span_hz == 0 else "frequency_hz"
            axis = getattr(current_state, axis_name)
            payload = {"power_dbm_traces": power[:count],
                       "auxiliary_values": auxiliary[:count],
                       "timestamp_ticks": ticks[:count], "sweep_indices": indices[:count],
                       "trace_masks": masks[:count],
                       "state_ids": np.full(count, current_state.state_id, dtype=np.uint16),
                       "trace_slot_indices": np.arange(state.trace_count, dtype=np.int32),
                       "elapsed_s": elapsed_seconds(ticks[:count], first_tick),
                       "zero_filled": filled[:count], "recorded_value_counts": recorded_counts[:count],
                       axis_name: axis, "axis_kind": axis_name,
                       "state_id": current_state.state_id,
                       "metadata_json": json.dumps(current_state.as_dict()),
                       "trace_headers_json": np.array([json.dumps(h) for h in headers], dtype=object),
                       **times}
            for name, value in list(payload.items()):
                if isinstance(value, np.ndarray) and value.dtype.kind == "U":
                    payload[name] = value.astype(object)
            filename = f"part_{len(manifest['parts']) + 1:06d}.mat"
            savemat(directory / filename, payload, appendmat=False, do_compression=True,
                    long_field_names=True, oned_as="column")
            rec._check_cancel()
            manifest["parts"].append({"file": filename, "state_id": current_state.state_id,
                                      "start_sweep": int(indices[0]),
                                      "stop_sweep": int(indices[count-1]) + 1,
                                      "n_sweeps": count, "axis_kind": axis_name})
            if progress:
                progress(int(indices[count-1]) + 1, len(rec))

        # The ordinary iterator validates every record/link, including boundaries.
        for sweep in rec:
            if count and (count == capacity or sweep.state.state_id != current_state.state_id):
                flush()
                count = 0
                headers.clear()
            current_state = sweep.state
            if first_tick is None:
                first_tick = sweep.ticks
            power[count] = sweep.power_dbm_traces
            auxiliary[count] = sweep.auxiliary_values
            ticks[count], indices[count], masks[count] = sweep.ticks, sweep.trace_id, sweep.trace_mask
            filled[count] = sweep.header.get('zero_filled', False)
            recorded_counts[count] = sweep.header.get('recorded_value_count', sweep.state.value_count)
            headers.append(sweep.header)
            count += 1
        if count:
            flush()
        rec._check_cancel()
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if target.exists():
            raise RecordingError(f"Export destination already exists: {target}")
        directory.rename(target)
    return manifest
