## Professional desktop layout and Explorer previews

The app now has a consistent light theme, clearer spacing, a branded icon and an
activity indicator. The Help tab is replaced by a **Help · F1** button that opens
a scrollable guide. Plot controls and CSV column mapping sit in scrollable
sidebars; session playback, max hold and min hold remain above the trace plot.

The **Explorer** has a resizable, read-only file preview beside the folder list.
Select a remote file or open a local file to view text, with encoding and byte
counts, Find next and Wrap. Binary files show hex. Reads are capped at 256 KiB,
hex output at 4 KiB, and larger files are marked prefix only. Remote preview uses
a dedicated read connection and closes it after the prefix; it makes no remote
changes. Stale selection results are discarded.

Download **FieldFoxWorkbench-standalone.exe** and run it: a single Windows x64
EXE, approximately 70 MiB, including Python 3.11 and runtime DLLs. No Python
installation or adjacent `_internal` folder is needed. Python CLI/API entry
points, UTC/EST MAT export and running playback holds remain available.

**225 tests passed; one skipped** because no real recording was supplied. The
offline frozen-app test covers all five tabs, the preview and Help window, both
running holds, rendering, decoding, UTC/EST MAT export, images and PDF reports.
The desktop layout was also inspected with synthetic data and a loopback server.
Exact size, SHA-256 and runtime checks are in `build-report.json` and
`SHA256SUMS.txt`. The enforced EXE size cap remains 300 MiB.

Live N9917B functionality still needs hardware validation, including early closure
of large preview transfers. Network tests use a simulator; no vendor programs,
real recordings or decoded user data are included.
