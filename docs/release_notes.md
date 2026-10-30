## Playback on the trace page

The session playback bar now sits directly above the trace plot on **Traces / CSV**.
Drag the slider, use the keyboard/mouse wheel or Previous / Play / Pause / Next
while viewing the sweep. Speed, UTC/EST timestamps and maximum/minimum hold / power
mean controls are on the same page. The separate playback tab is removed, and the
first selected sweep appears automatically after a session loads. Playback's cursor
and displayed trace stay in sync.

## One-file Windows build

Download **FieldFoxWorkbench-standalone.exe** and run it. Python and its runtime DLLs
are included; no Python installation or `_internal` folder is required. The EXE is
approximately 70 MiB and extracts its runtime temporarily when launched. Windows
x64; unsigned binary. The default build script now produces only the single EXE.

The packaging process requires 64-bit CPython 3.11, preserves an incompatible local
build environment and uses a separate 3.11 environment, cleans PyInstaller caches,
explicitly bundles interpreter/VC DLLs, and audits the final bootloader cookie,
DLL names, architecture and hashes. It rejects mixed Python 3.13 runtimes. The
frozen GUI/export self-test runs from an empty directory with Python removed from
PATH and a temporary path containing spaces and Unicode.

The previous published EXE was verified to contain Python 3.11; the reported
`python313.dll` failure could not be reproduced without the exact error/binary.
This update adds build guards and diagnostic evidence rather than claiming that
an unobserved Windows-loader cause has been proven. Use the new EXE and compare
its SHA-256 with `SHA256SUMS.txt` if a startup issue persists.

204 tests passed; one real-recording test skipped because no recording was supplied.
See `build-report.json` for the frozen self-test, runtime audit, exact size and hash.
CLI tools, recording decoding, screenshots, CSV/MAT/PDF exports and fixed EST remain.
Live N9917B operation still needs hardware validation; network tests use a simulator.
