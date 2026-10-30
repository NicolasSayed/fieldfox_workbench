"""Build-only checks for the exact Windows Python runtime shipped in releases."""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import platform
import re
import struct
import sys

PYTHON_DLL = "python311.dll"
VC_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll")


def validate_build_runtime(*, version=None, bits=None, implementation=None, system=None):
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    bits = struct.calcsize("P")*8 if bits is None else bits
    implementation = platform.python_implementation() if implementation is None else implementation
    system = sys.platform if system is None else system
    if (system, implementation, version, bits) != ("win32", "CPython", (3, 11), 64):
        raise RuntimeError("Release builds require 64-bit CPython 3.11 on Windows. "
                           "Run build_windows.ps1; do not reuse a Python 3.13 build environment.")
    return {"python_version": platform.python_version(), "architecture": "x64", "python_dll": PYTHON_DLL}


def runtime_binaries():
    """Include the interpreter and its VC runtime explicitly, using its own files."""
    validate_build_runtime()
    locations = [Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs", Path(sys._base_executable).parent]
    result = []
    for name in (PYTHON_DLL, *VC_DLLS):
        source = next((p / name for p in locations if (p / name).is_file()), None)
        if source is None:
            raise RuntimeError(f"Build Python is missing {name}. Use a complete 64-bit Python 3.11 installation.")
        if pe_machine(source.read_bytes()) != 0x8664:
            raise RuntimeError(f"Build runtime {name} is not an x64 PE file.")
        result.append((str(source), "."))
    return result


def pe_machine(data):
    if len(data) < 64 or data[:2] != b"MZ": raise RuntimeError("Invalid Windows PE signature.")
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset+6 > len(data) or data[offset:offset+4] != b"PE\0\0": raise RuntimeError("Invalid PE header offset.")
    return struct.unpack_from("<H", data, offset+4)[0]


def validate_runtime_names(names, *, python_version=311, library=PYTHON_DLL):
    names = list(names)
    lowered = [n.replace("\\", "/").casefold() for n in names]
    if len(set(lowered)) != len(lowered): raise RuntimeError("Bundle contains duplicate runtime paths.")
    if python_version != 311 or library.casefold() != PYTHON_DLL:
        raise RuntimeError(f"Executable cookie selects an unexpected Python runtime: {python_version}, {library}.")
    for required in (PYTHON_DLL, *VC_DLLS):
        if required not in lowered: raise RuntimeError(f"Bundle is missing {required} beside the Python runtime.")
    for name in lowered:
        if re.fullmatch(r"(?:.*/)?python\d+[^/]*\.dll", name) and name.rsplit("/", 1)[-1] not in {PYTHON_DLL, "python3.dll"}:
            raise RuntimeError(f"Bundle contains a mixed Python runtime: {name}.")


def audit_bundle(artifact, mode):
    """Check bootloader cookie, runtime presence, architecture and hashes."""
    artifact = Path(artifact)
    if mode == "onefile":
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(artifact))
        with artifact.open("rb") as stream:
            stream.seek(archive._end_offset - archive._COOKIE_LENGTH)
            _, _, _, _, version, library = struct.unpack(archive._COOKIE_FORMAT, stream.read(archive._COOKIE_LENGTH))
        library = library.split(b"\0", 1)[0].decode("ascii")
        validate_runtime_names(archive.toc, python_version=version, library=library)
        mapping = {name.casefold(): name for name in archive.toc}
        contents = {name: archive.extract(mapping[name]) for name in (PYTHON_DLL, *VC_DLLS)}
        exe = artifact
    elif mode == "onedir":
        internal = artifact / "_internal"
        names = [str(p.relative_to(internal)) for p in internal.rglob("*") if p.is_file()]
        validate_runtime_names(names)
        mapping = {str(p.relative_to(internal)).casefold(): p for p in internal.rglob("*") if p.is_file()}
        contents = {name: mapping[name].read_bytes() for name in (PYTHON_DLL, *VC_DLLS)}
        exe = artifact / "FieldFoxWorkbench.exe"
    else: raise ValueError("Unknown bundle mode")
    with exe.open("rb") as stream: header = stream.read(65536)
    if pe_machine(header) != 0x8664: raise RuntimeError("Executable is not x64.")
    for name, data in contents.items():
        if pe_machine(data) != 0x8664: raise RuntimeError(f"Bundled {name} is not x64.")
    return {"python_dll": PYTHON_DLL, "architecture": "x64", "runtime_files": {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()}}


def isolated_environment(environment, windows_directory, temporary_directory):
    """Prevent installed Python, active venvs and build folders helping the EXE."""
    result = {k: v for k, v in environment.items() if not k.upper().startswith(("PYTHON", "_PYI_", "CONDA_"))
              and k.upper() not in {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}}
    windows = Path(windows_directory)
    result.update(PATH=os.pathsep.join(str(p) for p in (windows / "System32", windows, windows / "System32" / "Wbem")),
                  TEMP=str(temporary_directory), TMP=str(temporary_directory))
    return result
