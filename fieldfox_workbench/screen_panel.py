from pathlib import Path

from .instrument import capture_file


class ScreenPanel:
    def __init__(self, app, parent):
        import tkinter as tk
        from tkinter import ttk
        self.app = app; self.image_path = None; self.photo = None
        self.drive = tk.StringVar(value="INTERNAL")
        self.status = tk.StringVar(value="Capture creates a unique temporary file on the selected instrument storage, downloads it and removes that temporary file.")
        outer = ttk.Frame(parent, padding=12); outer.pack(fill="both", expand=True)
        actions = ttk.Frame(outer); actions.pack(fill="x")
        ttk.Label(actions, text="Capture storage").pack(side="left")
        ttk.Combobox(actions, textvariable=self.drive, values=["INTERNAL", "SDCARD", "USBDISK", "USBDISK1", "USBDISK2"], state="readonly", width=13).pack(side="left", padx=8)
        for text, command in [("Capture PNG…", lambda: self.capture("png")),
                              ("Capture CSV…", lambda: self.capture("csv")),
                              ("Open image…", self.open_image), ("Save copy…", self.save_copy)]:
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=5)
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(fill="x", pady=12)
        self.preview = ttk.Label(outer, text="Screenshots appear here.", anchor="center")
        self.preview.pack(fill="both", expand=True)

    def capture(self, kind):
        from tkinter import filedialog
        if self.app.jobs.busy: self.app.status.set("Wait for the current operation."); return
        try: client = self.app.client()
        except Exception as error: self.app.error(error); return
        output = filedialog.asksaveasfilename(parent=self.app.root, title=f"Save captured {kind.upper()} to a new file",
                    defaultextension=f".{kind}", confirmoverwrite=False, filetypes=[(kind.upper(), f"*.{kind}")])
        if not output: return
        drive = self.drive.get()
        def done(result):
            self.status.set(result["warning"] or f"Saved {result['bytes']:,} bytes to {output}; temporary instrument file removed.")
            self.app.open_path(output)
        self.app.jobs.submit(lambda: capture_file(client, output, kind=kind, drive=drive,
                    cancel=self.app.jobs.cancel, progress=self.app.jobs.report), done, f"Capturing {kind.upper()}…")

    def open_image(self, path=None):
        from tkinter import filedialog
        from PIL import Image, ImageTk
        if path is None: path = filedialog.askopenfilename(parent=self.app.root, filetypes=[("Image", "*.png *.jpg *.jpeg *.bmp")])
        if not path: return
        try:
            path = Path(path)
            if path.stat().st_size > 32*1024**2: raise ValueError("Image exceeds 32 MiB.")
            with Image.open(path) as original:
                if original.width * original.height > 16_000_000: raise ValueError("Image exceeds 16 million pixels.")
                image = original.convert("RGB"); image.thumbnail((1100, 680))
                self.photo = ImageTk.PhotoImage(image, master=self.app.root)
            self.preview.configure(image=self.photo, text="")
            self.image_path = path; self.status.set(str(path)); self.app.remember(path)
        except Exception as error: self.app.error(error)

    def save_copy(self):
        from tkinter import filedialog
        from fieldfox_browser.client import destination
        import shutil
        try:
            if self.image_path is None: raise ValueError("Capture or open an image first.")
            output = filedialog.asksaveasfilename(parent=self.app.root, initialfile=self.image_path.name, confirmoverwrite=False)
            if not output: return
            with destination(output) as (_, stream), self.image_path.open("rb") as source:
                shutil.copyfileobj(source, stream, 65536)
            self.app.status.set(f"Saved unchanged image to {output}")
        except Exception as error: self.app.error(error)
