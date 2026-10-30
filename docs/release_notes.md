FieldFox Workbench combines Ethernet file browsing, recording-session loading,
spectrograms/playback, CSV overlays, markers/limits, screenshots, live SA traces,
basic SA controls and MAT/PDF exports in one lightweight Tkinter application.
The Python CLIs remain available in the source package.

**Recommended:** download `FieldFoxWorkbench-windows-x64.zip`, extract it and run
`FieldFoxWorkbench.exe`. Keep the `_internal` folder beside the executable.
`FieldFoxWorkbench-standalone.exe` is the one-file alternative; it extracts its
runtime temporarily when started. Neither build requires Python or Data Link.
Windows x64; unsigned binaries.

- Portable directory: approximately 162 MiB; ZIP download: approximately 70 MiB.
- Standalone EXE: approximately 69 MiB. Both are below the 300 MiB build limit.
- 186 tests passed; one real-recording test skipped because no recording was supplied.
- Both frozen executables passed GUI/rendering, synthetic decode, MAT UTC/EST,
  image preview, playback and PDF-report self-tests.
- EST defaults to fixed UTC−05:00; exact original ticks are preserved.

Download `SHA256SUMS.txt` to verify the assets and `build-report.json` for exact
sizes, hashes and self-test results. PyInstaller scripts and pinned dependencies
are included in the repository.

Live N9917B operation still needs hardware validation; network tests use a local
simulator. This is an independent common-workflow application, with the documented
feature gaps, not complete Data Link parity. No vendor binaries or user data are
included. See the README and validation notes before connecting an instrument.
