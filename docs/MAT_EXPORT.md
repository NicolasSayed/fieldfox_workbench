# Whole-session MATLAB export

This export reads the original session, including all sweeps, stored trace slots,
bins, auxiliary values, masks and state IDs. It does not use the thinned display
section. Supported formats are unchanged: GPSA versions 1–18 and scalar,
single-block, nonzero-span RTSA versions 8–18. IQ and density formats are rejected.
Use a completed local session rather than one still being recorded.

## Native MATLAB: edit two paths and run

Keep these files together in `matlab/`:

- `export_whole_session.m`: short script with editable input/output paths.
- `export_fieldfox_session.m`: full-session exporter.
- `read_fieldfox.m`: independent STA/TRC reader.
- `fieldfox_times.m`: exact ticks, instrument/UTC/EST/Eastern time conversions.
- `fieldfox_trace_layout.m`: per-partition counts, RPX CRCs and short-tail recovery.

Open `export_whole_session.m`, change its paths and press Run. Alternatively:

```matlab
addpath('path/to/fieldfox_workbench/matlab');
manifest = export_fieldfox_session('D:\recordings\RTAUTOsession01', ...
    'D:\exports\run1_MAT', 'SweepsPerPart', 5000, ...
    'MaxPartMiB', 128, 'SourceTimeZone', 'EST');
```

The output must be a **new folder outside the original session**. Both native
MATLAB and Python stage their own output and expose the final folder only after
successful completion. Workbench chooses an unused name automatically. For CLI
or MATLAB calls, choose another output name if it already exists.

