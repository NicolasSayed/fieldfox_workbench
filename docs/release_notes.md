## Export entire recording sessions to MATLAB

**Export full session MAT** on Session spectrogram now saves every original
sweep, stored trace slot and bin, regardless of the displayed plot selection.
Choose a parent folder; the app creates a new session_MAT folder with numbered
MAT parts and manifest.json. Existing exports are preserved with incremented
folder names. Section MAT export remains available for just the displayed data.

Parts split at settings changes, 5000 sweeps or a 128 MiB array payload budget.
Power dimensions are sweep × trace slot × point. Exact int64 recording ticks,
UTC, fixed EST (UTC−05:00), state IDs, masks and auxiliary values are included.
Process memory can exceed the array payload budget; the whole session is never
collected into one power matrix.

Prefer MATLAB? Edit two paths in
[export_whole_session.m](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/matlab/export_whole_session.m)
and Run, keeping the four matlab/ files together. The native scripts read the
original STA/TRC session without Python or Data Link and save v7.3 parts for
partial access with matfile. Python GUI/CLI exports use SciPy MAT v5 parts.
See [MAT export instructions](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/docs/MAT_EXPORT.md).

Download **FieldFoxWorkbench-standalone.exe** for the single-file Windows x64
application, including Python 3.11 and runtime DLLs. Previous Ethernet, screenshot,
CSV, playback/hold, preview and CLI/API features remain available.

235 tests passed; one real-recording test skipped. MATLAB R2024b batch checks
passed on four synthetic sessions, including multiple slots and changed axes,
and verified cross-language agreement, exact timestamps, partial reads and
failure cleanup. Source and isolated frozen GUI/export self-tests passed.
Exact EXE size, SHA-256 and runtime audit are attached in build-report.json and
SHA256SUMS.txt. The enforced cap is 300 MiB. Real-instrument validation remains
pending; no vendor binaries, real recordings or decoded user data are published.
