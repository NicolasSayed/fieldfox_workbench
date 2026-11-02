# FieldFox GPSA/RTSA trace Record/Playback format (static reconstruction)

This document describes the **supplied Data Link 8.2.9762.18414 code**. It has
not been validated against instrument recordings. Every confirmed claim below
means confirmed by static code, not observed in a real session. Exact artifacts,
methods, RVAs and relevant artifact hashes are summarized in [protocol / provenance](protocol.md).

## Session storage

No overall binary magic exists in the state/trace records. Identification
requires a recognized session store, version and consistent state/trace links.
The current writer uses version 18. The reader reconstructs versions 1–18;
version 0 and future versions are rejected conservatively.
RTSA is selected by application code 2 in versions 8-18. Initial RTSA support
is limited to a single recorded spectrum block with nonzero frequency span;
this is based on the explicit Data Link RTSA playback path, not on a guessed
point count. The RTSA evidence is summarized in [protocol / provenance](protocol.md).

```text
<arbitrary session name>/
  STA.rpx                         optional state index
  TRC.rpx                         optional trace index
  dSTA00000/00000000.STA          concatenated 104-byte state records
  dTRC00000/00000000.TRC          concatenated fixed-stride trace records
             00000001.TRC
  dTRC00001/...                    additional partitions as needed
```

`apf.a8/a7` also support the legacy flat names `STA00000`, `TRC00000`, etc.
These are storage layouts, independent of the arbitrary session folder name.
The implementation requires partition numbers consecutive from zero and
rejects ambiguous mixed flat/nested stores. The bundled caller uses nominal
5000 files per directory and targets 409600 bytes per file, but actual record
counts, file sizes and RPX deviations govern boundaries. Those nominal numbers
are **not hard-coded requirements in the Python reader**.

Each file begins directly with its first record; no file-header bytes are
skipped. Reads use a fixed stride derived from the initial state. State changes
may alter axes and settings. A session that changes dimensions/version is
rejected because no varying-stride storage was verified. Current GPSA writes
one trace and five auxiliary floats, but dimensions are read from the header.

## State record: 104 bytes, little endian

All offsets are from the beginning of one record. Types are signed unless `u`
is shown. `f32/f64` are IEEE 754 floats. Evidence: Utility `als.qm`/`ql`/`qp`,
GPSA `adg.or` and `aef.kg`. Widths and numerical types are confirmed-static;
fields explicitly marked raw have incomplete semantic interpretation.

