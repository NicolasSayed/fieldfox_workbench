"""Unified Tk desktop application; all instrument work is user initiated."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "fieldfox_workbench"

from . import __version__


def settings_path():
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / "FieldFoxWorkbench" / "settings.json"


class Workbench:
    def __init__(self, root, *, settings_file=None, persist=True):
        import tkinter as tk
        from tkinter import ttk
        from fieldfox_browser.gui import BrowserApp
        from fieldfox_recording.gui import FieldFoxApp
        from .jobs import Jobs
        from .plot_panel import PlotPanel
        from .screen_panel import ScreenPanel
        from .playback import Playback
        from .live_panel import LivePanel
        self.root = root; self.persist = persist; self.settings_file = Path(settings_file) if settings_file else settings_path()
        self.recent = []; self.closing = False
        root.title(f"FieldFox Workbench {__version__}")
        width, height = min(1280, root.winfo_screenwidth()-60), min(940, root.winfo_screenheight()-100)
        root.geometry(f"{max(950, width)}x{max(650, height)}"); root.minsize(950, 650)
        style = ttk.Style(root)
        if "vista" in style.theme_names(): style.theme_use("vista")
        self.status = tk.StringVar(value="Open a local session / CSV, or enter your FieldFox address on Instrument files.")
        self.jobs = Jobs(root, self.status, self.error)
        bar = ttk.Frame(root, padding=(10, 7)); bar.pack(fill="x")
        ttk.Label(bar, text="FieldFox Workbench", font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 20))
        ttk.Button(bar, text="Open session…", command=self.choose_session).pack(side="left", padx=4)
        ttk.Button(bar, text="Open CSV / image…", command=self.choose_file).pack(side="left", padx=4)
        self.recent_choice = tk.StringVar()
        self.recent_box = ttk.Combobox(bar, textvariable=self.recent_choice, state="readonly", width=36)
        self.recent_box.pack(side="left", padx=10); self.recent_box.bind("<<ComboboxSelected>>", lambda _: self.open_path(self.recent_choice.get()))
        ttk.Button(bar, text="Cancel operation", command=self.cancel).pack(side="right")
        ttk.Label(root, textvariable=self.status, padding=(10, 6), wraplength=1200).pack(side="bottom", fill="x")
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        self.browser_tab, self.session_tab, self.trace_tab, self.screen_tab, self.live_tab, help_tab = [ttk.Frame(self.tabs) for _ in range(6)]
        for frame, title in zip((self.browser_tab, self.session_tab, self.trace_tab, self.screen_tab, self.live_tab, help_tab),
                                ("Instrument files", "Session spectrogram", "Traces / CSV", "Screenshots / capture", "SA control / live", "Help")):
            self.tabs.add(frame, text=title)
        self.browser = BrowserApp(root, parent=self.browser_tab, embedded=True, on_download=self.open_path)
        self.viewer = FieldFoxApp(root, parent=self.session_tab, embedded=True, on_loaded=self.session_loaded)
        self.browser.cancel = self.jobs.cancel; self.browser._report = self.jobs.report; self.viewer.cancel_event = self.jobs.cancel
        self.browser._job = lambda work, done, message: self.panel_job(self.browser, work, done, message)
        self.viewer._job = lambda work, done, message: self.panel_job(self.viewer, work, done, message)
        self.browser._error = self.viewer._error = self.error
        self.plots = PlotPanel(self, self.trace_tab); self.screen = ScreenPanel(self, self.screen_tab)
        self.playback = Playback(self, self.plots.playback_frame); self.live = LivePanel(self, self.live_tab)
        help_text = tk.Text(help_tab, wrap="word", font=("Segoe UI", 11), padx=22, pady=16)
        help_text.pack(fill="both", expand=True)
        help_text.insert("1.0", HELP); help_text.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = lambda kind, value, trace: self.error(value)
        self.load_settings()
        self.tabs.select(self.session_tab)

    def error(self, error):
        from tkinter import messagebox
        self.live.stop() if hasattr(self, "live") else None
        self.playback.stop() if hasattr(self, "playback") else None
        notes = "\n".join(getattr(error, "__notes__", []))
        self.status.set(str(error))
        messagebox.showerror("FieldFox Workbench", str(error) + ("\n" + notes if notes else ""), parent=self.root)

    def client(self):
        from fieldfox_browser.client import FieldFoxClient
        return FieldFoxClient(self.browser.host.get().strip(), int(self.browser.port.get()), float(self.browser.timeout.get()))

    def panel_job(self, panel, work, done, message):
        if self.jobs.busy or self.jobs.closing: self.status.set("Wait for the current operation, or press Cancel."); return
        def finished(): panel.busy = False
        def completed(value):
            done(value); self.status.set(panel.status.get())
        if self.jobs.submit(work, completed, message, finished=finished):
            panel.busy = True; panel.status.set(message)

    def session_loaded(self, rec, section):
        self.playback.loaded(rec, section); self.remember(rec.path)

    def choose_session(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title="Select a complete recording session folder")
        if path: self.open_path(path)

    def choose_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("CSV / images", "*.csv *.tsv *.png *.jpg *.jpeg *.bmp"), ("All files", "*")])
        if path: self.open_path(path)

    def open_path(self, path):
        if self.jobs.busy: self.status.set("Wait for the current operation, or press Cancel."); return
        self.live.stop(); self.playback.stop()
        path = Path(path).expanduser().absolute()
        try:
            if not path.exists(): raise FileNotFoundError(path)
            if path.is_dir():
                # A session may be flat or partitioned; actual header validation is
                # always delegated to the decoder, never inferred from folder name.
                if any(p.name.upper().startswith(("DSTA", "STA0")) for p in path.iterdir()):
                    self.viewer.path.set(str(path)); self.tabs.select(self.session_tab); self.viewer.load()
                else:
                    children = [p for p in path.iterdir() if p.is_dir() and any(p.glob("[dD][sS][tT][aA]*"))]
                    if children: self.select_child(children)
                    else: raise ValueError("No session stores found. Select the folder containing dSTA00000 / dTRC00000, or open a downloaded CSV / image.")
            elif path.suffix.lower() in {".csv", ".tsv", ".txt"}:
                self.tabs.select(self.trace_tab); self.plots.open_csv(path)
            elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
                self.tabs.select(self.screen_tab); self.screen.open_image(path)
            else: raise ValueError("Open a complete session directory, CSV/TSV text file, or screenshot image.")
        except Exception as error: self.error(error)

    def select_child(self, paths):
        import tkinter as tk
        from tkinter import ttk
        window = tk.Toplevel(self.root); window.title("Choose a downloaded session"); window.geometry("600x340")
        box = tk.Listbox(window); box.pack(fill="both", expand=True, padx=10, pady=10)
        paths = sorted(paths)
        for path in paths: box.insert("end", path.name)
        def choose(event=None):
            if box.curselection():
                chosen = paths[box.curselection()[0]]; window.destroy(); self.open_path(chosen)
        box.bind("<Double-1>", choose); ttk.Button(window, text="Open session", command=choose).pack(pady=8)

    def remember(self, path):
        text = str(Path(path).absolute()); self.recent = [text] + [p for p in self.recent if p != text][:9]
        self.recent_box.configure(values=self.recent); self.recent_choice.set(text)

    def load_settings(self):
        try:
            if not self.persist or not self.settings_file.exists() or self.settings_file.stat().st_size > 32768: return
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict): return
            for key, var in [("host", self.browser.host), ("port", self.browser.port), ("timeout", self.browser.timeout), ("timezone", self.viewer.timezone)]:
                if isinstance(data.get(key), str): var.set(data[key])
            recent = data.get("recent", [])
            if isinstance(recent, list): self.recent = [p for p in recent if isinstance(p, str)][:10]
            self.recent_box.configure(values=self.recent)
        except (OSError, ValueError): self.status.set("Could not load saved preferences; using defaults.")

    def save_settings(self):
        if not self.persist: return
        data = {"host": self.browser.host.get(), "port": self.browser.port.get(), "timeout": self.browser.timeout.get(),
                "timezone": self.viewer.timezone.get(), "recent": self.recent}
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8"); temp.replace(self.settings_file)

    def cancel(self):
        self.live.stop(); self.playback.stop(); self.jobs.cancel.set()
        self.status.set("Cancellation requested; waiting for the current bounded read or socket timeout / cleanup.")

    def close(self):
        if self.closing: return
        self.closing = True; self.cancel()
        try: self.save_settings()
        except OSError: pass
        self.jobs.closing = True
        self.status.set("Closing; completing cancellation and temporary-file cleanup…")


HELP = """FieldFox Workbench

