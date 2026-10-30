from .instrument import read_sa_trace, sa_settings, apply_sa_settings, sweep_action


class LivePanel:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        self.app = app; self.timer = None; self.monitoring = False
        self.slot = tk.StringVar(value="1"); self.interval = tk.StringVar(value="2")
        self.status = tk.StringVar(value="Uses the host / port on Instrument files. Live traces require SA mode and firmware with TRAC:XVAL? (11.26+).")
        self.values = {key: tk.StringVar() for key in ["center_hz", "span_hz", "rbw_hz"]}
        outer = ttk.Frame(parent, padding=15); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="SA instrument control and trace capture", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(fill="x", pady=12)
        toolbar = ttk.Frame(outer); toolbar.pack(fill="x", pady=10)
        ttk.Label(toolbar, text="Trace").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.slot, values=[1, 2, 3, 4], state="readonly", width=5).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Capture trace", command=self.capture).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Start / stop live view", command=self.toggle).pack(side="left", padx=5)
        ttk.Label(toolbar, text="Interval (seconds, 1..3600)").pack(side="left", padx=(15, 5))
        ttk.Entry(toolbar, textvariable=self.interval, width=8).pack(side="left")
        controls = ttk.LabelFrame(outer, text="Change settings only when you press a control", padding=15); controls.pack(anchor="w", fill="x", pady=15)
        for row, (key, label) in enumerate([("center_hz", "Center frequency (Hz)"), ("span_hz", "Span (Hz)"), ("rbw_hz", "Resolution bandwidth (Hz)")]):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(controls, textvariable=self.values[key], width=25).grid(row=row, column=1, padx=10, pady=5)
        ttk.Button(controls, text="Read current settings", command=self.read_settings).grid(row=3, column=0, pady=8)
        ttk.Button(controls, text="Apply these SA settings", command=self.apply).grid(row=3, column=1, pady=8)
        actions = ttk.Frame(outer); actions.pack(anchor="w", pady=10)
        for label in ("Hold", "Run", "Single"):
            ttk.Button(actions, text=label, command=lambda value=label: self.action(value)).pack(side="left", padx=(0, 10))
        ttk.Label(outer, text="Captured traces appear on Traces / CSV. Live view replaces the previous live trace.\nCaptures read current values; they do not stop acquisition. For a stable snapshot use Hold first.\nApplying settings may select a manual RBW. The instrument enforces its own ranges.\nCSV and screenshot capture are available on Screenshots / capture for other measurement modes.", wraplength=1050).pack(anchor="w", pady=15)

    def _job(self, function, done, message):
        if self.app.jobs.busy: self.app.status.set("Wait for the current operation."); return False
        try: client = self.app.client()
        except Exception as error: self.app.error(error); self.stop(); return False
        return self.app.jobs.submit(lambda: function(client), done, message)

    def capture(self):
        try: slot = int(self.slot.get())
        except ValueError as error: self.app.error(error); return
        def done(trace):
            self.app.plots.add_trace(trace, replace=self.monitoring)
            self.app.tabs.select(self.app.trace_tab)
            self.status.set(f"Captured {len(trace.x)} points. {trace.metadata}")
        return self._job(lambda c: read_sa_trace(c, slot=slot, cancel=self.app.jobs.cancel), done, "Reading current SA trace…")

    def read_settings(self):
        self._job(lambda c: sa_settings(c, self.app.jobs.cancel), self.settings_done, "Reading SA settings…")

    def settings_done(self, values):
        for key, value in values.items(): self.values[key].set(f"{value:.12g}")
        self.status.set("Read settings from the instrument.")

    def apply(self):
        try: values = {key: float(var.get()) for key, var in self.values.items()}
        except ValueError as error: self.app.error(error); return
        self._job(lambda c: apply_sa_settings(c, **values, cancel=self.app.jobs.cancel), self.settings_done, "Applying SA settings…")

    def action(self, action):
        self._job(lambda c: sweep_action(c, action, self.app.jobs.cancel),
                  lambda _: self.status.set(f"{action} acknowledged by instrument."), action + "…")

    def toggle(self):
        if self.monitoring: self.stop(); return
        try:
            interval = float(self.interval.get())
            if not 1 <= interval <= 3600: raise ValueError("Live interval must be 1..3600 seconds.")
            self.app.client()
            self.monitoring = True; self._tick()
        except Exception as error: self.app.error(error)

    def _tick(self):
        if not self.monitoring: return
        if not self.app.jobs.busy: self.capture()
        try: delay = max(1, min(3600, float(self.interval.get())))
        except ValueError: delay = 2
        if self.monitoring: self.timer = self.app.root.after(int(delay*1000), self._tick)

    def stop(self):
        self.monitoring = False
        if self.timer is not None: self.app.root.after_cancel(self.timer); self.timer = None
