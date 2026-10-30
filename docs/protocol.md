# Protocol and decoding provenance

## Ethernet implementation

The browser uses standard-library TCP sockets on port 5025, documented by Keysight
in its [MATLAB socket file-transfer example](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/Examples/MATLAB/MATLAB_-_Sockets-_Binary_Block_File_Transfer.htm).
It connects only to the host entered by the user. There is no network scan, VISA
dependency, automatic preset or automatic operating-mode switch.

| Operation | Commands and primary documentation |
|---|---|
| Identity | `*IDN?` |
| Browse | [`MMEM:CAT?`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/MMEMory_CATalog.htm), absolute INTERNAL/SDCARD/USBDISK aliases |
| Download | [`MMEM:DATA?`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/MMEMory_DATA.htm), definite IEEE 488.2 block, length checked against catalogue |
| File preview | Same `MMEM:DATA?` query on a dedicated connection; read at most 256 KiB, then close the connection |
| PNG capture | [`MMEM:STOR:IMAG`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/MMEMory_STORe_IMAGe.htm), then `*OPC?`, catalogue and download |
| CSV capture | [`MMEM:STOR:FDAT`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/MMEMory_STORe_FDATa.htm), then `*OPC?`, catalogue and download |
| Capture cleanup | `MMEM:DEL` of the unique generated file only, as in Keysight's [image transfer example](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/Examples/Transfer_Image_to_PC.htm) |
| SA data | [`TRACn:DATA?`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/TRACe_n_DATA.htm), [`TRACn:XVAL?`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/TRACe_n_XVALues_.htm), `SENS:AMPL:UNIT?` |
| SA settings | `SENS:FREQ:CENT`, `SENS:FREQ:SPAN`, `SENS:BAND:RES`, documented in the [SA command index](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/A_SA_Mode_Commands.htm) |
| Sweep controls | [`INIT:CONT`](https://helpfiles.keysight.com/csg/FFProgrammingHelpWebHelp/INITiate_CONTinuous.htm), `INIT:IMM`, `*OPC?` |

Screen/data capture writes a UUID-named file on the selected instrument drive.
The exact file is removed in a `finally` cleanup using a separate bounded
connection, including after cancellation. Existing remote files are never selected
for deletion. Cleanup warnings include the path for manual removal. If a command
fails after sending, the file may already have been created, so cleanup is still
attempted. Storage must be writable and the firmware must accept absolute filenames.

Live SA capture temporarily selects ASCII data format and restores the previous
format. X values are queried before and after Y; changing axes are rejected. The
capture does not freeze acquisition or promise an atomic snapshot; use Hold for a
stable trace. XVAL requires firmware 11.26+ per Keysight's command history. The
instrument's amplitude unit is preserved; no dBm conversion is guessed. SA-only
live capture deliberately rejects other modes. The generic CSV/screenshot capture
commands support other documented modes when available on the instrument.

Explicit setting changes wait for operation completion, check one error-queue
entry and read settings back. Reading that entry consumes it. A rejected or timed
out change can leave some settings applied; read settings again. The analyzer
enforces model/options-specific limits. Single first enters Hold and waits for
completion, then triggers and waits again.

Downloads plan a recursive tree before copying, validate portable filenames and
case collisions, stream to a private staging directory, recheck catalogues and
publish to a new destination. Files have local SHA-256 hashes. Same-size remote
rewrites cannot be detected by catalogue rechecks; copy completed sessions.

File preview uses the same validated definite-length binary block header and
catalogue-size check as downloads. The command has no byte-range parameter. If
the file exceeds 256 KiB, only that prefix is read and the dedicated socket is
closed; it is never reused with an unread block remaining. For shorter files the
entire block and line ending are consumed. Cancellation closes the connection.
This bounds application reads and memory, but does not promise that firmware
sends only the prefix. Behavior after early socket closure remains unverified on
an N9917B. Preview makes no remote writes or local download files. Plain text is
decoded for display only; binary input gets a hex view capped at 4 KiB. Changed
selections invalidate in-flight results before they can replace the new preview.

## Binary decoder investigation actually performed

The original workspace supplied an already-unpacked `FFoxDataLinkInstall` tree:
140 files, 89,228,844 bytes. No installer container, complete instrument session or
known-good reference CSV was supplied locally. No vendor executable was installed
or executed. The managed .NET assemblies were inspected with **ILSpy / ilspycmd
9.1.0.7988**, hosted on .NET SDK 9.0.101; **Ghidra was not used**. PE metadata and
resources were read with pefile 2023.2.7, strings with GNU binutils 2.42, and the
bundled CHM help was extracted offline with 7-Zip 23.01.

| Artifact | Version | SHA-256 |
|---|---|---|
| FFoxDataLink.exe | 8.2.9762.18414 | `53149b520073fa1cb655b00e46622b3978aa4967b9ebfbeabbf07d7069363aec` |
| Agilent.FieldFox.Utility.dll | 1.0.9762.18351 | `61684457d57e50a8d95d3a45f409d912ae9017612b6b582ab5297aa9127bf879` |
| Agilent.FieldFox.GPSA.dll | 1.0.9762.18362 | `156952be28f87171050d4eada9d099d10b7c62e1e85425f9c2d96d56119aa891` |
| Agilent.FieldFox.Core.dll | 0.0.0.0 | `294341091a9e27472d47cd4f8d4c0b5e26f0e36cba31f49bc31ecbaac01c5aad` |

The console path in the main executable (`u.ConsoleCommands.DoWork` → `u.ch`)
led to GPSA `aef.kj` → `adg.or`, then Utility serializers and Core storage.
Reader/writer pairs were compared with their independent size calculations:

| Behavior | Static evidence |
|---|---|
| 104-byte state records | Utility `als.qm` reader (RVA `0x2a040`), `als.ql` writer, `als.qp` size (RVA `0x2b180`) |
| Versioned trace headers / samples | Utility `alt.qm` reader (RVA `0x2bd20`), `alt.ql`, `alt.qp` size (RVA `0x2cca4`) |
| Partition folders / direct seeks | Utility `apf.a8/a7`, `apf.n/a5/ba`, `aqb`; Core `n5.av/aw` |
| GPSA power and axis | GPSA `aef.kg`, float copies, dBm display/export labeling and axis generation |
| RTSA shared recording reader | Main executable `a7.b/a7.d` uses the same serializers with RTSA application discriminator |
| RTSA spectrum dBm / axis | Main executable `bw.bj`, `bw.am`, `bw.w`; first spectrum block copied directly |
| RPX framing/counts/CRC | Utility `apf`, `anm`, `ank`, `anl`, `ano`, `ann`, `amc` |
| File browser protocol | Main executable `y.g/k` catalogue calls and `y.a/d` binary transfers; DataLinkLANManager port 5025 |

RVA values refer to the supplied PE image, not offsets in a recording. Names are
obfuscated and version-specific. The independently authored implementation is
based on the recovered behavior, not a redistributed copy of vendor code.

The repeatable workflow is: inventory signatures/hashes and CLR metadata; search
recording/CSV/BinaryReader strings; follow the most direct importer/exporter path;
decompile individual types and immediate callers; compare reader, writer and size
routines for every version branch; document byte offsets; construct independent
fixtures; test boundaries, unsupported cases and exports. Run analysis tools with
owned process handles, time/memory limits and verified cleanup. Avoid unbounded
bulk decompilation. No further decompilation was needed for this desktop integration.

Confirmed **in inspected code**: header widths/version branches, scalar float32
samples, physical store naming, version/application discriminators, spectrum dBm
semantics and axes. Confirmed **with synthetic execution**: decoding, bounds,
negative cases, record seeking, CRC and cross-format exports. **Still unknown or
unvalidated on actual supplied data**: auxiliary/GPS scaling, physical trace-slot
mapping, all model/firmware combinations, unsupported RTSA density/multiblock and
IQ formats. Instrument clock time zone is absent; EST is the user's declared
assumption, not an embedded timestamp attribute.

The user reported the earlier decoder build worked on their recordings; those
recordings were not available for local comparison. A complete N9917B session and
matching instrument/Data Link CSV would allow first/middle/last-sweep numeric
validation. A reachable N9917B would validate catalogue, capture and control commands.
