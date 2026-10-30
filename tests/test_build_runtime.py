import struct

import pytest

from fieldfox_workbench.build_support import (
    PYTHON_DLL, VC_DLLS, validate_build_runtime, validate_runtime_names,
    pe_machine, isolated_environment,
)


def test_windows_x64_python311_build_is_supported():
    assert validate_build_runtime(version=(3, 11), bits=64, implementation="CPython", system="win32")["python_dll"] == "python311.dll"


@pytest.mark.parametrize("changes", [
    {"version": (3, 13)}, {"version": (3, 12)}, {"bits": 32},
    {"implementation": "PyPy"}, {"system": "linux"},
])
def test_wrong_build_interpreter_is_rejected_before_packaging(changes):
    options = dict(version=(3, 11), bits=64, implementation="CPython", system="win32")
    options.update(changes)
    with pytest.raises(RuntimeError, match="64-bit CPython 3.11"): validate_build_runtime(**options)


def test_runtime_files_are_present_and_cookie_agrees():
    validate_runtime_names([PYTHON_DLL, *VC_DLLS, "python3.dll", "library.pyd"])


@pytest.mark.parametrize("missing", [PYTHON_DLL, *VC_DLLS])
def test_missing_python_or_vc_runtime_fails_the_build(missing):
    with pytest.raises(RuntimeError, match="missing"):
        validate_runtime_names([n for n in (PYTHON_DLL, *VC_DLLS) if n != missing])


@pytest.mark.parametrize("extra", ["python313.dll", "python312.dll", "other/python313.dll"])
def test_mixed_runtime_dll_fails_the_build(extra):
    with pytest.raises(RuntimeError, match="mixed Python runtime"):
        validate_runtime_names([PYTHON_DLL, *VC_DLLS, extra])


def test_bootloader_cannot_select_python313_even_if_python311_is_included():
    with pytest.raises(RuntimeError, match="cookie"):
        validate_runtime_names([PYTHON_DLL, *VC_DLLS], python_version=313, library="python313.dll")


def test_vc_dll_nested_in_an_unrelated_package_does_not_satisfy_python_dependency():
    with pytest.raises(RuntimeError, match="missing vcruntime140.dll"):
        validate_runtime_names([PYTHON_DLL, VC_DLLS[1], "unrelated/"+VC_DLLS[0]])


def test_pe_machine_and_corrupt_file():
    data = bytearray(128); data[:2] = b"MZ"; struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"; struct.pack_into("<H", data, 68, 0x8664)
    assert pe_machine(data) == 0x8664
    with pytest.raises(RuntimeError): pe_machine(b"invalid")
    struct.pack_into("<I", data, 60, 1000000)
    with pytest.raises(RuntimeError): pe_machine(data)


def test_frozen_startup_cannot_use_python_or_venv_from_path(tmp_path):
    env = isolated_environment({"PATH": "C:/Python313", "PYTHONHOME": "C:/Python313", "PYTHONPATH": "source",
          "VIRTUAL_ENV": "venv", "CONDA_PREFIX": "conda", "_PYI_APPLICATION_HOME_DIR": "old_bundle", "KEEP": "yes"},
          tmp_path / "Windows", tmp_path)
    assert not any(k.startswith(("PYTHON", "CONDA_", "_PYI_")) for k in env)
    assert "VIRTUAL_ENV" not in env and "Python313" not in env["PATH"]
    assert env["KEEP"] == "yes" and env["TEMP"] == str(tmp_path)
