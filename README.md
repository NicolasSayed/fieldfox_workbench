# FieldFox Workbench

An independent, lightweight desktop application for the Keysight FieldFox N9917B
workflow: Ethernet files, recorded sessions, CSV traces, screenshots and reports.
It runs without Data Link, VISA, MATLAB, a web server or a browser runtime.

## Run on Windows

Download a build from [Releases](https://github.com/NicolasSayed/fieldfox_workbench/releases).
Extract the portable ZIP and run `FieldFoxWorkbench.exe` beside its `_internal`
folder. The standalone EXE is an alternative that unpacks its runtime temporarily
at each launch. Both include Python and all required libraries. The portable
folder starts faster. Unsigned builds may trigger Windows reputation prompts.

## Features

| Area | Available |
|---|---|
| Ethernet browser | Internal / SD / USB listings, filtering, recursive session downloads, progress, cancel, file SHA-256, JSON listings |
| Integrated loading | Downloaded sessions, CSV files and images open in the matching tab; local open and recent files |
| Recordings | GPSA / supported RTSA state and trace decoding, selected-section spectrogram, frequency/sweep selection, color limits/maps, zoom and pan |
| Playback | Sweep slider, previous/next/play, maximum/minimum hold and mean in linear power |
| CSV plotting | Header/metadata handling, X/Y column mapping, explicit X scaling, decoder sweep/slot selection, up to 16 compatible overlays |
| Analysis | Nearest-point markers, horizontal upper/lower limits with pass/fail counts, log X, axis ranges and JSON plot presets |
| Capture | Instrument screenshot PNG, formatted trace CSV, local image preview and unchanged image copies |
| SA operation | Current trace capture using actual X values and reported units, optional live polling, center/span/RBW, Hold/Run/Single |
| Export | Selected spectrogram MAT with UTC/EST, full-session CSV/NPZ, overlay CSV/MAT, PNG/PDF figures, multipage PDF report with notes, sources, plots and screenshot |
| Packaging | Reproducible PyInstaller scripts, portable and standalone builds, 300 MiB size gate and frozen-app self-test |

This covers the common data retrieval and analysis workflows. It is **not a full
Data Link replacement**: calibration-kit/cable editors, proprietary instrument
state editing, DTF transforms, DANL correction, Touchstone/Smith charts, IQ analysis
and remote recording configuration are not implemented. Firmware/options affect
SCPI availability. No live analyzer was available during development; network
features are tested against a loopback simulator, not claimed hardware-validated.

## Typical workflow

1. On **Instrument files**, enter the FieldFox IP address, port `5025` and a timeout.
   Connect / browse, then navigate internal/SD/USB storage. Download a **completed**
   `RTAUTOsessionXX` folder to a new local folder. Avoid recordings still being written.
2. The session opens on **Session spectrogram**. Set an inclusive first sweep,
   exclusive stop sweep, trace slot, frequency range and maximum displayed rows.
   Click **Load / update plot**. Large sections are thinned, not averaged.
3. Use **Session playback** for individual sweeps or hold/mean curves; curves appear
   on **Traces / CSV**. Export the spectrogram's selected section as MAT from its tab.
4. Open other CSV files to compare traces. Check the chosen X/Y columns and units;
   the generic reader takes the largest rectangular numeric block. Set X multiplier
   explicitly (e.g. `1000000` for MHz to Hz) and update the axis label. Decoder CSVs
   select a sweep/slot; Workbench overlay CSVs use Slot as the zero-based overlay.
5. On **Screenshots / capture**, capture the screen or formatted CSV to a new local
   file. Capture creates a UUID-named temporary file on the selected instrument
   drive and deletes only that file. Cleanup errors report its exact remote path.
6. Place markers, apply limits and export a PDF report on **Traces / CSV**. Limits
   test all imported points, including points outside the zoom. Reports include
   loaded trace plots, the session spectrogram and screenshot when present.

The source clock defaults to **EST, fixed UTC−05:00 all year**. Recording ticks have
no embedded time zone. MAT section exports include `timestamp_instrument`,
`timestamp_utc`, `timestamp_est`, DST-aware `timestamp_eastern`, original int64
ticks and converted UTC ticks. Use `America/New_York` only for an instrument clock
that follows daylight saving time; repeated times require a fold selection.

## Install from source / keep the CLIs

Python 3.11+ with Tkinter is required. The standard Windows Python installer includes
Tk. On Linux install your distribution's Tk package before creating the environment.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install .
.venv\Scripts\python -m fieldfox_workbench
```

IDE Run File works for `scripts/fieldfox_workbench.py` and
`fieldfox_workbench/app.py`, from any working directory. An optional session / CSV /
image path can be supplied on the command line.

```powershell
python -m fieldfox_workbench "D:\recordings\RTAUTOsession01"
python -m fieldfox_recording inspect "D:\recordings\RTAUTOsession01"
python -m fieldfox_recording plot "D:\recordings\RTAUTOsession01" --start-sweep 0 --stop-sweep 500 --export-mat section.mat --source-timezone EST
python -m fieldfox_recording export "D:\recordings\RTAUTOsession01" --format csv --output session.csv
python -m fieldfox_browser ls 192.168.1.100 '[INTERNAL]:\' --json
python -m fieldfox_browser download 192.168.1.100 '[INTERNAL]:\RTAUTOsession01' --recursive --output local-session
```

Use each command's `--help` for all options. Session decoding APIs remain available
as `from fieldfox_recording import FieldFoxRecording`; the socket browser API is
`from fieldfox_browser.client import FieldFoxClient`.

## Build the EXEs

On 64-bit Windows, install Python 3.11 and run:

```powershell
.\build_windows.ps1
# Or double-click build_windows.bat
# Optional: .\build_windows.ps1 -Mode onedir
```

The script creates an isolated `.venv-build`, installs the pinned
`requirements-build.txt`, and runs `scripts/build_exe.py` with
`packaging/FieldFoxWorkbench.spec`. It builds both variants, rejects a bundle above
**300 MiB**, and runs each executable's offline self-test. Outputs:

- `dist/FieldFoxWorkbench/FieldFoxWorkbench.exe` plus `_internal/` (keep together)
- `dist/FieldFoxWorkbench-windows-x64.zip` (portable release download)
- `dist/FieldFoxWorkbench-standalone.exe` (one-file alternative)
- `dist/build-report.json` and `dist/SHA256SUMS.txt`

The size check measures the **whole portable folder**, not just its launcher EXE.
Tk/Agg backends are bundled; Qt, notebooks, pandas and vendor programs are excluded.
Third-party notices are included. Build helpers have a 20-minute timeout and frozen
checks a 60-second timeout; owned process trees are terminated on timeout. Build on
the target OS; these scripts do not cross-compile Windows executables on Linux.

## Tests and resource limits

```powershell
python -m pip install '.[test]'
python -m pytest -q
python -m fieldfox_workbench --self-test build/source-selftest.json
```

Tests construct synthetic binary sessions and a loopback SCPI instrument. They cover
versions, truncation, direct launches, MAT clock conversions, TCP fragmentation,
transfer cleanup, capture lifecycle, trace format restoration, GUI handoffs,
playback, limits and reports. Self-test renders TkAgg figures and round-trips SciPy
MAT exports in the actual frozen app. It does not contact an instrument. See
[validation](docs/validation.md) for measured results and hardware limitations.

One worker runs at a time. Transfers stream in 64 KiB chunks; session plotting is
capped at 20 million cells and defaults to 2000 sweeps. CSV imports are capped at
128 MiB, one million rows, 128 columns and four million numeric cells. Overlays are
capped at 16 traces / two million points. Image preview is capped at 32 MiB / 16
million pixels. Full CSV exports stream; NPZ uses disk-backed power arrays but
retains per-sweep metadata in RAM. Cancellation is checked between records/socket
reads; final compression, rendering and cleanup finish before shutdown. No jobs
remain when the app exits. Preferences/recent paths are saved only in
`%APPDATA%\FieldFoxWorkbench\settings.json` on Windows.

Supported recordings are GPSA versions 1–18 and single-block, nonzero-span RTSA
versions 8–18. The folder name does not determine the format. RTSA density/multiblock
captures, IQ/VITA-49, unknown versions and partial stores fail explicitly. Generic
CSV import is not a proprietary state-file decoder. See
[binary format](docs/recording_format.md) and [protocol / provenance](docs/protocol.md).

No proprietary Data Link code, installer, DLL, user recording or decoded user data
is included. [Third-party notices](THIRD_PARTY_NOTICES.md).
