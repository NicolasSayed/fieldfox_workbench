"""Playback reuses only the loaded spectrogram section, never rereads the session."""
import numpy as np

from .traces import Trace


class RunningHolds:
    """Extrema from the start/reset row through the current playback row.

    Forward jumps include intervening selected rows. Backward seeks recalculate
    to avoid retaining future data; seeking before the reset row reanchors there.
    Only two point-sized buffers are kept in addition to the loaded section.
    """
    def __init__(self, values):
        self.values = np.asarray(values)
        if self.values.ndim != 2 or not all(self.values.shape):
            raise ValueError("Running holds need a nonempty sweeps × points matrix.")
        self.start_row = 0; self.last_row = -1
        self.maximum = self.minimum = None

    def update(self, row):
        if not 0 <= row < len(self.values): raise ValueError("Hold row is outside the selected section.")
        if row < self.start_row: self.start_row = row
        if self.maximum is None or row < self.last_row:
            block = self.values[self.start_row:row+1]
            self.maximum = block.max(axis=0)
            self.minimum = block.min(axis=0)
        elif row > self.last_row:
            block = self.values[max(self.start_row, self.last_row+1):row+1]
            np.maximum(self.maximum, block.max(axis=0), out=self.maximum)
            np.minimum(self.minimum, block.min(axis=0), out=self.minimum)
        self.last_row = row
        return self.maximum, self.minimum

    def reset(self, row):
        if not 0 <= row < len(self.values): raise ValueError("Hold reset row is outside the selected section.")
        self.start_row = row; self.last_row = -1
        self.maximum = self.minimum = None
        return self.update(row)


class Playback:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        self.app = app; self.rec = self.section = None; self.playing = False; self.timer = None
        self._shown = self._active_trace = self.holds = None
        self._active_traces = []
        self.max_hold = tk.BooleanVar(); self.min_hold = tk.BooleanVar()
        self.max_hold.trace_add("write", lambda *_: self.show())
        self.min_hold.trace_add("write", lambda *_: self.show())
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
                              ("Section mean", lambda: self.summary("Power mean"))]:
            button = ttk.Button(buttons, text=text, command=command, state="disabled")
            button.pack(side="left", padx=(0, 5)); self.buttons.append(button)
            if text == "Play": self.play_button = button
        ttk.Label(buttons, text="Delay (ms)").pack(side="left", padx=(8, 4))
        ttk.Entry(buttons, textvariable=self.delay, width=7).pack(side="left")
        holding = ttk.Frame(outer); holding.pack(fill="x", pady=(3, 0))
        for text, variable in [("Max hold", self.max_hold), ("Min hold", self.min_hold)]:
            button = ttk.Checkbutton(holding, text=text, variable=variable, state="disabled")
            button.pack(side="left", padx=(0, 10)); self.buttons.append(button)
        self.reset_button = ttk.Button(holding, text="Reset holds here", command=self.reset_holds, state="disabled")
        self.reset_button.pack(side="left", padx=(0, 10)); self.buttons.append(self.reset_button)
        ttk.Label(holding, text="Selected sweeps: start/reset → cursor; backward seeks recalculate.").pack(side="left")
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(fill="x", pady=(3, 1))

    def loaded(self, rec, section):
        self.stop(); self.rec, self.section = rec, section
        self._shown = self._active_trace = None
        self._active_traces = []; self.holds = RunningHolds(section.power_dbm)
        self.slider.configure(to=len(section.sweep_indices)-1, state="normal"); self.index.set(0)
        for button in self.buttons: button.configure(state="normal")
        self.show()

    def trace(self, values, name, **metadata):
        return Trace(name, self.section.frequency_hz, values, "Frequency (Hz)", "Power (dBm)", str(self.rec.path),
                     {"selected_sweep_indices": self.section.sweep_indices.tolist(), "trace_slot": self.section.trace_slot, **metadata})

    def show(self):
        if self.section is None: return
        try:
            index = max(0, min(self.index.get(), len(self.section.sweep_indices)-1))
            maximum, minimum = self.holds.update(index)
            key = (id(self.section), index, self.app.viewer.timezone.get(), self.app.viewer.fold.get(),
                   self.max_hold.get(), self.min_hold.get(), self.holds.start_row)
            if key == self._shown and all(any(t is active for t in self.app.plots.traces) for active in self._active_traces): return
            trace = self.trace(self.section.power_dbm[index], f"Sweep {self.section.sweep_indices[index]}", trace_role="playback_current")
            from fieldfox_recording.timezones import convert_timestamps
            converted = convert_timestamps(self.section.timestamp_ticks[index:index+1], source_timezone=self.app.viewer.timezone.get() or None,
                          dst_fold={"Ask if ambiguous": None, "Earlier occurrence": 0, "Later occurrence": 1}[self.app.viewer.fold.get()])
            trace.metadata.update({k: v[0].item() for k, v in converted.items() if isinstance(v, np.ndarray) and len(v) == 1})
            traces = [trace]
            first = int(self.section.sweep_indices[self.holds.start_row]); last = int(self.section.sweep_indices[index])
            for enabled, values, name, role in [(self.max_hold.get(), maximum, "Max hold", "playback_max_hold"),
                                                 (self.min_hold.get(), minimum, "Min hold", "playback_min_hold")]:
                if enabled:
                    traces.append(self.trace(np.array(values, dtype=np.float64, copy=True), name, trace_role=role, hold_start_sweep=first, hold_stop_sweep=last,
                                  hold_start_row=self.holds.start_row, hold_stop_row=index,
                                  hold_scope="All selected rows from start/reset through cursor; backward seeks recalculate."))
            self.app.plots.set_playback_traces(traces, clear_markers=key[:2] != (self._shown or ())[:2])
            self._shown, self._active_trace = key, trace
            self._active_traces = traces
            self.status.set(f"{self.rec.path.name} · row {index+1}/{len(self.section.sweep_indices)} · sweep {self.section.sweep_indices[index]} · {self.section.elapsed_s[index]:.7g} s · hold sweeps {first}–{last}\nUTC {converted['timestamp_utc'][0]}   EST {converted['timestamp_est'][0]}")
        except Exception as error: self.stop(); self.app.error(error)

    def reset_holds(self):
        if self.section is None: return
        self.holds.reset(self.index.get()); self._shown = None; self.show()

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
            if hasattr(self.app, "_activity"): self.app._activity(self.app.jobs.busy)
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
        if hasattr(self.app, "_activity"): self.app._activity(self.app.jobs.busy)
        if self.timer is not None: self.app.root.after_cancel(self.timer); self.timer = None

    def summary(self, kind):
        if self.section is None: self.app.error(ValueError("Load a session section first.")); return
        if kind in {"Maximum hold", "Minimum hold"}:
            (self.max_hold if kind == "Maximum hold" else self.min_hold).set(True)
            self.app.tabs.select(self.app.trace_tab); return
        self.stop()
        data = self.section.power_dbm
        # Numerically stable mean of linear power, bounded by the section cap.
        reference = data.max(axis=0).astype(np.float64)
        total = np.zeros(data.shape[1], dtype=np.float64)
        for row in data: total += np.power(10., (row-reference)/10.)
        values = reference + 10*np.log10(total/len(data))
        try:
            self.app.plots.add_trace(self.trace(values, "Section power mean"))
            self.app.tabs.select(self.app.trace_tab)
        except Exception as error: self.app.error(error)
