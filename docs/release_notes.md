## Screenshot walkthrough and visible spectrogram exports

See the [screenshot tour](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/docs/UI_TOUR.md)
for the actual Windows interface: Explorer text preview, session spectrogram,
playback with both running holds and the separate Help window. All screenshots
use synthetic data and a loopback instrument simulator.

The spectrogram now reserves space for its export buttons and status below the
plot, preventing the plot's requested height from pushing them out of the window.
The MAT, image, full CSV and full NPZ actions remain visible together while the
selection controls scroll independently.

Download **FieldFoxWorkbench-standalone.exe** for the single-file Windows x64
application. Python 3.11 and runtime DLLs are included. The professional theme,
Help / F1, bounded text/hex previews, playback holds, UTC/EST MAT exports and
Python CLI/API entry points from 0.1.3 remain available.

225 tests passed; one real-recording test skipped. The isolated frozen-app startup
and export checks passed, including both holds, preview and Help. Exact size and
SHA-256 are in `build-report.json` and `SHA256SUMS.txt`; the enforced size cap is
300 MiB. Live N9917B validation remains pending. No vendor programs, real user
recordings or decoded user data are included.
