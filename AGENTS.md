# Working on FieldFox Workbench

This repo contains an independently authored Python desktop app, socket browser
and recording decoder. Do not add vendor programs, DLLs, decompiled source, real
recordings, decoded user data, local settings, environments or build outputs to Git.
Test data must be synthesized in code. Preserve existing Python CLI/API entry points.

Use Tkinter, NumPy, Matplotlib and SciPy MAT I/O; keep network and file work off the
Tk thread. One owned worker at a time, bounded reads and cooperative cancellation.
Never leave analysis/build helpers running after timeout or shutdown. No bulk
decompilation is necessary for routine application work.

Do not guess binary layouts, axes, timestamp zones or amplitude units. Unknown
recording versions and unsupported IQ/density formats must fail clearly. EST is
fixed UTC-05:00 unless the user explicitly chooses a different source clock zone.

Network changes require explicit GUI actions. No automatic preset, discovery,
mode switch, uploads or deleting user files. Screenshot/CSV capture may create and
remove only its own unique temporary remote file. Protect existing local files.

Run `python -m pytest -q` and the offline `--self-test` after relevant edits.
Before publishing EXEs, build in the isolated pinned environment with
`build_windows.ps1` (onefile by default), pass the runtime audit, isolated frozen
check and 300 MiB size cap. When a diagnostic onedir build is requested, measure
the whole directory. Document mock/synthetic validation separately from real
hardware validation; no instrument was available for the initial release.