| Offset | Width | Type | Meaning / version condition | Evidence / confidence |
|---:|---:|---|---|---|
| 0 | 1 | i8 | Recording format version | als.qm; confirmed-static |
| 1 | 1 | i8 | Application: >=8, 1=GPSA, 2=RTSA; <8 reader forces GPSA | enum + als.qm; confirmed-static |
| 2 | 2 | u16 | State identifier | alp.c, Core oa verifies IDs; confirmed-static |
| 4 | 4 | i32 | First associated trace index, >=5 | alp.d; confirmed-static |
| 4 | 2+2 | u16 + raw | First trace index plus reserved i16, <5 | als.qm; confirmed-static |
| 8 | 4 | i32 | Number of trace points, <11 | als.qm; confirmed-static |
| 8 | 2+2 | i16+i16 | Points and trace count, 11–15 | als.qm; confirmed-static |
| 8 | 2+1+1 | i16+u8+u8 | Points, trace count, auxiliary float count, >=16 | als.qm/adg.or; confirmed-static |
| 12 | 4 | raw i32 | Reserved/discarded by vendor reader | retained raw; confirmed-static |
| 16 | 8 | i64 | State timestamp in .NET ticks | alp.h and DateTime.Now.Ticks; confirmed-static |
| 24 | 8 | f64 | Center frequency, Hz | alo.c/aef.kg; confirmed-static |
| 32 | 8 | f64 | Signed span, Hz; zero means time scan | alo.d/adg.ap/aef.kg; confirmed-static |
| 40 | 4 | f32 | alo.e; reference-level-related raw value, forced zero <13 | exact type confirmed, semantics partial |
| 44 | 4 | f32 | alo.f; scale-per-division-related raw value, forced zero <13 | exact type confirmed, semantics partial |
| 48 | 4 | f32 | Signed RBW, abs gives Hz; sign carries setting mode | alo.g/aef.kg; confirmed-static |
| 52 | 4 | f32 | Signed VBW, abs gives Hz; sign carries setting mode | alo.h/aef.kg; confirmed-static |
| 56 | 4 | f32 | Sweep time, seconds | alo.i/aef.kg; confirmed-static |
| 60 | 4 | f32 | Trigger delay, used as zero-span axis start | alo.v/aef.kg; confirmed-static |
| 64 | 4 | f32 | Trigger level raw (alo.w) | exporter diagnostic label; confirmed-static |
| 68 | 4 | f32 | Trigger holdoff-related raw value (alo.x) | type confirmed, semantics partial |
| 72 | 4 | f32 | External gain raw (alo.y); forced zero <2 | aef.kg/als.qm; confirmed-static |
| 76 | 4 | f32 | Extra trigger setting raw (alo.ac); forced zero <6 | type confirmed, semantics unknown |
| 80 | 4 | raw i32 | Reserved | als.qm; confirmed-static |
| 84 | 4 | raw i32 | Reserved <11; two extra signed settings >=11 (alo.k/l) | als.qm; semantics unknown |
| 88 | 2 | i16 | Signed averaging count (alo.j) | adg.ap/als.qm; confirmed-static |
| 90 | 2 | raw i16 | Reserved | als.qm; confirmed-static |
| 92 | 1 | bool / i8 | Legacy preamp bool <10; encoded preamp value >=10 | als.qm/alo.ae; preserve raw |
| 93 | 1 | bool | Trigger flag (alo.ad) | exact type confirmed; semantics partial |
| 94 | 1 | i8 | Measurement path flags >=17, ignored/zero earlier | als.qm; confirmed-static |
| 95 | 1 | i8 | Encoded RF attenuation; >=9 magnitude minus 1; sign encodes mode | als.qm/aef.kg; confirmed-static |
| 96 | 1 | i8 | Signed sweep mode (alo.q) | adg.ap; preserve raw |
| 97 | 1 | i8 | Signed detector code (alo.r) | adg.ap/aef.kg; preserve raw |
| 98 | 1 | i8 | Signed averaging mode (alo.s) | adg.ap; preserve raw |
| 99 | 1 | i8 | Trigger type (alo.t) | adg.ap; preserve raw |
| 100 | 1 | i8 | Trigger source (alo.u) | adg.ap; preserve raw |
| 101 | 1 | i8 flags | Misc flags; forced zero <3 | enum/als.qm; confirmed-static |
| 102 | 1 | i8 | Trigger-related setting, forced -1 <6 | als.qm; semantics unknown |
| 103 | 1 | i8 | IF/path setting; forced zero <13 | als.qm; preserve raw |

The original 104 bytes remain in `State.raw_header` even where vendor default
rules replace legacy semantic values. Not all enum values or signed setting
modes are translated by this first implementation.

## Trace record

Let `P=points`, `T=trace_count`, `A=auxiliary_count`, `V=P*T+A`.
For <11, T defaults to 1. For <16, A is 0.

- Versions 1–3: **32 + 4V bytes**.
- Versions 4–18: **44 + 4V bytes**.

Evidence: `alt.qp` and matching `alt.qm/ql` read/write order. There is **no
trailing padding**. GPS fields add exactly 12 bytes, using either two bytes
or one int16 at the same location, not both.

