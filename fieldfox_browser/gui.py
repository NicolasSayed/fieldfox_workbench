"""Tkinter file browser; also runnable directly from an IDE."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import queue
import sys
import threading
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "fieldfox_browser"

from .client import BrowserError, Cancelled, DRIVES, FieldFoxClient, RemotePath, component
from .preview import make_preview, preview_local


class BrowserApp:
    def __init__(self, root, *, parent=None, embedded=False, on_download=None):
        import tkinter as tk
        from tkinter import ttk
        self.root = root; self.busy = False; self.closing = False
        self.on_download = on_download
        self.external_busy = lambda: False
        self.preview_epoch = 0; self.preview_after = None; self.preview_result = None
        self.results = queue.Queue(); self.cancel = threading.Event(); self.last_report = 0
        self.entries = {}; self.catalog = None; self.loaded = None
        self.host = tk.StringVar(); self.port = tk.StringVar(value="5025")
        self.timeout = tk.StringVar(value="10"); self.drive = tk.StringVar(value="INTERNAL")
        self.path = tk.StringVar(value="[INTERNAL]:\\"); self.filter = tk.StringVar()
        self.identity = tk.StringVar(value="Enter the FieldFox IP address or hostname.")
        self.status = tk.StringVar(value="Browse instrument files, then download a file or complete session folder.")
        if not embedded:
            root.title("FieldFox Ethernet file browser"); root.geometry("1040x650"); root.minsize(820, 500)
        frame = ttk.Frame(parent if parent is not None else root, padding=10); frame.pack(fill="both", expand=True)
        connection = ttk.LabelFrame(frame, text="Instrument connection", padding=(10, 8)); connection.pack(fill="x")
        self.inputs = []; self.buttons = []
        for text, variable, width in [("Instrument IP / hostname", self.host, 28), ("Port", self.port, 7), ("Timeout (s)", self.timeout, 6)]:
            ttk.Label(connection, text=text).pack(side="left", padx=(0, 5))
            widget = ttk.Entry(connection, textvariable=variable, width=width); widget.pack(side="left", padx=(0, 10)); self.inputs.append(widget)
        self._button(connection, "Connect / browse", self.browse, style="Accent.TButton").pack(side="left")
        ttk.Label(frame, textvariable=self.identity, style="Muted.TLabel").pack(fill="x", pady=(10, 8))
        navigation = ttk.Frame(frame); navigation.pack(fill="x")
        storage = ttk.Combobox(navigation, textvariable=self.drive, values=DRIVES, state="readonly", width=12)
        storage.pack(side="left", padx=(0, 7)); self.inputs.append(storage); self.storage = storage
        storage.bind("<<ComboboxSelected>>", lambda _: self.path.set(f"[{self.drive.get()}]:\\"))
        path_entry = ttk.Entry(navigation, textvariable=self.path); path_entry.pack(side="left", fill="x", expand=True, padx=(0, 7)); self.inputs.append(path_entry)
        path_entry.bind("<Return>", lambda _: self.browse())
        self._button(navigation, "Go / refresh", self.browse).pack(side="left", padx=(0, 7))
        self._button(navigation, "Up", self.up).pack(side="left")
        filtering = ttk.Frame(frame); filtering.pack(fill="x", pady=8)
        ttk.Label(filtering, text="Filter names").pack(side="left")
        ttk.Entry(filtering, textvariable=self.filter).pack(side="left", fill="x", expand=True, padx=8)
        self.filter.trace_add("write", lambda *_: self._render())
        self.panes = ttk.Panedwindow(frame, orient="horizontal"); self.panes.pack(fill="both", expand=True)
        table = ttk.Frame(self.panes); self.panes.add(table, weight=3)
        self.tree = ttk.Treeview(table, columns=("kind", "bytes", "type"), selectmode="browse")
        for name, title, width in [("#0", "Name", 290), ("kind", "Kind", 75), ("bytes", "Bytes", 105), ("type", "Type", 65)]:
            self.tree.heading(name, text=title); self.tree.column(name, width=width, minwidth=55 if name != "#0" else 150, anchor="e" if name == "bytes" else "w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        table.rowconfigure(0, weight=1); table.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew"); scroll.grid(row=0, column=1, sticky="ns"); horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<<TreeviewSelect>>", self._preview_selection)
        preview = ttk.LabelFrame(self.panes, text="File preview", padding=10); self.panes.add(preview, weight=2)
        self.preview_name = tk.StringVar(value="Select a file")
        self.preview_info = tk.StringVar(value="Text preview · read-only · up to 256 KiB")
        ttk.Label(preview, textvariable=self.preview_name, style="Section.TLabel", wraplength=450).pack(fill="x")
        ttk.Label(preview, textvariable=self.preview_info, style="Muted.TLabel", wraplength=450).pack(fill="x", pady=(4, 8))
        preview_actions = ttk.Frame(preview); preview_actions.pack(fill="x", pady=(0, 7))
        ttk.Button(preview_actions, text="Preview selected", command=self.preview_selected).pack(side="left", padx=(0, 6))
        ttk.Button(preview_actions, text="Open local…", command=self.open_local_preview).pack(side="left")
        self.preview_wrap = tk.BooleanVar()
        ttk.Checkbutton(preview_actions, text="Wrap", variable=self.preview_wrap,
                        command=lambda: self.preview_text.configure(wrap="word" if self.preview_wrap.get() else "none")).pack(side="right")
        find = ttk.Frame(preview); find.pack(fill="x", pady=(0, 7))
        self.preview_query = tk.StringVar()
        query_entry = ttk.Entry(find, textvariable=self.preview_query)
        query_entry.pack(side="left", fill="x", expand=True, padx=(0, 6)); query_entry.bind("<Return>", lambda _: self.find_preview())
        ttk.Button(find, text="Find next", command=self.find_preview).pack(side="right")
        area = ttk.Frame(preview); area.pack(fill="both", expand=True)
        area.rowconfigure(0, weight=1); area.columnconfigure(0, weight=1)
        self.preview_text = tk.Text(area, wrap="none", state="disabled", font="TkFixedFont", width=34, height=8,
                                    borderwidth=0, padx=10, pady=8, highlightthickness=1, highlightbackground="#D7DFEB")
        vs = ttk.Scrollbar(area, orient="vertical", command=self.preview_text.yview)
        hs = ttk.Scrollbar(area, orient="horizontal", command=self.preview_text.xview)
        self.preview_text.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.preview_text.grid(row=0, column=0, sticky="nsew"); vs.grid(row=0, column=1, sticky="ns"); hs.grid(row=1, column=0, sticky="ew")
        self.preview_text.tag_configure("match", background="#FFE8A3", foreground="#18283E")
        self.preview_text.bind("<Control-a>", self._select_all_preview)
        self._set_preview_text("Select an instrument file to inspect its contents.\n\nText stays read-only. Binary files show hexadecimal bytes. Large files show a bounded prefix.")
        self._sash_ready = False
        preview.bind("<Configure>", lambda event: [label.configure(wraplength=max(180, event.width-26)) for label in preview.winfo_children() if isinstance(label, ttk.Label)])
        def position_sash(event):
            if not self._sash_ready and event.width > 650:
                self.panes.sashpos(0, int(event.width*.55)); self._sash_ready = True
        self.panes.bind("<Configure>", position_sash)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=8)
        self._button(actions, "Download selected", self.download_selected).pack(side="left", padx=(0, 8))
        self._button(actions, "Download current folder", self.download_current).pack(side="left", padx=(0, 8))
        self._button(actions, "Save listing JSON", self.save_listing).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Cancel", command=self.cancel.set).pack(side="right")
        ttk.Label(frame, textvariable=self.status, wraplength=1000).pack(fill="x")
        if not embedded:
            root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self._poll)

    def _button(self, parent, text, command, **options):
        from tkinter import ttk
        button = ttk.Button(parent, text=text, command=command, **options); self.buttons.append(button); return button

    def _set_preview_text(self, text):
        self.preview_text.configure(state="normal"); self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text); self.preview_text.configure(state="disabled")

    def _select_all_preview(self, event=None):
        self.preview_text.tag_add("sel", "1.0", "end-1c"); return "break"

    def find_preview(self):
        query = self.preview_query.get()
        self.preview_text.tag_remove("match", "1.0", "end")
        if not query: return
        ranges = self.preview_text.tag_ranges("sel")
        start = str(ranges[-1]) if ranges else "1.0"
        found = self.preview_text.search(query, start, stopindex="end", nocase=True)
        if not found: found = self.preview_text.search(query, "1.0", stopindex=start, nocase=True)
        if found:
            end = f"{found}+{len(query)}c"
            self.preview_text.tag_add("match", found, end); self.preview_text.tag_remove("sel", "1.0", "end")
            self.preview_text.tag_add("sel", found, end); self.preview_text.see(found)

    def _cancel_preview_timer(self):
        if self.preview_after is not None:
            self.root.after_cancel(self.preview_after); self.preview_after = None

    def _preview_selection(self, event=None):
        self._cancel_preview_timer(); self.preview_epoch += 1
        self.preview_result = None
        selection = self.tree.selection(); entry = self.entries.get(selection[0]) if selection else None
        if entry is None or entry.is_dir:
            self.preview_name.set(entry.name if entry else "Select a file")
            self.preview_info.set("Select a file to preview its contents."); self._set_preview_text(""); return
        self.preview_name.set(entry.name); self.preview_info.set("Waiting to read preview…"); self._set_preview_text("")
        self.preview_after = self.root.after(200, self.preview_selected)

    def preview_selected(self):
        self._cancel_preview_timer()
        selection = self.tree.selection(); entry = self.entries.get(selection[0]) if selection else None
        if entry is None or entry.is_dir: return
        if self.busy or self.external_busy():
            self.preview_after = self.root.after(200, self.preview_selected); return
        try:
            client, path = self._settings()
            key = self._key(client, path)
            if key != self.loaded:
                self.preview_info.set("Connect / browse to apply the current host and folder first."); return
        except (ValueError, OSError) as error:
            self.preview_info.set(str(error)); return
        epoch = self.preview_epoch; remote = path.child(entry.name)
        self.preview_name.set(entry.name); self.preview_info.set("Reading preview…")
        def work():
            try: return make_preview(*client.read_prefix(remote, expected_size=entry.size, cancel=self.cancel)), None
            except Cancelled: raise
            except Exception as error: return None, str(error)
        def done(result):
            if epoch != self.preview_epoch or self.loaded != key: return
            preview, error = result
            if error:
                self.preview_info.set("Preview unavailable"); self._set_preview_text(error); return
            self._show_preview(preview)
        self._job(work, done, "Reading file preview…")

    def _show_preview(self, preview):
        self.preview_result = preview; self.preview_info.set(preview.description); self._set_preview_text(preview.text)
        self.status.set(f"Preview: {self.preview_name.get()} · {preview.description}")

    def open_local_preview(self, path=None):
        from tkinter import filedialog
        if self.busy or self.external_busy(): return
        if path is None: path = filedialog.askopenfilename(parent=self.root, title="Preview a local file", filetypes=[("Text / CSV", "*.txt *.csv *.xml *.json *.log *.md"), ("All files", "*")])
        if not path: return
        self._cancel_preview_timer(); self.preview_epoch += 1; epoch = self.preview_epoch
        self.preview_name.set(Path(path).name); self.preview_info.set("Reading local preview…")
        def done(preview):
            if epoch == self.preview_epoch: self._show_preview(preview)
        self._job(lambda: preview_local(path), done, "Reading local file preview…")

    def _settings(self):
        client = FieldFoxClient(self.host.get().strip(), int(self.port.get()), float(self.timeout.get()))
        return client, RemotePath.parse(self.path.get())

    def _key(self, client, path):
        return (client.host, client.port, client.timeout, str(path))

    def _error(self, error):
        from tkinter import messagebox
        self.status.set(str(error)); messagebox.showerror("FieldFox browser", str(error), parent=self.root)

    def _report(self, text):
        now = time.monotonic()
        if now-self.last_report >= .1:
            self.last_report = now; self.results.put(("progress", text, None))

    def _job(self, work, done, message):
        if self.busy:
            self.status.set("An operation is already running."); return
        self.cancel.clear(); self.busy = True; self.last_report = 0; self.status.set(message)
        for widget in self.inputs + self.buttons:
            widget.configure(state="disabled")
        def worker():
            try: self.results.put((done, work(), None))
            except Exception as error: self.results.put((done, None, error))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        while True:
            try: callback, value, error = self.results.get_nowait()
            except queue.Empty: break
            if callback == "progress":
                self.status.set(value); continue
            self.busy = False
            for widget in self.inputs + self.buttons:
                widget.configure(state="normal")
            self.storage.configure(state="readonly")
            if not self.closing:
                if isinstance(error, Cancelled): self.status.set(str(error))
                elif error is not None: self._error(error)
                else:
                    try: callback(value)
                    except Exception as failure: self._error(failure)
        if self.closing and not self.busy:
            self.root.destroy(); return
        self.root.after(100, self._poll)

    def browse(self):
        try: client, path = self._settings()
        except (ValueError, OSError) as error: self._error(error); return
        def done(result):
            identity, self.catalog = result
            self.identity.set(identity); self.path.set(str(path)); self.loaded = self._key(client, path)
            self._render()
            self.status.set(f"{len(self.catalog.entries)} entries. Storage free: {self.catalog.free_bytes:,} bytes.")
        self._job(lambda: client.browse(path, self.cancel), done, "Connecting and listing folder…")

    def _render(self):
        self._cancel_preview_timer(); self.preview_epoch += 1
        self.preview_result = None; self.preview_name.set("Select a file")
        self.preview_info.set("Text preview · read-only · up to 256 KiB"); self._set_preview_text("")
        self.tree.delete(*self.tree.get_children()); self.entries = {}
        if self.catalog is None: return
        query = self.filter.get().casefold()
        for number, entry in enumerate(self.catalog.entries):
            if query not in entry.name.casefold(): continue
            iid = str(number); self.entries[iid] = entry
            self.tree.insert("", "end", iid=iid, text=entry.name, values=("Folder" if entry.is_dir else "File", "" if entry.size is None or entry.is_dir else f"{entry.size:,}", entry.file_type))

    def _ready(self):
        if self.busy: return None
        try:
            client, path = self._settings()
            if self.catalog is None or self.loaded != self._key(client, path):
                raise BrowserError("Click Connect / browse to apply the current host and folder first.")
            return client, path
        except (ValueError, OSError) as error:
            self._error(error); return None

    def up(self):
        if self.busy: return
        try: self.path.set(str(RemotePath.parse(self.path.get()).parent)); self.browse()
        except BrowserError as error: self._error(error)

    def open_selected(self, event=None):
        ready = self._ready(); selection = self.tree.selection()
        if ready is None or not selection: return
        entry = self.entries[selection[0]]
        if entry.is_dir:
            self.path.set(str(ready[1].child(entry.name))); self.browse()

    def _folder_download(self, client, remote):
        from tkinter import filedialog, simpledialog
        parent = filedialog.askdirectory(title="Choose the parent directory for a NEW local folder", parent=self.root)
        if not parent: return
        name = simpledialog.askstring("Local folder", "New folder name", initialvalue=remote.name, parent=self.root)
        if name is None: return
        try: target = Path(parent) / component(name, local=True)
        except BrowserError as error: self._error(error); return
        self._job(lambda: client.download_folder(remote, target, cancel=self.cancel, progress=self._report),
                  lambda r: self._downloaded(r, True), "Planning folder download…")

    def _downloaded(self, result, folder=False):
        target = result["destination"] if folder else result["local_path"]
        self.status.set(f"Saved {result['bytes']:,} bytes to {target}.")
        if self.on_download is not None:
            self.on_download(Path(target))

    def download_selected(self):
        from tkinter import filedialog
        ready = self._ready(); selection = self.tree.selection()
        if ready is None: return
        if not selection: self.status.set("Select a file or folder first."); return
        client, path = ready; entry = self.entries[selection[0]]; remote = path.child(entry.name)
        if entry.is_dir: self._folder_download(client, remote); return
        target = filedialog.asksaveasfilename(title="Download file to a NEW local filename", initialfile=entry.name, confirmoverwrite=False, parent=self.root)
        if target:
            self._job(lambda: client.download_file(remote, target, expected_size=entry.size, cancel=self.cancel, progress=self._report),
                      lambda r: self._downloaded(r), "Downloading file…")

    def download_current(self):
        ready = self._ready()
        if ready is not None: self._folder_download(*ready)

    def save_listing(self):
        from tkinter import filedialog
        if self._ready() is None: return
        target = filedialog.asksaveasfilename(title="Save folder listing", defaultextension=".json", confirmoverwrite=False, parent=self.root)
        if not target: return
        try:
            with open(target, "x", encoding="utf-8") as stream:
                json.dump({"path": self.path.get(), "identity": self.identity.get(), **asdict(self.catalog)}, stream, indent=2, ensure_ascii=False)
            self.status.set(f"Saved {target}")
        except OSError as error: self._error(error)

    def close(self):
        self._cancel_preview_timer()
        self.closing = True; self.cancel.set()
        if not self.busy: self.root.destroy()
        else: self.status.set("Stopping transfer and cleaning temporary files; waiting for the socket timeout if needed…")


def main():
    try:
        import tkinter as tk
    except ImportError as error:
        raise BrowserError("The GUI needs a Python installation with Tkinter; the CLI uses only the standard library.") from error
    root = tk.Tk(); BrowserApp(root); root.mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
