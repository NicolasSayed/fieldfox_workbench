"""Playback reuses only the loaded spectrogram section, never rereads the session."""
import numpy as np

from .traces import Trace


class Playback:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        self.app = app; self.rec = self.section = None; self.playing = False; self.timer = None
        self._shown = self._active_trace = None
        self.index = tk.IntVar(); self.delay = tk.StringVar(value="250")
        self.index.trace_add("write", lambda *_: self.show())
        self.status = tk.StringVar(value="Load a session section on the Session spectrogram tab first.")
        self.outer = outer = ttk.Frame(parent); outer.pack(fill="x")
        self.slider = tk.Scale(outer, from_=0, to=0, variable=self.index, orient="horizontal", command=lambda _: self.show(),
                               showvalue=False, takefocus=True, state="disabled", highlightthickness=0)
        self.slider.pack(fill="x")
        self.slider.bind("<MouseWheel>", self._wheel)
        buttons = ttk.Frame(outer); buttons.pack(fill="x")
        self.buttons = []
        for text, command in [("Previous", lambda: self.move(-1)), ("Play", self.toggle), ("Next", lambda: self.move(1)),
                              ("Maximum hold", lambda: self.summary("Maximum hold")),
                              ("Minimum hold", lambda: self.summary("Minimum hold")),
                              ("Power mean", lambda: self.summary("Power mean"))]:
            button = ttk.Button(buttons, text=text, command=command, state="disabled")
            button.pack(side="left", padx=(0, 5)); self.buttons.append(button)
            if text == "Play": self.play_button = button
        ttk.Label(buttons, text="Delay (ms)").pack(side="left", padx=(8, 4))
        ttk.Entry(buttons, textvariable=self.delay, width=7).pack(side="left")
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(fill="x", pady=(3, 1))

    def loaded(self, rec, section):
        self.stop(); self.rec, self.section = rec, section
        self._shown = self._active_trace = None
        self.slider.configure(to=len(section.sweep_indices)-1, state="normal"); self.index.set(0)
        for button in self.buttons: button.configure(state="normal")
        self.show()

    def trace(self, values, name):
        return Trace(name, self.section.frequency_hz, values, "Frequency (Hz)", "Power (dBm)", str(self.rec.path),
                     {"selected_sweep_indices": self.section.sweep_indices.tolist(), "trace_slot": self.section.trace_slot})

    def show(self):
        if self.section is None: return
        try:
            index = max(0, min(self.index.get(), len(self.section.sweep_indices)-1))
            key = (id(self.section), index, self.app.viewer.timezone.get(), self.app.viewer.fold.get())
            if key == self._shown and any(t is self._active_trace for t in self.app.plots.traces): return
            trace = self.trace(self.section.power_dbm[index], f"Sweep {self.section.sweep_indices[index]}")
            from fieldfox_recording.timezones import convert_timestamps
            converted = convert_timestamps(self.section.timestamp_ticks[index:index+1], source_timezone=self.app.viewer.timezone.get() or None,
                          dst_fold={"Ask if ambiguous": None, "Earlier occurrence": 0, "Later occurrence": 1}[self.app.viewer.fold.get()])
            trace.metadata.update({k: v[0].item() for k, v in converted.items() if isinstance(v, np.ndarray) and len(v) == 1})
            self.app.plots.add_trace(trace, replace=True)
            self._shown, self._active_trace = key, trace
            self.status.set(f"{self.rec.path.name} · row {index+1}/{len(self.section.sweep_indices)} · sweep {self.section.sweep_indices[index]} · {self.section.elapsed_s[index]:.7g} s\nUTC {converted['timestamp_utc'][0]}   EST {converted['timestamp_est'][0]}")
        except Exception as error: self.stop(); self.app.error(error)

    def move(self, amount):
        if self.section is not None:
            self.stop()
            self.index.set(max(0, min(self.index.get()+amount, len(self.section.sweep_indices)-1))); self.show()

    def _wheel(self, event):
        if event.delta: self.move(-1 if event.delta > 0 else 1)
        return "break"

    def toggle(self):
        if self.playing: self.stop(); return
        try:
            delay = int(self.delay.get())
            if not 100 <= delay <= 10000: raise ValueError("Playback delay must be 100..10000 ms.")
            if self.section is None: raise ValueError("Load a session section first.")
            if self.index.get() == len(self.section.sweep_indices)-1: self.index.set(0)
            self.playing = True; self.play_button.configure(text="Pause")
            self.app.tabs.select(self.app.trace_tab); self._tick()
        except Exception as error: self.app.error(error)

    def _tick(self):
        if not self.playing: return
        self.show()
        if not self.playing: return
        if self.index.get() >= len(self.section.sweep_indices)-1: self.stop(); return
        try: delay = max(100, min(10000, int(self.delay.get())))
        except ValueError: delay = 250
        self.timer = self.app.root.after(delay, self._advance)

    def _advance(self):
        self.timer = None
        if self.playing:
            self.index.set(min(self.index.get()+1, len(self.section.sweep_indices)-1)); self._tick()

    def stop(self):
        self.playing = False
        self.play_button.configure(text="Play")
        if self.timer is not None: self.app.root.after_cancel(self.timer); self.timer = None

    def summary(self, kind):
        if self.section is None: self.app.error(ValueError("Load a session section first.")); return
        self.stop()
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