1. Instrument files: enter your N9917B IP address, port 5025 and a timeout. Connect / browse lists internal / SD / USB folders. Double-click folders to navigate; download a completed session or individual file to a NEW local destination. Completed downloads open in the appropriate tab.

2. Session spectrogram: select an RTAUTOsession folder containing dSTA00000 and dTRC00000 (or supported flat stores). Choose the sweep interval and frequency range, then Load / update plot. Large selections are thinned to the maximum displayed sweeps, not averaged. Export section MAT preserves the displayed data plus instrument, UTC and EST timestamps. Existing files and original session folders are protected.

3. Session playback is at the top of Traces / CSV, directly above the plot. Drag the slider, use the arrow keys or mouse wheel, or use Previous / Play / Next to browse selected sweeps while viewing the trace. Playback speed, UTC / EST timestamps and maximum/minimum hold / power mean are on the same page. Playback uses the loaded selection; it does not load the whole recording.

4. Traces / CSV: open a numeric CSV with optional metadata/header rows. Check X/Y columns and units; X multiplier converts units explicitly. The largest rectangular numeric block is selected. Long-form decoder CSVs select one sweep and trace slot. Add compatible overlays, use toolbar zoom/pan, click to place up to eight nearest-point markers, and apply horizontal upper/lower limits. Limits test all imported points, including those outside the zoom. Save a JSON plot preset, CSV/MAT data, PNG/PDF image or PDF report with plots, screenshot, notes and sources.

