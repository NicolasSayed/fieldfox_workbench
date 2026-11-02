## Fix Load / update plot at overlapping TRC boundaries

Fixes `invalid first trace 5500; expected trace 5503 or later` when the previous
file's byte length extends past the next partition's first sweep ID. Recovery
now validates the next header and uses that boundary, retaining trace 5500 from
the next file and reporting excluded bytes in the preceding file. No original
file is changed. Identical whole repeated prefixes are compared byte-for-byte;
bad or conflicting headers still fail. MATLAB and Python use the same policy.

Missing power still uses −300 dBm. Complete recorded samples, UTC/EST handling,
MAT exports, CLI entry points and the existing strict decoding option remain.
`metadata.recovery.ignored_trailing_bytes` and per-file entries report exclusions;
the GUI displays them after loading and export. Extra bytes are not silently
counted as additional sweeps.

**Fill incomplete TRC tails (−300 dBm)** defaults on in Workbench. MATLAB uses
`'RecoverIncomplete',true`. CLI/API remain strict unless `--recover-incomplete`
or `recover_incomplete=True` is supplied. If no RPX index declares the intended
length of a short final file, enter **Expected total sweeps**, set `expectedSweeps`
in the short MATLAB script, or use `--expected-sweeps`. This is the whole-session
total, not a per-file count.

Prefer MATLAB? Edit two paths in
[export_whole_session.m](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/matlab/export_whole_session.m)
and Run, keeping the five matlab/ files together. The native scripts read the
original STA/TRC session without Python or Data Link and save v7.3 parts for
partial access with matfile. Python GUI/CLI exports use SciPy MAT v5 parts.
See [MAT export instructions](https://github.com/NicolasSayed/fieldfox_workbench/blob/main/docs/MAT_EXPORT.md).

Exports carry `zero_filled` (legacy flag name), `recorded_value_counts`, `timestamp_valid`, `recovery_fill_dbm` and a
recovery report. Missing-header timestamps stay blank with ticks 0 and elapsed
seconds NaN; they are never interpolated. Spectrograms switch to sweep indices
when times are unavailable, and playback labels recovered rows. Placeholder
−300 values participate in plots/means/holds and are not measurements; use the flags
to exclude them from measurements. Full corrupt records, missing partition files,
unsupported layouts, contradictory indexes and CRC failures still fail clearly.

Download **FieldFoxWorkbench-standalone.exe** for the single-file Windows x64
application, including Python 3.11 and runtime DLLs. Previous Ethernet, screenshot,
CSV, playback/hold, preview and CLI/API features remain available.

265 tests passed; one real-recording test skipped. MATLAB R2024b batch checks
passed on fifteen synthetic sessions, including the 5500/5503 case and 497-of-500 recovery,
and verified cross-language agreement, exact timestamps, partial reads and
failure cleanup. Source and isolated frozen GUI/export self-tests passed.
Tests also verify that original recorded zeros remain unchanged. Re-export from
the original session to update an older MAT export; existing files are protected.
Exact EXE size, SHA-256 and runtime audit are attached in build-report.json and
SHA256SUMS.txt. The enforced cap is 300 MiB. Real-instrument validation remains
pending; no vendor binaries, real recordings or decoded user data are published.
