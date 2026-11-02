# Release 0.1.8 validation

Validated on Windows x64 with Python 3.11.9 and the isolated packages pinned in
`requirements-build.txt`: NumPy 2.4.6, SciPy 1.17.1, Matplotlib 3.11.2, Pillow 12.3.0,
tzdata 2026.6 and PyInstaller 6.22.3.

## Executed checks

`python -m pytest -q`: **265 passed, 1 skipped**. The skipped integration test
requires `FIELDFOX_TEST_SESSION`; no real session was available. Playback slider/plot synchronization and rejection of mismatched, missing or mixed
Python/VC runtimes are included in the suite.

## Whole-session MAT export

The full-session exporter was checked across partitioned/flat stores, old GPSA,
RTSA, multiple stored trace slots, state/axis changes, zero span, exact int64
ticks, UTC/fixed-EST strings, continuous elapsed times, budgets forcing one-row
parts, late corrupted records, cancellation and protected destinations. The GUI
test exports all original rows/bins even with an unloaded section and invalid
unapplied plot controls, then confirms a second export chooses a new folder.
Closing the standalone viewer during export cancels its owned worker and waits
for compression and temporary-folder cleanup before destroying the window.

Native MATLAB R2024b Update 3 was actually run in batch against fifteen independently
generated sessions: two-slot/partitioned GPSA with an axis change, GPSA v1 flat
stores, RTSA v18, GPSA zero span, 497-of-500 indexed records, an unindexed gap
before sweep 500 in the next file, an explicit final count, torn float32 values,
a torn header, an empty TRC file, RPX per-file deviations, the exact 5500/5503
overlap, unused tail bytes, indexed overlaps and a whole repeated prefix. Native v7.3 and Python MAT parts agree on all
power values, auxiliary values, masks/state IDs, indices, axes, exact ticks,
UTC/EST strings and global elapsed times. MATLAB `matfile` partial reads passed.
Existing-output protection and cleanup after corruption in a later part passed.
These checks used synthetic data, not supplied real recordings. Reproduction:
[MAT export guide](MAT_EXPORT.md#reproduce-cross-language-validation).

Both recovery implementations validate present RPX CRCs and TRC counts; strict
native MATLAB mode scans physical records without validating indexes. Python
validates indexes in both modes. Recovery retains complete samples, fills missing
tail power with −300 dBm and records the replacements in metadata/arrays. Missing times
remain blank, ticks are 0 and elapsed seconds are NaN. The GUI test loads a torn
header, plots by sweep index, plays the placeholder with an explicit label and
exports the recovered data to MAT. Original files remain unchanged. CLI/API
strict defaults still reject truncation and mismatches. Three expected recovery
warnings in the suite report the synthetic short-file GUI load/export and
overlapping-boundary plot load. The overlap GUI test selects sweeps 5498–5502,
loads/plots them and plays sweep 5500 from the next file. Export tests compare
its values after splitting at 5000 sweeps. Negative cases check backward IDs,
conflicting repeated starts, invalid next-file clocks/states and partial first
headers. Original bytes are checked unchanged. The actual AutoSession14 files
have not been supplied, so no cause for their extra bytes is claimed.
Default part budgets bound array payloads, not total process memory; temporary
compression buffers, strings and MATLAB/SciPy working copies add memory.

File-preview checks cover UTF-8, UTF-16/32 BOMs, Windows-1252, incomplete UTF-8 at
the prefix boundary, empty files, binary hex output, bounded local reads,
fragmented remote blocks, size mismatches, line endings, cancellation, dedicated
connection closure and changing selections during a read. GUI tests verify
read-only local/remote previews, Find and a single-instance Help dialog.

The native Windows layout was inspected with independently generated synthetic
session data and a loopback file server: Explorer split/text preview, loaded
spectrogram, trace playback with both holds and the Help window. Window sizing
respects the Windows work area; plot controls scroll and the load action remains
visible. The application icon is independently authored; no vendor artwork is used.

The [screenshot tour](UI_TOUR.md) contains four native Windows captures from
0.1.4 with synthetic data. During capture, the spectrogram's export row was found
to be clipped by the plot's requested height. The export row and status now reserve
space below the plot before the expandable content is laid out. The final native
capture confirms that MAT, image, CSV and NPZ buttons are visible together.

Repeat source tests encountered intermittent Tcl/Tk script-read errors in this
PC's Microsoft Store Python installation. A separate 15-root Tk startup check
and the final complete suite passed; no runtime repair or specific cause is
claimed. The frozen application uses its bundled Tcl/Tk scripts and passed the
isolated startup/export check. Source-runtime errors remain a local environment
limitation to investigate if they recur.

Running-hold tests use nonmonotonic synthetic rows to check both extrema during
actual timed playback, forward jumps including intermediate peaks, backward seeks
without future-data leakage, reset windows, independent toggles, reload, retained
CSV overlays and MAT snapshots with interval metadata. The hold engine retains
only two point-sized buffers and references the existing selected data.

Tests cover GPSA/RTSA version branches, binary headers and record boundaries,
partition stores, negative/truncated data, RPX indexes/CRC, frequency axes, section
selection, CSV/NPZ/MAT, exact integer ticks, fixed EST and UTC, DST folds/gaps,
direct GUI launches, catalogue variants, fragmented binary transfers, cancellation,
temporary-file cleanup and changing remote files. New integration checks exercise
download → recording load → playback, screenshot/CSV capture → viewer, power mean,
markers/limits, overlay MAT round-trip, report output and a single-worker guard.

The release is a single EXE. Its frozen `--self-test RESULT_JSON` checks creation
of all five tabs, the read-only file preview and Help dialog, synthetic session
decode and TkAgg rendering, CSV columns,
markers/limits, section MAT round-trip with UTC/EST fields, overlay MAT, Pillow
image preview, PDF report, both running holds and reset. It verifies that playback
controls are embedded in the trace page and that changing the row updates the plot.
No network or instrument is used by this diagnostic. Temporary synthetic files
are removed.

The build requires 64-bit CPython 3.11, explicitly collects its interpreter and VC
runtime DLLs and inspects the completed executable's PyInstaller cookie and archive.
It rejects missing/wrong/mixed Python DLLs and verifies x64 PE headers plus runtime
hashes. PyInstaller uses a clean cache and version-specific work directory. The
frozen test is run with installed Python removed from PATH, no Python/venv/Conda
variables, an empty working directory, and a temporary directory containing spaces
and Unicode. This is environment isolation on the build PC, not a clean Windows VM.

The single-file EXE is approximately 70 MiB, below the enforced 300 MiB cap. Exact
artifact sizes, SHA-256, runtime hashes, Python version and startup-test output
are in the release's `build-report.json` and `SHA256SUMS.txt`. The one-file launcher
memory statistic excludes its child application and must not be interpreted as the
whole app's memory use. Large selected sections and plotting need additional RAM.

The earlier published 0.1.0 EXE was inspected and contains `python311.dll` plus both
VC runtime DLLs. It does not select Python 3.13. The reported `python313.dll` error
could not be reproduced without the exact affected binary/error; do not claim its
specific cause has been established. The 0.1.1 build records the runtime explicitly
and prevents reusing a mismatched local build environment. A failed startup after
Python initializes is written to JSON in diagnostic mode; DLL-loader failures
before Python starts are caught by the bounded runner and its log/timeout. No
analysis or build helper is intentionally left running after failure.

## Evidence limits and next hardware check

The decoder format is reconstructed from the inspected managed Data Link 8.2
assemblies and tested with independent synthetic binary fixtures. The user reported
that the earlier build worked on their recordings. No supplied complete recording
or Data Link reference CSV was available locally, so no real first/middle/last-sweep
frequency/power comparison is claimed.

SCPI operations were exercised with a loopback simulator using documented Keysight
commands. Real N9917B catalogue layouts, firmware-specific behavior, screenshot
creation/cleanup, data capture, format restoration, SA controls and early closure
of large file-preview transfers still need a live
instrument check. Connecting does not run these controls automatically. Start with
identity/catalogue and a completed session download, then test screenshot capture
and a held SA trace before applying settings. Keep captures and instrument inputs
outside this source repository.

The standalone binary contains the independently authored app
and third-party Python libraries. No proprietary Data Link binary, decompiled
source, actual user recording or derived user data is packaged or published.
