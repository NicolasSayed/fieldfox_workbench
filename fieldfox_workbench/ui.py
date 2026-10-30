"""Shared Tk styles and window sizing, without extra theme dependencies."""
import sys

BACKGROUND = "#F3F5F9"
SURFACE = "#FFFFFF"
INK = "#18283E"
MUTED = "#5F7086"
ACCENT = "#245FD3"
BORDER = "#D7DFEB"


def work_area(root):
    area = (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):
            area = rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top
    return area


def fit_window(root):
    left, top, available_width, available_height = work_area(root)
    width, height = min(1280, available_width-48), min(900, available_height-88)
    root.geometry(f"{width}x{height}+{left+24}+{top+24}")
    root.minsize(min(950, width), min(650, height))


def apply_theme(root):
    from tkinter import ttk, font
    family = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        font.nametofont(name, root=root).configure(family=family, size=10)
    font.nametofont("TkFixedFont", root=root).configure(family="Consolas" if sys.platform == "win32" else "DejaVu Sans Mono", size=10)
    style = ttk.Style(root); style.theme_use("clam")
    root.configure(background=BACKGROUND)
    style.configure(".", background=BACKGROUND, foreground=INK, font="TkDefaultFont")
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, foreground=INK)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Heading.TLabel", font=(family, 15, "bold"), foreground=INK)
    style.configure("Section.TLabel", font=(family, 11, "bold"))
    style.configure("Header.TFrame", background="#142B45")
    style.configure("Header.TLabel", background="#142B45", foreground=SURFACE, font=(family, 17, "bold"))
    style.configure("HeaderMuted.TLabel", background="#142B45", foreground="#B7CBE3", font=(family, 9))
    style.configure("TButton", padding=(11, 6), background=SURFACE, foreground=INK, bordercolor=BORDER, relief="flat", focusthickness=1)
    style.map("TButton", background=[("disabled", "#ECF0F5"), ("pressed", "#DEE8F9"), ("active", "#EAF0FB")],
              foreground=[("disabled", "#8793A5")], bordercolor=[("focus", ACCENT)])
    style.configure("Accent.TButton", background=ACCENT, foreground=SURFACE, bordercolor=ACCENT)
    style.map("Accent.TButton", background=[("disabled", "#A8BCDF"), ("pressed", "#164BAF"), ("active", "#3470E2")], foreground=[("disabled", SURFACE), ("!disabled", SURFACE)])
    style.configure("TEntry", fieldbackground=SURFACE, bordercolor=BORDER, padding=5)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=SURFACE, bordercolor=BORDER, arrowsize=13, padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", INK)])
    style.configure("TLabelframe", bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", foreground=MUTED, font=(family, 10, "bold"))
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=(0, 6, 0, 0))
    style.configure("TNotebook.Tab", padding=(17, 10), background="#E9EEF5", foreground=MUTED)
    style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", "#E4ECF9")], foreground=[("selected", ACCENT)])
    style.configure("Treeview", rowheight=29, fieldbackground=SURFACE, background=SURFACE, foreground=INK, bordercolor=BORDER)
    style.configure("Treeview.Heading", background="#EAF0F7", foreground=MUTED, padding=(8, 7), font=(family, 9, "bold"), relief="flat")
    style.map("Treeview", background=[("selected", "#DCE9FF")], foreground=[("selected", "#153D7C")])
    style.configure("TCheckbutton", padding=(3, 3))
    style.configure("TProgressbar", background=ACCENT, troughcolor="#E5EBF4", borderwidth=0, thickness=3)
    root.option_add("*Text.background", SURFACE); root.option_add("*Text.foreground", INK)
    root.option_add("*Text.selectBackground", "#C8DEFF"); root.option_add("*Text.selectForeground", INK)
    root.option_add("*Text.insertBackground", INK)
    from pathlib import Path
    import tkinter as tk
    icon = Path(__file__).resolve().parent / "assets" / "workbench.png"
    if icon.exists():
        root._workbench_icon = tk.PhotoImage(master=root, file=str(icon))
        root.iconphoto(True, root._workbench_icon)
    return style
