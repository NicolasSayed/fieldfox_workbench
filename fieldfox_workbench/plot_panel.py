"""Trace overlay, CSV column mapping, markers, limits and portable reports."""
from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np

from .traces import read_csv, table_trace, export_traces


class PlotPanel:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        self.app = app; self.traces = []; self.table = None; self.markers = []
        self.title = tk.StringVar(value="Trace comparison")
        self.xlabel = tk.StringVar(value="Frequency (Hz)"); self.ylabel = tk.StringVar(value="Power (dBm)")
        self.lower = tk.StringVar(); self.upper = tk.StringVar(); self.xmin = tk.StringVar(); self.xmax = tk.StringVar()
        self.ymin = tk.StringVar(); self.ymax = tk.StringVar(); self.logx = tk.BooleanVar()
        self.marker_x = tk.StringVar(); self.xcol = tk.StringVar(); self.ycol = tk.StringVar()
        self.scale = tk.StringVar(value="1"); self.sweep = tk.StringVar(); self.slot = tk.StringVar(value="0")
        self.summary = tk.StringVar(value="Open a CSV or capture an SA trace. Click the plot to place markers.")
        outer = ttk.Frame(parent, padding=10); outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer); top.pack(fill="x")
        ttk.Button(top, text="Open CSV…", command=self.open_csv).pack(side="left")
        for label, var, width in [("Decoder sweep (blank=first)", self.sweep, 8), ("Slot", self.slot, 4)]:
            ttk.Label(top, text=label).pack(side="left", padx=(12, 3))
            ttk.Entry(top, textvariable=var, width=width).pack(side="left")
        mapping = ttk.Frame(outer); mapping.pack(fill="x", pady=6)
        self.xbox = ttk.Combobox(mapping, textvariable=self.xcol, state="readonly", width=25)
        self.ybox = ttk.Combobox(mapping, textvariable=self.ycol, state="readonly", width=25)
        for label, box in [("X", self.xbox), ("Y", self.ybox)]:
            ttk.Label(mapping, text=label).pack(side="left", padx=(0, 4)); box.pack(side="left", padx=(0, 10))
        ttk.Label(mapping, text="X multiplier").pack(side="left")
        ttk.Entry(mapping, textvariable=self.scale, width=9).pack(side="left", padx=5)
        ttk.Button(mapping, text="Add CSV overlay", command=self.add_csv).pack(side="left")
        ttk.Button(mapping, text="Clear traces", command=self.clear).pack(side="right")
        body = ttk.Frame(outer); body.pack(fill="both", expand=True)
        from fieldfox_recording.gui import scroll_controls
        side = scroll_controls(body, width=245)
        fields = [("Plot title", self.title), ("X axis label", self.xlabel), ("Y axis label", self.ylabel),
                  ("X minimum", self.xmin), ("X maximum", self.xmax), ("Y minimum", self.ymin),
                  ("Y maximum", self.ymax), ("Lower limit (Y units)", self.lower), ("Upper limit (Y units)", self.upper)]
        for label, var in fields:
            ttk.Label(side, text=label).pack(anchor="w")
            ttk.Entry(side, textvariable=var, width=25).pack(fill="x", pady=(0, 3))
        ttk.Checkbutton(side, text="Logarithmic X", variable=self.logx).pack(anchor="w")
        ttk.Button(side, text="Apply plot / limits", command=self.redraw_safe).pack(fill="x", pady=4)
        ttk.Label(side, text="Marker X (nearest point)").pack(anchor="w")
        ttk.Entry(side, textvariable=self.marker_x, width=25).pack(fill="x")
        ttk.Button(side, text="Add marker", command=self.add_marker).pack(fill="x", pady=3)
        ttk.Button(side, text="Clear markers", command=self.clear_markers).pack(fill="x")
        ttk.Label(side, text="Report notes").pack(anchor="w", pady=(6, 0))
        self.notes = tk.Text(side, height=4, width=24, wrap="word"); self.notes.pack(fill="x")
        self.figure = Figure(figsize=(8, 5), layout="constrained")
        self.axes = self.figure.add_subplot()
        plot = ttk.Frame(body); plot.pack(side="left", fill="both", expand=True)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot, pack_toolbar=False)
        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._click)
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=8)
        for label, command in [("Export overlays CSV / MAT…", self.export), ("Save image…", self.save_image),
                               ("PDF report…", self.report), ("Save plot preset…", self.save_preset),
                               ("Load preset…", self.load_preset)]:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))
        ttk.Label(outer, textvariable=self.summary, wraplength=1130).pack(fill="x")
        self.redraw()

    def open_csv(self, path=None):
        from tkinter import filedialog
        if path is None: path = filedialog.askopenfilename(parent=self.app.root, filetypes=[("CSV / TSV", "*.csv *.tsv *.txt"), ("All files", "*")])
        if not path: return
        try: sweep = int(self.sweep.get()) if self.sweep.get().strip() else None; slot = int(self.slot.get())
        except ValueError as error: self.app.error(error); return
        def done(table):
            self.table = table; self.xbox.configure(values=table.columns); self.ybox.configure(values=table.columns)
            self.xcol.set(table.columns[0]); self.ycol.set(table.columns[1]); self.summary.set(table.note)
            self.app.remember(path)
            # Column mapping stays visible and may be corrected before re-adding.
            self.add_csv()
        self.app.jobs.submit(lambda: read_csv(path, sweep=sweep, trace_slot=slot), done, "Reading CSV…")

    def add_csv(self):
        try:
            if self.table is None: raise ValueError("Open a CSV first.")
            trace = table_trace(self.table, self.table.columns.index(self.xcol.get()),
                                self.table.columns.index(self.ycol.get()), float(self.scale.get()))
            self.add_trace(trace)
        except Exception as error: self.app.error(error)

    def add_trace(self, trace, *, replace=False):
        if not replace and (len(self.traces) >= 16 or sum(len(t.x) for t in self.traces)+len(trace.x) > 2_000_000):
            raise ValueError("Overlay limit reached (16 traces / two million points). Clear traces first.")
        if replace: self.traces = []; self.markers = []
        if self.traces and (trace.x_label != self.traces[0].x_label or trace.y_label != self.traces[0].y_label):
            raise ValueError("Overlay axes differ. Clear traces before plotting different columns or units.")
        self.traces.append(trace)
        self.xlabel.set(trace.x_label); self.ylabel.set(trace.y_label)
        self.redraw()

    @staticmethod
    def number(variable):
        text = variable.get().strip()
        if not text: return None
        result = float(text)
        if not math.isfinite(result): raise ValueError("Plot controls must contain finite numbers.")
        return result

    def redraw_safe(self):
        try: self.redraw()
        except Exception as error: self.app.error(error)

    def redraw(self):
        lower, upper = self.number(self.lower), self.number(self.upper)
        xmin, xmax, ymin, ymax = map(self.number, (self.xmin, self.xmax, self.ymin, self.ymax))
        if xmin is not None and xmax is not None and xmin >= xmax: raise ValueError("X minimum must be below maximum.")
        if ymin is not None and ymax is not None and ymin >= ymax: raise ValueError("Y minimum must be below maximum.")
        if lower is not None and upper is not None and lower > upper: raise ValueError("Lower limit exceeds upper limit.")
        if self.logx.get() and (any(np.any(t.x <= 0) for t in self.traces) or xmin is not None and xmin <= 0 or xmax is not None and xmax <= 0):
            raise ValueError("Logarithmic X needs positive X values and limits.")
        ax = self.axes; ax.clear(); summaries = []
        for trace in self.traces:
            ax.plot(trace.x, trace.y, linewidth=1, label=trace.name)
            stats = trace.statistics(lower, upper)
            summaries.append(f"{trace.name}: peak {stats['peak_y']:.6g} at {stats['peak_x']:.9g}; {stats['limit_result']} ({stats['failed_points']} outside)")
        for value, name in [(lower, "Lower limit"), (upper, "Upper limit")]:
            if value is not None: ax.axhline(value, color="#c04040", linestyle="--", label=name)
        for number, marker in enumerate(self.markers):
            ax.plot(marker[0], marker[1], "o", color="#c05000")
            ax.annotate(f"M{number+1}: {marker[0]:.6g}, {marker[1]:.6g}", marker, xytext=(8, 10), textcoords="offset points", fontsize=8)
        ax.set(title=self.title.get(), xlabel=self.xlabel.get(), ylabel=self.ylabel.get())
        ax.set_xscale("log" if self.logx.get() else "linear"); ax.grid(True, alpha=.25)
        if xmin is not None or xmax is not None: ax.set_xlim(left=xmin, right=xmax)
        if ymin is not None or ymax is not None: ax.set_ylim(bottom=ymin, top=ymax)
        if self.traces: ax.legend(fontsize=8)
        self.summary.set(" | ".join(summaries) or "Open a CSV, load session playback, or capture an SA trace.")
        self.canvas.draw_idle()

    def _click(self, event):
        if event.inaxes == self.axes and event.button == 1 and not self.toolbar.mode and self.traces:
            self.marker_x.set(f"{event.xdata:.12g}"); self.add_marker()

    def add_marker(self):
        try:
            if not self.traces: raise ValueError("Load a trace first.")
            if len(self.markers) >= 8: raise ValueError("Clear markers before adding more than eight.")
            _, x, y = self.traces[-1].marker(float(self.marker_x.get()))
            self.markers.append((x, y)); self.redraw()
        except Exception as error: self.app.error(error)

    def clear_markers(self): self.markers.clear(); self.redraw_safe()

    def clear(self):
        self.traces.clear(); self.markers.clear(); self.redraw_safe()

    def export(self):
        from tkinter import filedialog
        try:
            self.redraw()
            if not self.traces: raise ValueError("Load a trace first.")
            output = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".mat", confirmoverwrite=False,
                     filetypes=[("MATLAB", "*.mat"), ("CSV", "*.csv")])
            if not output: return
            traces = list(self.traces); lower, upper = self.number(self.lower), self.number(self.upper)
            self.app.jobs.submit(lambda: export_traces(traces, output, lower=lower, upper=upper),
                                 lambda _: self.app.status.set(f"Saved {output}"), "Exporting traces…")
        except Exception as error: self.app.error(error)

    def save_image(self):
        from tkinter import filedialog
        from fieldfox_browser.client import destination
        try:
            self.redraw()
            output = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".png", confirmoverwrite=False,
                     filetypes=[("PNG", "*.png"), ("PDF", "*.pdf")])
            if not output: return
            with destination(output) as (_, stream): self.figure.savefig(stream, format=Path(output).suffix[1:], dpi=150)
            self.app.status.set(f"Saved {output}")
        except Exception as error: self.app.error(error)

    def report(self):
        from tkinter import filedialog
        try:
            self.redraw()
            if not self.traces and self.app.viewer.section is None and self.app.screen.image_path is None:
                raise ValueError("Load traces, a session section or a screenshot first.")
            output = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".pdf", confirmoverwrite=False)
            if output: self.write_report(output)
        except Exception as error: self.app.error(error)

    def write_report(self, output):
        from datetime import datetime, timezone
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure
        from fieldfox_browser.client import destination
        import textwrap
        lines = ["FieldFox Workbench report", datetime.now(timezone.utc).isoformat(), "",
                 "Notes: " + self.notes.get("1.0", "end").strip(), "", "Trace analysis (limits in plotted Y units):"]
        for trace in self.traces:
            lines += [trace.name, "Source: " + trace.source, f"Axes: {trace.x_label}; {trace.y_label}",
                      json.dumps(trace.statistics(self.number(self.lower), self.number(self.upper)), ensure_ascii=False),
                      json.dumps(trace.metadata, ensure_ascii=False)]
        lines += ["Markers on last selected trace: " + repr(self.markers)]
        if self.app.viewer.rec is not None:
            lines += ["Session: " + str(self.app.viewer.rec.path), "Source clock assumption: " + self.app.viewer.timezone.get(),
                      "Loaded selection: " + repr(self.app.viewer.loaded_options),
                      "EST is fixed UTC-05:00. Recording ticks contain no timezone."]
        paragraphs = [part for line in lines for part in textwrap.wrap(line, 100) or [""]]
        with destination(output) as (_, stream), PdfPages(stream, metadata={"Title": self.title.get(), "Creator": "FieldFox Workbench"}) as pdf:
            for offset in range(0, len(paragraphs), 48):
                fig = Figure(figsize=(8.27, 11.69)); ax = fig.add_subplot(); ax.axis("off")
                ax.text(0, 1, "\n".join(paragraphs[offset:offset+48]), va="top", fontsize=9, family="monospace", transform=ax.transAxes)
                pdf.savefig(fig)
            if self.traces: pdf.savefig(self.figure)
            if self.app.viewer.figure is not None: pdf.savefig(self.app.viewer.figure)
            if self.app.screen.image_path is not None:
                from PIL import Image
                with Image.open(self.app.screen.image_path) as image:
                    fig = Figure(figsize=(10, 7)); ax = fig.add_subplot(); ax.imshow(image); ax.axis("off"); ax.set_title("FieldFox screenshot")
                    pdf.savefig(fig)
        self.app.status.set(f"Saved report to {output}")

    def preset(self):
        return {key: getattr(self, key).get() for key in ("title", "xlabel", "ylabel", "lower", "upper", "xmin", "xmax", "ymin", "ymax", "logx")}

    def save_preset(self):
        from tkinter import filedialog
        from fieldfox_browser.client import destination
        output = filedialog.asksaveasfilename(parent=self.app.root, defaultextension=".json", confirmoverwrite=False)
        if not output: return
        try:
            self.redraw()
            with destination(output) as (_, stream): stream.write(json.dumps(self.preset(), indent=2).encode())
        except Exception as error: self.app.error(error)

    def load_preset(self):
        from tkinter import filedialog
        output = filedialog.askopenfilename(parent=self.app.root, filetypes=[("Plot preset", "*.json")])
        if not output: return
        old = self.preset()
        try:
            if Path(output).stat().st_size > 16384: raise ValueError("Preset exceeds 16 KiB.")
            data = json.loads(Path(output).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != set(old): raise ValueError("Not a Workbench plot preset.")
            if any(not isinstance(v, str) for k, v in data.items() if k != "logx") or not isinstance(data["logx"], bool):
                raise ValueError("Preset values have invalid types.")
            for key, value in data.items(): getattr(self, key).set(value)
            self.redraw()
        except Exception as error:
            for key, value in old.items(): getattr(self, key).set(value)
            self.redraw(); self.app.error(error)
