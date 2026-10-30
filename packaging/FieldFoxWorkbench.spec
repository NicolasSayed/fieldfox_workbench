# PyInstaller configuration: Tk/Agg only; no Qt, web runtime or vendor binaries.
from pathlib import Path
import os
import importlib.metadata
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from fieldfox_workbench.build_support import runtime_binaries
onefile = os.environ.get("FFWB_ONEFILE") == "1"
name = "FieldFoxWorkbench" if not onefile else "FieldFoxWorkbench-standalone"
data = collect_data_files("tzdata")
data += [(str(root / "README.md"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
data += [(str(root / "docs"), "docs")]
for source in [Path(sys.base_prefix) / "LICENSE.txt",
               Path(sys.base_prefix) / "tcl" / "tcl8.6" / "license.terms",
               Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms"]:
    if source.is_file(): data.append((str(source), str(Path("licenses") / source.parent.name)))
# Preserve notices from the exact installed third-party distributions.
for package in ("numpy", "scipy", "matplotlib", "Pillow", "tzdata", "contourpy", "cycler", "fonttools", "kiwisolver", "packaging", "pyparsing", "python-dateutil", "six", "pyinstaller"):
    distribution = importlib.metadata.distribution(package)
    for file in distribution.files or []:
        if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
            source = Path(distribution.locate_file(file))
            if source.is_file(): data.append((str(source), str(Path("licenses") / package / Path(*file.parts[:-1]))))

a = Analysis([str(root / "packaging" / "launch_workbench.py")], pathex=[str(root)],
    binaries=runtime_binaries(), datas=data, hiddenimports=["matplotlib.backends.backend_pdf", "scipy.io.matlab", "PIL.ImageTk"],
    hookspath=[], hooksconfig={"matplotlib": {"backends": ["TkAgg", "Agg"]}},
    runtime_hooks=[], excludes=["pytest", "IPython", "notebook", "pandas", "PyQt5", "PyQt6", "PySide2", "PySide6",
                               "numpy.tests", "scipy.tests", "matplotlib.tests", "tkinter.test"],
    noarchive=False, optimize=1)
pyz = PYZ(a.pure)
if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=name,
              debug=False, strip=False, upx=False, console=False,
              version=str(root / "packaging" / "version_info.txt"))
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name,
              debug=False, strip=False, upx=False, console=False,
              version=str(root / "packaging" / "version_info.txt"))
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)