The MATLAB script enables short-tail recovery by default and writes **v7.3** files. MATLAB's
[`matfile`](https://www.mathworks.com/help/matlab/ref/matlab.io.matfile.html)
supports reading just part of an array from these files:

```matlab
m = matfile('D:\exports\run1_MAT\part_000001.mat');
firstSweep = reshape(m.power_dbm_traces(1,1,:), [], 1);
```

MATLAB R2024b Update 3 was used for the cross-language checks. The native reader
checks present RPX index CRCs and TRC counts in recovery mode; strict native mode
scans physical records without validating the index. Python checks present
indexes in both modes. Native MAT files
retain raw STA headers in `states`; Python parts also retain decoded per-sweep
headers as `trace_headers_json`. This is an analysis export, not an archival copy
of every original byte. Keep the original recording for provenance.

## Workbench, Python CLI and API

Select a session folder on **Session spectrogram**, then **Export full session
MAT**. Choose the parent folder; the output is `<session>_MAT`, `_MAT_2`, etc.
This works before plotting and ignores all plot selection controls. Workbench
runs the export on its existing worker and reports sweep progress. Cancel is
checked between records/parts; compression already in progress finishes first.

```powershell
python -m fieldfox_recording export "D:\recordings\RTAUTOsession01" --format mat --output "D:\exports\run1_MAT" --chunk-sweeps 5000 --max-part-mib 128 --source-timezone EST
```

```python
from fieldfox_recording import FieldFoxRecording
rec = FieldFoxRecording.open(r'D:\recordings\RTAUTOsession01')
manifest = rec.to_mat(r'D:\exports\run1_MAT', chunk_sweeps=5000,
                      source_timezone='EST')
```

Python writes compressed MAT v5 parts using SciPy. Load one part at a time with
`load`; efficient `matfile` partial reads require the native script's v7.3 output.
No HDF5 dependency is added to the Python app. The existing **Export section
.mat** button still saves exactly the displayed selection as before.

## Part layout

`manifest.json` lists files in order, each part's state, zero-based start sweep
and exclusive stop sweep. It includes session metadata and the declared source
clock zone. Even a small session uses this folder layout.

| MAT variable | Meaning |
|---|---|
| `power_dbm_traces` | Single precision; sweep × trace slot × point |
| `frequency_hz` | Column axis for frequency sweeps |
| `time_axis_s` | Column axis for supported GPSA zero-span recordings |
| `axis_kind` | Which of those axes to use |
| `sweep_indices` | Original zero-based sweep indices, int64 |
| `trace_slot_indices` | Zero-based stored trace slots; MATLAB slot 1 corresponds to index 0 |
| `timestamp_ticks` | Original exact int64 .NET ticks (100 ns), unspecified instrument clock |
| `timestamp_ticks_utc` | Converted exact int64 UTC ticks using declared clock zone |
| `timestamp_instrument`, `timestamp_utc`, `timestamp_est`, `timestamp_eastern` | ISO strings with seven fractional digits |
| `source_timezone`, `timestamp_conversion` | Declared clock assumption and conversion description |
| `elapsed_s` | Seconds from the **first sweep of the session**, continuous across parts |
| `zero_filled` | True for any sweep with a missing header or payload values |
| `recorded_value_counts` | Count of complete original float32 values (flattened power slots, then auxiliary fields); remaining values were zero-filled |
| `timestamp_valid` | False when a missing header prevents recovering its timestamp |
| `state_ids`, `trace_masks`, `auxiliary_values` | Per-sweep state, stored trace mask and unscaled auxiliary fields |
| `metadata_json` | State metadata in Python parts; session summary in native parts |

Part boundaries respect state changes, even when the frequency axis stays the
same. For zero span use `time_axis_s`; frequency arrays are absent or empty.
Settings or frequency axes can differ between parts: process them separately
unless you explicitly account for those differences. A trace mask is preserved
without replacing or dropping stored slots. Unknown auxiliary fields remain raw.

The defaults are at most 5000 sweeps and a 128 MiB array payload budget per part.
String conversion, compression and temporary copies require additional RAM;
lower `SweepsPerPart` / `chunk_sweeps` or `MaxPartMiB` / `max_part_mib` if needed.
Parts are bounded rather than accumulating the entire session in memory.

EST is **fixed UTC−05:00 all year**. The recording does not encode a time zone.
Choose `America/New_York` only if the instrument clock follows DST; ambiguous
hours require `DSTFold`, 0/1 in MATLAB, or `--dst-fold 0/1` in Python. An empty
source zone preserves instrument times and leaves converted fields empty.

## Short TRC recovery

Workbench's **Zero-fill incomplete TRC tails** and MATLAB's `RecoverIncomplete`
default to enabled. Python CLI/API decoding defaults to strict; use
`--recover-incomplete` or `FieldFoxRecording.open(path, recover_incomplete=True)`.

For 500 expected records with only 497 present, the last three positions contain
zeros and later partitions retain their original sweep IDs. Available complete
samples in a torn sweep are retained; a torn float itself becomes zero. A torn
or absent header means that entire sweep is zero-filled. The source files are
never padded or rewritten. The manifest's `metadata.recovery` identifies affected
files, expected/present counts and how the counts were determined.

RPX FDAT/fDEV counts are checked, including legitimate shorter partitions. Without
an index, the next file's first sweep ID can establish a gap. The intended length
of a final file containing 497 complete records cannot be inferred as 500 from
its size alone. If no index declares it, specify **Expected total sweeps** in the
GUI, `expectedSweeps` in `export_whole_session.m`, `'ExpectedSweeps',500` in MATLAB,
or `--expected-sweeps 500` in the CLI. The number refers to the entire session.

Missing timestamps are not interpolated: ticks and converted UTC ticks are `0`,
timestamp strings are empty, `timestamp_valid` is false and elapsed seconds are
`NaN`. If the session's very first timestamp is missing, all session-relative
elapsed seconds are unknown. MATLAB plots should use `double(d.sweep_indices)`
as the vertical axis when `any(~isfinite(d.elapsed_s))`. The Python spectrogram
does that automatically and labels the axis accordingly.

**Placeholder zeros are not measured 0 dBm.** They participate in existing
plot/hold/mean operations. Exclude rows using `~d.zero_filled` (or use
`recorded_value_counts` for partial-row processing) when computing measurements.
Missing partition files, unsupported formats, invalid full records, contradictory
indexes and CRC failures remain errors. Disable recovery for strict verification.

## Process all parts in MATLAB

```matlab
folder = 'D:\exports\run1_MAT';
index = jsondecode(fileread(fullfile(folder,'manifest.json')));
for k = 1:numel(index.parts)
    d = load(fullfile(folder,index.parts(k).file));
    % All sweeps of the first stored trace, including singleton final parts:
    p = reshape(d.power_dbm_traces(:,1,:), numel(d.sweep_indices), []);
    % Analyze/save results here, then let the next iteration replace this part.
end
```

## Reproduce cross-language validation

From the repository root, generate a new directory of synthetic fixtures:

```powershell
python -m tests.matlab.generate_fixtures "D:\temp\fieldfox_mat_test"
```

Then in MATLAB:

```matlab
addpath('path/to/fieldfox_workbench/tests/matlab');
test_full_session('D:\temp\fieldfox_mat_test');
```

Checks compare native MAT files to Python exports for every slot/value, axes,
auxiliary fields, masks, exact ticks, UTC/EST strings and elapsed times. Fixtures
cover old GPSA, partitioned GPSA with two slots/settings changes, RTSA and zero
span, 497-of-500 records, next-file gaps, explicit final counts, torn floats,
missing headers, empty files, RPX deviations, existing-output protection, late corruption cleanup and v7.3 partial
reads. All fixtures are generated in code. This validates cross-language
agreement on synthetic sessions, not a new comparison against an instrument or
Data Link CSV export.
