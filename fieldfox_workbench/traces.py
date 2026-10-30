"""Bounded CSV ingestion and trace analysis, independent of Tkinter."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import csv
import io
import json
import math
import re

import numpy as np

MAX_CSV_BYTES = 128 * 1024**2
MAX_CSV_ROWS = 1_000_000
MAX_CSV_CELLS = 4_000_000


@dataclass
class Table:
    columns: tuple[str, ...]
    values: np.ndarray
    source: str
    note: str = ""


@dataclass
class Trace:
    name: str
    x: np.ndarray
    y: np.ndarray
    x_label: str = "X"
    y_label: str = "Y"
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.x = np.asarray(self.x, dtype=np.float64)
        self.y = np.asarray(self.y, dtype=np.float64)
        if self.x.ndim != 1 or self.x.shape != self.y.shape or len(self.x) < 2:
            raise ValueError("A trace needs matching one-dimensional X/Y arrays with at least two points.")
        if len(self.x) > 1_000_000 or not np.isfinite(self.x).all() or not np.isfinite(self.y).all():
            raise ValueError("Trace exceeds one million points or contains non-finite values.")

    def statistics(self, lower=None, upper=None):
        for value in (lower, upper):
            if value is not None and not math.isfinite(value):
                raise ValueError("Limits must be finite numbers.")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("Lower limit exceeds upper limit.")
        high = int(np.argmax(self.y)); low = int(np.argmin(self.y))
        failed = np.zeros(len(self.y), dtype=bool)
        if lower is not None: failed |= self.y < lower
        if upper is not None: failed |= self.y > upper
        return dict(points=len(self.y), peak_x=float(self.x[high]), peak_y=float(self.y[high]),
                    min_x=float(self.x[low]), min_y=float(self.y[low]),
                    arithmetic_mean_y=float(self.y.mean()), failed_points=int(failed.sum()),
                    limit_result="UNTESTED" if lower is None and upper is None else ("FAIL" if failed.any() else "PASS"))

    def marker(self, x):
        if not math.isfinite(x): raise ValueError("Marker X must be finite.")
        index = int(np.argmin(abs(self.x-x)))
        return index, float(self.x[index]), float(self.y[index])


def read_csv(path, *, sweep=None, trace_slot=0, max_rows=MAX_CSV_ROWS) -> Table:
    """Read the largest rectangular numeric block, or one decoder long-form sweep.

    Metadata and column labels are retained as a note; no units are inferred or
    converted. Decoder CSVs are recognized by their explicit column names.
    """
    path = Path(path)
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds 128 MiB. Export a smaller section or use the session loader.")
    if not 2 <= max_rows <= MAX_CSV_ROWS: raise ValueError("max_rows must be 2..1,000,000")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(65536); stream.seek(0)
        try: delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error: delimiter = ","
        rows = csv.reader(stream, delimiter=delimiter)
        first = next(rows, [])
        if {"trace_id", "trace_slot", "power_dbm", "frequency_hz"} <= set(first):
            return _recording_csv(path, stream, delimiter, sweep, trace_slot, max_rows)
        if {"trace", "source", "x_label", "y_label", "point", "x", "y"} <= set(first):
            return _overlay_csv(path, stream, delimiter, trace_slot, max_rows)
        stream.seek(0)
        best = []; best_labels = (); block = []; block_labels = (); last_labels = ()
        total = cells = 0
        for row in csv.reader(stream, delimiter=delimiter):
            total += 1
            if total > max_rows: raise ValueError("CSV row limit exceeded; select a smaller input.")
            if len(row) > 128: raise ValueError("CSV has more than 128 columns.")
            try:
                values = [float(v.strip().replace("D", "E").replace("d", "e")) for v in row]
                numeric = len(values) >= 2
            except ValueError:
                numeric = False
            if numeric:
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("CSV numeric data contains a non-finite value.")
                cells += len(values)
                if cells > MAX_CSV_CELLS: raise ValueError("CSV numeric cell limit exceeded.")
                if block and len(values) != len(block[-1]):
                    if len(block) > len(best): best, best_labels = block, block_labels
                    block = []
                if not block: block_labels = last_labels
                block.append(values)
            else:
                if len(block) > len(best): best, best_labels = block, block_labels
                block = []
                if any(v.strip() for v in row): last_labels = tuple(v.strip() for v in row)
        if len(block) > len(best): best, best_labels = block, block_labels
    if len(best) < 2: raise ValueError("No rectangular numeric CSV block with at least two rows and columns was found.")
    count = len(best[0])
    labels = best_labels if len(best_labels) == count else tuple(f"Column {i+1}" for i in range(count))
    # Number prefixes disambiguate repeated vendor header labels in the GUI.
    labels = tuple(f"{i+1}: {label}" for i, label in enumerate(labels))
    return Table(labels, np.array(best, dtype=np.float64), str(path),
                 f"Loaded largest numeric block: {len(best)} rows × {count} columns; {total-len(best)} other rows. Check X/Y columns and units.")


def _overlay_csv(path, stream, delimiter, slot, max_rows):
    stream.seek(0); names = []; values = []; labels = None
    slot = int(slot)
    if slot < 0: raise ValueError("Overlay slot must be nonnegative.")
    for index, row in enumerate(csv.DictReader(stream, delimiter=delimiter)):
        if index >= max_rows: raise ValueError("CSV row limit exceeded.")
        name = row["trace"]
        # Repeated overlay names are disambiguated by a point-index reset.
        if row["point"] == "0": names.append(name)
        if len(names)-1 != slot: continue
        current_labels = (row["x_label"], row["y_label"])
        if labels is not None and labels != current_labels: raise ValueError("CSV axes change inside an overlay.")
        labels = current_labels; values.append((float(row["x"]), float(row["y"])))
    data = np.array(values, dtype=np.float64)
    if len(values) < 2 or not np.isfinite(data).all(): raise ValueError("Selected overlay has fewer than two valid points.")
    return Table(labels, data, str(path), f"Workbench CSV overlay {slot}: {names[slot]}")


def _recording_csv(path, stream, delimiter, sweep, slot, max_rows):
    stream.seek(0); reader = csv.DictReader(stream, delimiter=delimiter)
    chosen = None if sweep is None else int(sweep); slot = int(slot)
    if chosen is not None and chosen < 0 or slot < 0: raise ValueError("Sweep and trace slot must be nonnegative.")
    values = []; ticks = None; source_time = None; axis = None
    for index, row in enumerate(reader):
        if index >= max_rows: raise ValueError("CSV row limit exceeded. Use the binary session loader for large recordings.")
        if int(row["trace_slot"]) != slot: continue
        if chosen is None: chosen = int(row["trace_id"])
        if int(row["trace_id"]) != chosen: continue
        key = "frequency_hz" if row["frequency_hz"].strip() else "time_s"
        if axis is not None and axis != key: raise ValueError("Selected CSV sweep changes its X axis.")
        axis = key
        values.append((float(row[key]), float(row["power_dbm"])))
        ticks = row.get("timestamp_ticks"); source_time = row.get("timestamp_local_unspecified")
    if len(values) < 2: raise ValueError("The selected sweep/trace slot has fewer than two CSV points.")
    data = np.array(values, dtype=np.float64)
    if not np.isfinite(data).all(): raise ValueError("Selected CSV sweep contains non-finite values.")
    return Table((axis, "power_dbm"), data, str(path),
                 f"Decoder CSV: sweep {chosen}, slot {slot}; instrument time {source_time}, ticks {ticks}. Clock zone unspecified in CSV.")


def table_trace(table, x_column=0, y_column=1, x_scale=1.0, name=None):
    if not math.isfinite(x_scale) or x_scale <= 0: raise ValueError("X multiplier must be a positive finite number.")
    if not 0 <= x_column < len(table.columns) or not 0 <= y_column < len(table.columns):
        raise ValueError("Choose valid X and Y columns.")
    def label(column):
        text = re.sub(r"^\d+: ", "", table.columns[column])
        return {"frequency_hz": "Frequency (Hz)", "time_s": "Time (s)", "power_dbm": "Power (dBm)"}.get(text, text)
    x_label = label(x_column) + (f" (× {x_scale:g})" if x_scale != 1 else "")
    return Trace(name or Path(table.source).stem, table.values[:, x_column]*x_scale,
                 table.values[:, y_column], x_label, label(y_column),
                 table.source, {"import_note": table.note, "x_multiplier": x_scale})


def export_traces(traces, output, *, lower=None, upper=None):
    """Export all displayed overlays with explicit axes; never overwrite inputs."""
    from fieldfox_browser.client import destination
    traces = list(traces)
    if not traces: raise ValueError("Load a trace before exporting.")
    target = Path(output)
    with destination(target) as (_, stream):
        if target.suffix.lower() == ".mat":
            from scipy.io import savemat
            payload = {f"trace_{i+1}": dict(name=t.name, x=t.x[:, None], y=t.y[:, None],
                       x_label=t.x_label, y_label=t.y_label, source=t.source,
                       metadata_json=json.dumps(t.metadata, ensure_ascii=False),
                       lower_limit=np.nan if lower is None else lower,
                       upper_limit=np.nan if upper is None else upper)
                       for i, t in enumerate(traces)}
            savemat(stream, payload, do_compression=True, appendmat=False)
        elif target.suffix.lower() == ".csv":
            text = io.TextIOWrapper(stream, encoding="utf-8", newline="", write_through=True)
            try:
                writer = csv.writer(text)
                writer.writerow(["trace", "source", "x_label", "y_label", "point", "x", "y"])
                for trace in traces:
                    for i, (x, y) in enumerate(zip(trace.x, trace.y)):
                        writer.writerow([trace.name, trace.source, trace.x_label, trace.y_label, i, x, y])
                text.flush()
            finally:
                text.detach()  # destination owns the binary stream
        else: raise ValueError("Choose a .csv or .mat export filename.")
