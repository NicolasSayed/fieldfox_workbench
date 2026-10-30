"""Playback reuses only the loaded spectrogram section, never rereads the session."""
import numpy as np

from .traces import Trace


class Playback:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        self.app = app; self.rec = self.section = None; self.playing = False; self.timer = None
        self.index = tk.IntVar(); self.delay = tk.StringVar(value="250")
        self.status = tk.StringVar(value="Load a session section on the Session spectrogram tab first.")
        outer = ttk.Frame(parent, padding=12); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Session playback and summaries", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Playback uses the selected section and its effective sweep step. Power mean averages in linear mW before converting to dBm.").pack(anchor="w", pady=8)
        self.slider = tk.Scale(outer, from_=0, to=0, variable=self.index, orient="horizontal", command=lambda _: self.show(), label="Selected row (zero based)")
        self.slider.pack(fill="x", pady=8)
        buttons = ttk.Frame(outer); buttons.pack(fill="x")
        for text, command in [("Previous", lambda: self.move(-1)), ("Next", lambda: self.move(1)),
                              ("Play / pause", self.toggle), ("Show selected sweep", self.show),
                              ("Maximum hold", lambda: self.summary("Maximum hold")),
                              ("Minimum hold", lambda: self.summary("Minimum hold")),
                              ("Power mean", lambda: self.summary("Power mean"))]:
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 7))
        ttk.Label(outer, text="Playback delay (milliseconds, 100..10000)").pack(anchor="w", pady=(20, 4))
        ttk.Entry(outer, textvariable=self.delay, width=12).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(fill="x", pady=15)
        ttk.Label(outer, text="Sweep and summary plots appear on Traces / CSV. Use that tab to place markers, set limits, compare overlays and export reports.\nMAT spectrogram exports include instrument clock, UTC, fixed EST and DST-aware Eastern timestamps.", wraplength=1000).pack(anchor="w")

    def loaded(self, rec, section):
        self.stop(); self.rec, self.section = rec, section
        self.slider.configure(to=len(section.sweep_indices)-1); self.index.set(0)
        self.status.set(f"{rec.path.name}: {len(section.sweep_indices)} selected sweeps. Move the slider to view a sweep.")

    def trace(self, values, name):
        return Trace(name, self.section.frequency_hz, values, "Frequency (Hz)", "Power (dBm)", str(self.rec.path),
                     {"selected_sweep_indices": self.section.sweep_indices.tolist(), "trace_slot": self.section.trace_slot})

    def show(self):
        if self.section is None: return
        try:
            index = max(0, min(self.index.get(), len(self.section.sweep_indices)-1))
            trace = self.trace(self.section.power_dbm[index], f"Sweep {self.section.sweep_indices[index]}")
            from fieldfox_recording.timezones import convert_timestamps
            converted = convert_timestamps(self.section.timestamp_ticks[index:index+1], source_timezone=self.app.viewer.timezone.get() or None,
                          dst_fold={"Ask if ambiguous": None, "Earlier occurrence": 0, "Later occurrence": 1}[self.app.viewer.fold.get()])
            trace.metadata.update({k: v[0].item() for k, v in converted.items() if isinstance(v, np.ndarray) and len(v) == 1})
            self.app.plots.add_trace(trace, replace=True)
            self.status.set(f"Sweep {self.section.sweep_indices[index]}, elapsed {self.section.elapsed_s[index]:.7g} s. UTC {converted['timestamp_utc'][0]}; EST {converted['timestamp_est'][0]}.")
        except Exception as error: self.stop(); self.app.error(error)

    def move(self, amount):
        if self.section is not None:
            self.index.set(max(0, min(self.index.get()+amount, len(self.section.sweep_indices)-1))); self.show()

    def toggle(self):
        if self.playing: self.stop(); return
        try:
            delay = int(self.delay.get())
            if not 100 <= delay <= 10000: raise ValueError("Playback delay must be 100..10000 ms.")
            if self.section is None: raise ValueError("Load a session section first.")
            self.playing = True; self.app.tabs.select(self.app.trace_tab); self._tick()
        except Exception as error: self.app.error(error)

    def _tick(self):
        if not self.playing: return
        self.show()
        if not self.playing: return
        index = self.index.get()+1
        if index >= len(self.section.sweep_indices): self.stop(); return
        self.index.set(index)
        try: delay = max(100, min(10000, int(self.delay.get())))
        except ValueError: delay = 250
        self.timer = self.app.root.after(delay, self._tick)

    def stop(self):
        self.playing = False
        if self.timer is not None: self.app.root.after_cancel(self.timer); self.timer = None

    def summary(self, kind):
        if self.section is None: self.app.error(ValueError("Load a session section first.")); return
        data = self.section.power_dbm
        if kind == "Maximum hold": values = data.max(axis=0)
        elif kind == "Minimum hold": values = data.min(axis=0)
        else:
            # Numerically stable mean of linear power, bounded by the section cap.
            reference = data.max(axis=0).astype(np.float64)
            total = np.zeros(data.shape[1], dtype=np.float64)
            for row in data: total += np.power(10., (row-reference)/10.)
            values = reference + 10*np.log10(total/len(data))
        try:
            self.app.plots.add_trace(self.trace(values, kind))
            self.app.tabs.select(self.app.trace_tab)
        except Exception as error: self.app.error(error)
