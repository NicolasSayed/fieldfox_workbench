"""Distinct launcher name keeps PyInstaller from shadowing the package."""
from pathlib import Path
import json
import sys
import traceback

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fieldfox_workbench.app import main
    code = main()
except Exception:
    if "--self-test" in sys.argv:
        output = Path(sys.argv[sys.argv.index("--self-test")+1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"ok": False, "startup_error": traceback.format_exc()}, indent=2), encoding="utf-8")
        code = 1
    else:
        raise
raise SystemExit(code)