5. Screenshots / capture: captures the current PNG screen or formatted CSV using a unique temporary file on the instrument. That temporary file is removed after transfer; cleanup failure reports the exact remote filename. Save to writable internal/SD/USB storage. Open local screenshots or save unchanged copies.

6. SA control / live: capture a current SA trace, start/stop periodic display, read or explicitly apply center/span/RBW, Hold/Run/Single. Traces use the actual instrument X axis and reported amplitude unit. Requires SA mode; no automatic mode switching. Hold first for stable snapshots. Live polling ends on errors, Cancel, opening a file or closing the app.

Clock assumption: EST means fixed UTC-05:00 all year, as requested. The recording has no embedded time zone. Choose America/New_York only if the instrument clock follows daylight saving time. UTC/EST/Eastern exports are based on this declared assumption. MAT exports retain exact integer ticks.

Compatibility: GPSA recording versions 1–18 and supported RTSA versions 8–18, scalar traces only. RTSA density/multiblock and IQ/VITA-49 are unsupported. Session folders named RTAUTOsession can contain GPSA; headers determine the format. A standalone instrument state .STA is not a recording session.

This is an independent application, not Keysight Data Link. It covers common browse/download, playback, plotting, markers, limits, screenshot, trace and report workflows. Calibration-kit/cable editors, proprietary state editors, DTF transforms, DANL correction, S-parameter/Smith charts, IQ analysis and remote recording configuration are not implemented. Network functions use documented commands and mock-instrument tests; live N9917B validation is still required.

Resource limits: one worker at a time; session plot cap 20 million cells / default 2000 sweeps; CSV 128 MiB, one million rows and four million numeric cells; 16 overlays / two million points; screenshots 32 MiB / 16 million pixels. Downloads stream in 64 KiB chunks. Full CSV/NPZ exports may take time; cancellation is checked between records. Final compression and figure rendering finish before cancellation takes effect. Settings and recent paths are stored locally under your user application-data folder. No discovery, telemetry or background tasks run when the application is closed.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="FieldFox Workbench desktop application")
    parser.add_argument("path", nargs="?", help="Session directory, CSV or screenshot to open")
    parser.add_argument("--self-test", type=Path, metavar="RESULT_JSON", help="Exercise the GUI and exports with synthetic data, then exit")
    args = parser.parse_args(argv)
    import tkinter as tk
    import matplotlib
    matplotlib.use("TkAgg")
    root = tk.Tk()
    if args.self_test: root.withdraw()
    app = Workbench(root, persist=not bool(args.self_test))
    if args.self_test:
        from .diagnostics import self_test
        return self_test(app, args.self_test)
    if args.path: root.after(100, lambda: app.open_path(args.path))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
