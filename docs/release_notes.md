## Running max hold and min hold during playback

Enable **Max hold**, **Min hold**, or both on **Traces / CSV**. Both hold curves stay
visible alongside the current sweep and update as playback advances. They can be
toggled without pausing. Max hold is red/dashed; min hold is green/dotted.

- **Reset holds here** starts a new interval at the current sweep without pausing.
- Forward jumps include intervening selected rows. Backward seeks recalculate to
  the cursor so later peaks/troughs do not leak into earlier views.
- Moving before a reset reanchors there; loading a section or restarting playback
  from the end starts over.
- Holds cover the loaded selection only. Rows omitted by step/thinning do not count.
- Compatible CSV overlays and the fixed section mean remain visible during playback.
- CSV/MAT exports and reports include the displayed holds; MAT metadata includes
  the hold interval. Exported snapshots are independent of later playback updates.

Holds reuse the selected section and keep two point-sized extrema buffers. The
recording is not reread per frame. The Section mean button is a separate fixed
summary in linear power over the whole selected section.

Download **FieldFoxWorkbench-standalone.exe** and run it: a single Windows x64 EXE,
approximately 70 MiB, including Python 3.11 and runtime DLLs. No Python install or
adjacent `_internal` folder is needed. The 300 MiB cap and runtime audit remain.

213 tests passed; one test skipped because no real recording was supplied. The
frozen self-test also checks both running holds, updates and reset alongside
rendering, decoding, UTC/EST MAT export, image preview and PDF reports. Exact sizes,
SHA-256 and runtime checks are in `build-report.json` and `SHA256SUMS.txt`.
Live N9917B functionality still needs hardware validation; network tests use a simulator.
