# Release 0.1.0 validation

Validated on Windows x64 with Python 3.11.9 and the isolated packages pinned in
`requirements-build.txt`: NumPy 2.4.6, SciPy 1.17.1, Matplotlib 3.11.2, Pillow 12.3.0,
tzdata 2026.6 and PyInstaller 6.22.3.

## Executed checks

`python -m pytest -q -rs`: **186 passed, 1 skipped**. The skipped integration test
requires `FIELDFOX_TEST_SESSION`; no real session was available. A subsequent
focused MAT overlay test also passed after adding exported trace metadata.

Tests cover GPSA/RTSA version branches, binary headers and record boundaries,
partition stores, negative/truncated data, RPX indexes/CRC, frequency axes, section
selection, CSV/NPZ/MAT, exact integer ticks, fixed EST and UTC, DST folds/gaps,
direct GUI launches, catalogue variants, fragmented binary transfers, cancellation,
temporary-file cleanup and changing remote files. New integration checks exercise
download → recording load → playback, screenshot/CSV capture → viewer, power mean,
markers/limits, overlay MAT round-trip, report output and a single-worker guard.

Each frozen executable was actually run with `--self-test RESULT_JSON`. Both
passed creation of all seven Tk tabs, synthetic session decode and TkAgg rendering,
CSV columns, markers/limits, section MAT round-trip with UTC/EST fields, overlay
MAT, Pillow image preview, PDF report and playback/maximum hold. No network or
instrument is used by this diagnostic. Temporary synthetic files are removed.

Measured build sizes (rounded; exact bytes and SHA-256 are release assets):

| Build | Size |
|---|---:|
| Complete portable application directory, including runtime | approximately 162 MiB |
| Portable ZIP download | approximately 70 MiB |
| Standalone EXE download | approximately 69 MiB |
| Enforced maximum per complete bundle | 300 MiB |

The portable executable's measured peak working set during the small synthetic
self-test was approximately **168 MiB**. This is not a prediction for large data:
larger selected sections, plot rendering and report generation need additional
memory. The standalone launcher's memory statistic excludes its child application
and must not be interpreted as the whole app's memory use. Default display limits,
explicit caps, one worker and lazy SciPy imports help keep normal use modest.

The first packaging attempt exposed a module-name collision between a source
launcher and the package. The production spec uses a distinct launcher in
`packaging/`, and both corrected binaries passed their checks. A failed frozen
startup is written to JSON in diagnostic mode; bounded build runners terminate
their owned helper trees on timeout.

## Evidence limits and next hardware check

The decoder format is reconstructed from the inspected managed Data Link 8.2
assemblies and tested with independent synthetic binary fixtures. The user reported
that the earlier build worked on their recordings. No supplied complete recording
or Data Link reference CSV was available locally, so no real first/middle/last-sweep
frequency/power comparison is claimed.

SCPI operations were exercised with a loopback simulator using documented Keysight
commands. Real N9917B catalogue layouts, firmware-specific behavior, screenshot
creation/cleanup, data capture, format restoration and SA controls still need a live
instrument check. Connecting does not run these controls automatically. Start with
identity/catalogue and a completed session download, then test screenshot capture
and a held SA trace before applying settings. Keep captures and instrument inputs
outside this source repository.

The portable folder and standalone binary contain the independently authored app
and third-party Python libraries. No proprietary Data Link binary, decompiled
source, actual user recording or derived user data is packaged or published.