| Offset | Width | Type | Meaning / versions | Evidence / confidence |
|---:|---:|---|---|---|
| 0 | 2 | u16 | Trace ID <5; reserved >=5 | alt.qm; confirmed-static |
| 2 | 2 | u16 | Associated state ID | alt.qm/Core oa; confirmed-static |
| 4 | 4 | i32 | Reserved <5; trace ID >=5 | alt.qm; confirmed-static |
| 8 | 8 | i64 | Trace timestamp, .NET ticks | alt.qm/aef.kg; confirmed-static |
| 16 | 4 | i32 | GPS coordinate j, >=4 | exact type confirmed, scaling unknown |
| 20 | 4 | i32 | GPS coordinate k, >=4 | exact type confirmed, scaling unknown |
| 24 | 2 | i16 | Elevation in meters, >=4 | exporter appends m; confirmed-static |
| 26 | 1+1 | i8+bool | GPS validity plus reserved byte, 4–6 | alt.qm; confirmed-static |
| 26 | 2 | i16 | GPS age in 10 ms units, >=7; negative invalid; <=5000 ms fresh | alt.qm; confirmed-static |
| H | 3 | bytes | <12: ADC overrange, uncal, drift flags; >=12: two legacy bytes + condition bitmask | alt.qm; confirmed-static |
| H+3 | 1 | i8 mask | Trace bitmask (1,2,4,8 for Trace1..4) | enum/alt.qm; confirmed-static |
| H+4 | 4 | i32 | Reserved | retained raw; confirmed-static |
| H+8 | 8 | f64 | Result sweep time in seconds (alq.c.b); negative sentinel meanings unknown | az.ek CSV label; confirmed-static |
| H+16 | 4V | f32[V] | Trace values then auxiliary values | alt.qm/alq.h; confirmed-static |

Here `H=16` for versions <4, otherwise `H=28`. Version >=12 condition bits:
1 uncalibrated, 2 ADC overrange, 4 questionable drift alignment,
8 questionable wide-IF alignment, 16 oversweep active. Before version 6 the
drift flag is consumed but forced false by the vendor reader.

The value payload concatenates T blocks of P float32 values; the last A
float32 values are exposed separately. Slot order is retained; mapping slots
onto enabled physical traces is not assigned from the mask. This build's
GPSA writer creates T=1 and, for >=16, A=5. Auxiliary meanings remain unknown.

## Power, frequency and timestamps

GPSA `aef.kg` sets the input unit to `YAxisUnit.dBm` after copying values with
`alq.e`. There is no scale or reference-level conversion during binary read.
`power_dbm` therefore exposes stored GPSA float32 values directly. Data Link's
explicit RTSA loader (`a7.b`) selects the same serializers; playback (`bw.bj`)
copies the first spectrum block directly and labels it dBm (`bw.am`). The
independent reader now accepts that single RTSA spectrum block. Additional
RTSA blocks and RTSA zero-span axes remain rejected pending semantic evidence.
Raw IQ/VITA-49 captures and Data Link DLS ZIP files are distinct and unsupported.

Frequency points include both endpoints:

```text
start_hz = center_hz - signed_span_hz / 2
stop_hz  = center_hz + signed_span_hz / 2
frequency_hz[i] = start_hz + i * (stop_hz-start_hz)/(P-1)
```

Negative span gives descending frequencies. Zero span produces seconds from
trigger delay through trigger delay + sweep time; no fictitious frequency
axis is returned. Changed settings use per-sweep state axes. Point counts
below 2 are rejected because the verified axis expression divides by P-1.

.NET ticks count 100 ns from 0001-01-01. The writer uses `DateTime.Now.Ticks`
and the exporter constructs `new DateTime(ticks)` without a timezone. This
cannot be truthfully labeled UTC. Python preserves the exact int64 and
exposes a seven-digit fractional ISO string without a timezone. Invalid ticks
are rejected instead of reproducing the vendor reader's current-time fallback.

## Optional RPX index

`STA.rpx` / `TRC.rpx` begin with ASCII `FFRPINDX` (8 bytes), then little-endian
uint16 version 1. Evidence: `anm` constructor, `ank.k`, `apf.x`.

