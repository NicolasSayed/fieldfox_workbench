"""Build, measure and smoke-test Windows executables. Run in the build venv."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
import time


ROOT = Path(__file__).resolve().parents[1]


def run_bounded(command, *, log=None, env=None, timeout=1200):
    """Own every helper; terminate its complete tree on a timeout."""
    output = open(log, "w", encoding="utf-8") if log else subprocess.DEVNULL
    process = None
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        peak = 0
        try:
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                    ["PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                     "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage"]]
            memory = Counters(); memory.cb = ctypes.sizeof(memory)
            query = ctypes.WinDLL("psapi").GetProcessMemoryInfo
            query.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            deadline = time.monotonic()+timeout
            while process.poll() is None:
                if query(int(process._handle), ctypes.byref(memory), memory.cb): peak = max(peak, memory.PeakWorkingSetSize)
                if time.monotonic() > deadline: raise subprocess.TimeoutExpired(command, timeout)
                time.sleep(.1)
            code = process.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
            process.wait(timeout=10)
            raise RuntimeError(f"Build process exceeded {timeout} seconds and was terminated.")
        if code:
            tail = "\n".join(Path(log).read_text(encoding="utf-8", errors="replace").splitlines()[-50:]) if log else ""
            raise RuntimeError(f"Command failed ({code}): {command}\n{tail}")
        return peak
    finally:
        if process is not None and process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
            process.wait(timeout=10)
        if log: output.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["onedir", "onefile", "both"], default="both")
    parser.add_argument("--max-mib", type=int, default=300)
    args = parser.parse_args()
    if sys.platform != "win32": parser.error("Build Windows executables on Windows.")
    if args.max_mib <= 0: parser.error("--max-mib must be positive")
    build = ROOT / "build"; build.mkdir(exist_ok=True)
    reports = []
    for mode in (["onedir", "onefile"] if args.mode == "both" else [args.mode]):
        print(f"Building {mode}; log: build/{mode}.log", flush=True)
        env = os.environ | {"FFWB_ONEFILE": "1" if mode == "onefile" else "0", "PYTHONNOUSERSITE": "1"}
        run_bounded([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "INFO",
                     "--workpath", str(build / mode), str(ROOT / "packaging" / "FieldFoxWorkbench.spec")],
                     log=build / f"{mode}.log", env=env)
        artifact = ROOT / "dist" / ("FieldFoxWorkbench-standalone.exe" if mode == "onefile" else "FieldFoxWorkbench")
        exe = artifact if mode == "onefile" else artifact / "FieldFoxWorkbench.exe"
        files = [artifact] if mode == "onefile" else [p for p in artifact.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        if size > args.max_mib*1024**2: raise RuntimeError(f"{mode} size {size/1024**2:.1f} MiB exceeds {args.max_mib} MiB cap")
        report = build / f"{mode}-selftest.json"; report.unlink(missing_ok=True)
        peak = run_bounded([str(exe), "--self-test", str(report)], log=build / f"{mode}-selftest.log", timeout=60)
        result = json.loads(report.read_text(encoding="utf-8"))
        if not result.get("ok"): raise RuntimeError(result)
        if mode == "onedir":
            bundle = ROOT / "dist" / "FieldFoxWorkbench-windows-x64.zip"
            with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for file in files: archive.write(file, file.relative_to(artifact.parent))
        else: bundle = artifact
        with bundle.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
        info = dict(mode=mode, uncompressed_bytes=size, artifact=bundle.name, artifact_bytes=bundle.stat().st_size,
                    sha256=digest, self_test=result, launcher_peak_working_set_bytes=peak)
        reports.append(info)
        print(f"{mode}: {size/1024**2:.1f} MiB uncompressed; download {bundle.stat().st_size/1024**2:.1f} MiB; self-test passed", flush=True)
    (ROOT / "dist" / "build-report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    (ROOT / "dist" / "SHA256SUMS.txt").write_text("\n".join(f"{r['sha256']}  {r['artifact']}" for r in reports)+"\n", encoding="ascii")


if __name__ == "__main__": main()
