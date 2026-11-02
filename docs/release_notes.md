## Recover incomplete TRC files without losing sweep positions

When an index expects 500 sweeps but a TRC file contains only 497, Workbench and
the native MATLAB exporter can now zero-fill the three missing positions and
continue. Complete samples in a torn final sweep are preserved; missing samples
become zero. Later partitions keep their original sweep IDs. Source files are
never changed. RPX nominal counts and per-file deviations are honored, so a
legitimate shorter partition is not automatically padded to a fixed size.

**Zero-fill incomplete TRC tails** defaults on in Workbench. MATLAB uses
`'RecoverIncomplete',true`. CLI/API remain strict unless `--recover-incomplete`
or `recover_incomplete=True` is supplied. If no RPX index declares the intended
length of a short final file, enter **Expected total sweeps**, set `expectedSweeps`
in the short MATLAB script, or use `--expected-sweeps`. This is the whole-session
total, not a per-file count.

Prefer MATLAB? Edit two paths in
[export_whole_session.m](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/matlab/export_whole_session.m)
and Run, keeping the five matlab/ files together. The native scripts read the
original STA/TRC session without Python or Data Link and save v7.3 parts for
partial access with matfile. Python GUI/CLI exports use SciPy MAT v5 parts.
See [MAT export instructions](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/docs/MAT_EXPORT.md).

Exports carry `zero_filled`, `recorded_value_counts`, `timestamp_valid` and a
recovery report. Missing-header timestamps stay blank with ticks 0 and elapsed
seconds NaN; they are never interpolated. Spectrograms switch to sweep indices
when times are unavailable, and playback labels zero-filled rows. Placeholder
zeros participate in plots/means/holds and are not measured 0 dBm; use the flags
to exclude them from measurements. Full corrupt records, missing partition files,
unsupported layouts, contradictory indexes and CRC failures still fail clearly.

Download **FieldFoxWorkbench-standalone.exe** for the single-file Windows x64
application, including Python 3.11 and runtime DLLs. Previous Ethernet, screenshot,
CSV, playback/hold, preview and CLI/API features remain available.

253 tests passed; one real-recording test skipped. MATLAB R2024b batch checks
passed on eleven synthetic sessions, including 497-of-500 recovery,
and verified cross-language agreement, exact timestamps, partial reads and
failure cleanup. Source and isolated frozen GUI/export self-tests passed.
Exact EXE size, SHA-256 and runtime audit are attached in build-report.json and
SHA256SUMS.txt. The enforced cap is 300 MiB. Real-instrument validation remains
pending; no vendor binaries, real recordings or decoded user data are published.