At offset 10, repeat chunks until EOF:

| Chunk-relative offset | Width | Type | Meaning | Confidence |
|---:|---:|---|---|---|
| 0 | 4 | i32 | Payload length L, excluding tag/header/checksum | confirmed-static, anl.t |
| 4 | 4 | ASCII | Chunk tag | confirmed-static |
| 8 | L | bytes | Body | confirmed-static |
| 8+L | 4 | u32 | CRC-32 of tag + body | confirmed-static, anl.u/amc |

CRC-32 uses reflected polynomial 0xEDB88320, initial/final complement, matching
`zlib.crc32`. It does not cover the length or the sweep data. Chunks have no
alignment padding. `FDAT` / `fDEV` bodies are length-tag-value items:
little-endian int32 payload length, byte item ID, payload.

FDAT item IDs: 10 ASCII store type, 11 int32 total records, 12 int32 nominal
files per directory, 13 int32 nominal records per file. fDEV item 10 is store
type; 11 and 12 are pairs of int32 describing directory/file count exceptions.
The file exception pair is `(zero_based_file_number, record_count)`, confirmed
by `apf.t` (cases 11/15 initialize nominal counts; case 5 replaces a file's
count). Recovery uses these counts, rather than assuming every file contains
the nominal number of records.
`sTRS` stores length-prefixed ASCII key/value settings; it is retained as raw
bytes by this implementation. Unknown chunks and fields are also retained.

Present indexes are checked for CRC. Strict Python decoding requires total-count
agreement with physical records. Explicit recovery mode uses declared counts to
fill missing TRC power with −300 dBm, retaining available complete float32 values and
reporting the replacements separately; this is a recovery policy, not evidence
that a placeholder is an instrument measurement. Missing auxiliary values remain
0. The reader can scan recognized stores without an index, as can the
vendor fallback (`apf.n`). Recovery also uses validated next-partition first IDs
as logical boundaries even if a preceding file has extra physical tail bytes.
Those bytes are reported as `ignored_trailing_bytes`; identical whole repeated
prefixes require bounded byte comparison. This boundary choice is a recovery
policy, not evidence about why an instrument file contains extra bytes.
Missing final physical records cannot always be
detected when there is no declared count or checksum. No trace checksum or
compression is present in the recovered als/alt path.

## Validation limits

All numerical integration tests currently use synthetic fixtures constructed
from these recovered layouts. They cover endian choice, version boundaries,
record sizing, state links, timestamps, exports and negative inputs. They are
not independent proof of instrument compatibility. Need a complete finished
GPSA session, and ideally its Data Link CSV, to measure actual sweep/axis/time/
power agreement. The user clarified that their GPSA data uses RTAUTOsessionXX
folders with numbered files in dSTA00000 and dTRC00000; the folder prefix is
not an application discriminator. They report the preceding decoder works.
Reference comparison statistics are **pending**, not zero.

## Exported time-zone interpretations (v0.3.0)

The binary clock interpretation above is unchanged: .NET ticks with no stored
time zone. The user stated the instrument clock should have been EST, so the
new MAT/GUI/MATLAB exports default to the explicit assumption EST = UTC-05:00.
The original ticks and original seven-digit clock strings are always retained.
Converted UTC ticks subtract the integer source UTC offset from the raw ticks;
conversion never changes the fractional tick remainder.

`timestamp_est` uses fixed UTC-05:00; `timestamp_eastern` separately uses
America/New_York daylight saving. The selected source zone is exported as
metadata and is configurable. UTC and fixed EST are not inferred from a field
or from GPS validity. Python rejects nonexistent DST wall times and requires
an explicit fold for ambiguous repeated times. CSV/NPZ remain original-clock
exports. MAT files store selected float32 dBm matrices with one row per selected
sweep, int64 timestamps/indices, numeric column axes, and ISO cell-string columns.
