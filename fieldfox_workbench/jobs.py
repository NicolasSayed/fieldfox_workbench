"""One owned worker, cooperative cancellation, main-thread callbacks."""
import queue
import threading
import time

from fieldfox_browser.client import Cancelled


class Jobs:
    def __init__(self, root, status, on_error):
        self.root, self.status, self.on_error = root, status, on_error
        self.cancel = threading.Event(); self.results = queue.Queue()
        self.busy = False; self.closing = False; self.thread = None
        self.last_progress = 0
        self.on_busy = None
        root.after(70, self.poll)

    def submit(self, work, done, message, *, finished=None):
        if self.busy or self.closing:
            self.status.set("Wait for the current operation, or press Cancel.")
            return False
        self.busy = True; self.cancel.clear(); self.status.set(message)
        if self.on_busy: self.on_busy(True)
        def run():
            try:
                value = work(); error = None
            except Exception as failure:
                value, error = None, failure
            self.results.put((done, finished, value, error))
        self.thread = threading.Thread(target=run, name="FieldFox-operation", daemon=True)
        self.thread.start()
        return True

    def report(self, message):
        now = time.monotonic()
        if now-self.last_progress > .1:
            self.last_progress = now; self.results.put((None, None, message, None))

    def poll(self):
        while True:
            try: done, finished, value, error = self.results.get_nowait()
            except queue.Empty: break
            if done is None:
                self.status.set(value); continue
            self.busy = False
            if self.on_busy: self.on_busy(False)
            if finished is not None: finished()
            if self.closing: continue
            if error is not None:
                if isinstance(error, Cancelled) or self.cancel.is_set(): self.status.set(f"Cancelled: {error}")
                else: self.on_error(error)
            else:
                self.status.set("Complete.")
                try: done(value)
                except Exception as failure: self.on_error(failure)
        if self.closing and not self.busy:
            self.root.destroy(); return
        self.root.after(70, self.poll)
