"""Explicit, documented SCPI operations for screen capture and SA traces."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import math
import uuid

import numpy as np

from fieldfox_browser.client import BrowserError, RemotePath
from .traces import Trace


def complete(connection):
    if connection.text("*OPC?").strip() != "1":
        raise BrowserError("Instrument did not acknowledge operation completion.")


def capture_file(client, output, *, kind="png", drive="INTERNAL", cancel=None, progress=None):
    """Save a uniquely named instrument file, fetch it, remove only our own file.

    A cleanup failure is returned as a warning with the exact generated path.
    Never delete or replace an existing user-selected remote file.
    """
    if kind not in {"png", "csv"}: raise ValueError("Capture kind must be png or csv")
    target = Path(output).expanduser().absolute()
    if target.exists() or target.is_symlink(): raise FileExistsError(target)
    remote = RemotePath.parse(f"[{drive}]:\\").child(f"ffwb_{uuid.uuid4().hex}.{kind}")
    warning = None; created = False; result = None; primary_error = None
    try:
        with client.connection(cancel) as connection:
            # Check for even the extremely unlikely UUID collision before writing.
            catalog = connection.catalog(remote.parent)
            if any(e.name.casefold() == remote.name.casefold() for e in catalog.entries):
                raise BrowserError("Generated capture filename already exists; try again.")
            command = "MMEM:STOR:IMAG" if kind == "png" else "MMEM:STOR:FDAT"
            created = True  # A send/OPC timeout may still leave a newly created file.
            connection._send(f'{command} "{remote}"')
            complete(connection)
            saved = next((e for e in connection.catalog(remote.parent).entries if e.name == remote.name and not e.is_dir), None)
            if saved is None: raise BrowserError("Capture was not created. Check writable storage, mode and firmware support.")
            result = connection.download(remote, target, expected_size=saved.size,
                                         max_bytes=32*1024**2 if kind == "png" else 128*1024**2,
                                         progress=progress)
    except Exception as error:
        primary_error = error
        raise
    finally:
        if created:
            try:
                # Cancellation closes the transfer, but must not suppress cleanup.
                with client.connection() as cleanup:
                    cleanup._send(f'MMEM:DEL "{remote}"'); complete(cleanup)
            except Exception as error:
                warning = f"Remove temporary instrument file {remote} manually: {error}"
                if progress: progress(warning)
                # Keep cleanup information when the main operation also failed.
                if primary_error is not None: primary_error.add_note(warning)
    result["warning"] = warning
    return result


def numbers(response):
    fields = response.strip().split(",")
    if len(fields) < 2 or len(fields) > 1_000_000:
        raise BrowserError("Trace point count is outside the supported bounds.")
    try: result = np.array([float(v) for v in fields], dtype=np.float64)
    except ValueError as error: raise BrowserError("Expected ASCII trace data from the analyzer.") from error
    if not np.isfinite(result).all(): raise BrowserError("Trace contains non-finite values.")
    return result


def read_sa_trace(client, *, slot=1, cancel=None):
    """Read a snapshot, using the trace's actual X values, restoring data format."""
    if slot not in {1, 2, 3, 4}: raise ValueError("SA trace number must be 1..4")
    with client.connection(cancel) as connection:
        identity = connection.text("*IDN?")
        mode = connection.text("INST:SEL?").strip().strip('"')
        if mode != "SA": raise BrowserError(f"Live trace capture currently supports SA mode; instrument reports {mode}.")
        unit = connection.text("SENS:AMPL:UNIT?").strip().strip('"')
        old_format = connection.text("FORM:DATA?").strip()
        if not old_format or len(old_format) > 64 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789., +-'\"" for c in old_format):
            raise BrowserError("Unrecognized data-format response; refusing to change the format.")
        try:
            connection._send("FORM:DATA ASC")
            x = numbers(connection.text(f"TRAC{slot}:XVAL?"))
            y = numbers(connection.text(f"TRAC{slot}:DATA?"))
            # Refuse a changing axis rather than synthesizing an incorrect one.
            if not np.array_equal(x, numbers(connection.text(f"TRAC{slot}:XVAL?"))):
                raise BrowserError("Trace X values changed during capture. Hold the instrument sweep and retry.")
            span = float(connection.text("SENS:FREQ:SPAN?"))
        finally:
            # Use a fresh connection after transport failure/cancellation.
            with client.connection() as restore:
                restore._send(f"FORM:DATA {old_format}"); complete(restore)
    if x.shape != y.shape: raise BrowserError("Instrument returned different X/Y point counts.")
    captured = datetime.now(timezone.utc).isoformat()
    return Trace(f"Live SA trace {slot}", x, y, "Time (s)" if span == 0 else "Frequency (Hz)", "Power (dBm)" if unit.upper() == "DBM" else unit,
                 client.host, {"identity": identity, "mode": mode, "captured_pc_utc": captured,
                               "reported_amplitude_unit": unit,
                               "coherence": "Current trace, acquisition not stopped; X axis checked before/after."})


def sa_settings(client, cancel=None):
    with client.connection(cancel) as connection:
        if connection.text("INST:SEL?").strip().strip('"') != "SA":
            raise BrowserError("SA controls require the instrument to already be in SA mode.")
        return {name: float(connection.text(command + "?")) for name, command in
                [("center_hz", "SENS:FREQ:CENT"), ("span_hz", "SENS:FREQ:SPAN"),
                 ("rbw_hz", "SENS:BAND:RES")]}


def apply_sa_settings(client, *, center_hz, span_hz, rbw_hz, cancel=None):
    values = (center_hz, span_hz, rbw_hz)
    if not all(math.isfinite(v) for v in values) or center_hz <= 0 or span_hz < 0 or rbw_hz <= 0:
        raise ValueError("Center and RBW must be positive, span nonnegative, and all settings finite.")
    with client.connection(cancel) as connection:
        if connection.text("INST:SEL?").strip().strip('"') != "SA": raise BrowserError("Select SA mode on the FieldFox first.")
        for command, value in zip(("SENS:FREQ:CENT", "SENS:FREQ:SPAN", "SENS:BAND:RES"), values):
            connection._send(f"{command} {value:.15g}")
        complete(connection)
        error = connection.text("SYST:ERR?")
        if not error.split(",", 1)[0].strip() in {"0", "+0"}:
            raise BrowserError(f"Instrument reported {error}. Some settings may have changed; read settings again.")
    return sa_settings(client, cancel)


def sweep_action(client, action, cancel=None):
    commands = {"Hold": "INIT:CONT 0", "Run": "INIT:CONT 1", "Single": "INIT:CONT 0"}
    if action not in commands: raise ValueError("Unknown sweep action")
    with client.connection(cancel) as connection:
        connection._send(commands[action]); complete(connection)
        if action == "Single":
            connection._send("INIT:IMM"); complete(connection)
