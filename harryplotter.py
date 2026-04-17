"""
HarryPlotter - HDF5 Signal Viewer for Linux
"""
import os
import re
import tempfile
import webbrowser
import atexit
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from tkinter import BooleanVar, StringVar

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import h5py

try:
    import mplcursors
    MPLCURSORS_AVAILABLE = True
except ImportError:
    MPLCURSORS_AVAILABLE = False

try:
    import folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

np.set_printoptions(threshold=10)

APP_TITLE   = "Harry Plotter"
APP_VERSION = "v1.2"

# ── Catppuccin Mocha ──────────────────────────────────────────────────────────
C = dict(
    base    ="#1e1e2e", mantle  ="#181825", crust   ="#11111b",
    surface0="#313244", surface1="#45475a", surface2="#585b70",
    overlay0="#6c7086", overlay1="#7f849c",
    text    ="#cdd6f4", subtext0="#a6adc8", subtext1="#bac2de",
    lavender="#b4befe", blue    ="#89b4fa", sapphire="#74c7ec",
    sky     ="#89dceb", teal    ="#94e2d5", green   ="#a6e3a1",
    yellow  ="#f9e2af", peach   ="#fab387", maroon  ="#eba0ac",
    red     ="#f38ba8", mauve   ="#cba6f7", pink    ="#f5c2e7",
    flamingo="#f2cdcd",
)

PLOT_COLORS = [
    C["blue"], C["green"], C["peach"], C["mauve"],
    C["red"],  C["teal"],  C["yellow"],C["sapphire"],
    C["pink"], C["flamingo"], C["sky"], C["lavender"],
]

# ──────────────────────────────────────────────────────────────────────────────
# HDF5 helpers
# ──────────────────────────────────────────────────────────────────────────────

def collect_datasets(hdf_file):
    out = {}
    def _v(name, obj):
        if isinstance(obj, h5py.Dataset):
            out[name] = obj
    hdf_file.visititems(_v)
    return out

def load_signal(ds):
    data = ds[()]
    if data.ndim == 0:
        return np.array([float(data)])
    return np.squeeze(data)

# ──────────────────────────────────────────────────────────────────────────────
# Tooltip
# ──────────────────────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, widget, text):
        self._w = widget
        self._text = text
        self._tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _e=None):
        x = self._w.winfo_rootx() + 4
        y = self._w.winfo_rooty() + self._w.winfo_height() + 6
        self._tw = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self._text, bg=C["surface1"], fg=C["text"],
                 font=("monospace", 8), relief="flat",
                 padx=8, pady=4).pack()

    def _hide(self, _e=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None

# ──────────────────────────────────────────────────────────────────────────────
# Main App
# ──────────────────────────────────────────────────────────────────────────────

class HarryPlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} {APP_VERSION}")
        self.root.geometry("1440x900+40+40")
        self.root.configure(bg=C["base"])
        self.root.minsize(900, 600)

        # state
        self.file_path    = None
        self.hdf_files: dict = {}   # fname -> h5py.File  (all open files)
        self.hdf_file     = None    # kept for GPS compat (last opened)
        self.signals: dict = {}
        self.filtered_signals: list = []
        self.latitude:  list = []
        self.longitude: list = []
        self.graphs:   list = []
        self.toolbars: list = []
        self._sel_cache: list = []
        self._plotted_paths: list = []

        self.plot_together_var        = BooleanVar(value=False)
        self.use_time_as_xaxis_var    = BooleanVar(value=True)
        self.grid_var                 = BooleanVar(value=True)
        self.skip_first_sample_var    = BooleanVar(value=False)
        self.search_var               = StringVar()

        self.temp_map = os.path.join(tempfile.gettempdir(),
                                     "harryplotter_gps_map.html")
        atexit.register(self.cleanup)

        self._style()
        self._build()

        if DND_AVAILABLE:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

        self._prev_w = self.root.winfo_width()
        self._prev_h = self.root.winfo_height()
        self._resize_id = None
        self.root.bind("<Configure>", self._on_resize)
        self.root.bind("<Control-o>", lambda _: self.open_file())
        self.root.bind("<Control-l>", lambda _: self.clear_graphs())

    # ── ttk style ─────────────────────────────────────────────────────────────

    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        fui = ("Sans", 9)

        s.configure(".", background=C["base"], foreground=C["text"],
                    fieldbackground=C["surface0"], font=fui,
                    borderwidth=0, relief="flat")
        s.configure("TFrame", background=C["base"])
        s.configure("TLabel", background=C["base"], foreground=C["text"])
        s.configure("TEntry", fieldbackground=C["surface0"],
                    foreground=C["text"], insertcolor=C["text"])
        s.configure("TPanedwindow", background=C["surface1"])

        # Normal button
        s.configure("TButton", background=C["surface0"], foreground=C["text"],
                    padding=(12, 5), focusthickness=0, borderwidth=0)
        s.map("TButton",
              background=[("active", C["surface1"]),("pressed", C["surface2"])],
              foreground=[("active", C["text"])])

        # Accent button (blue)
        s.configure("Accent.TButton", background=C["blue"],
                    foreground=C["crust"], padding=(12, 5),
                    focusthickness=0, borderwidth=0,
                    font=("Sans", 9, "bold"))
        s.map("Accent.TButton",
              background=[("active", C["sapphire"]),("pressed", C["lavender"])],
              foreground=[("active", C["crust"])])

        # Danger button (red/clear)
        s.configure("Danger.TButton", background=C["surface0"],
                    foreground=C["maroon"], padding=(12, 5),
                    focusthickness=0, borderwidth=0)
        s.map("Danger.TButton",
              background=[("active", C["surface1"])],
              foreground=[("active", C["red"])])

        s.configure("TCheckbutton", background=C["mantle"],
                    foreground=C["subtext0"], focusthickness=0)
        s.map("TCheckbutton",
              foreground=[("selected", C["text"]), ("active", C["text"])],
              background=[("active", C["mantle"])])

        s.configure("Treeview", background=C["surface0"],
                    foreground=C["text"], fieldbackground=C["surface0"],
                    rowheight=26, borderwidth=0)
        s.configure("Treeview.Heading", background=C["mantle"],
                    foreground=C["overlay0"], relief="flat")
        s.map("Treeview",
              background=[("selected", C["surface2"])],
              foreground=[("selected", C["text"])])

        s.configure("TScrollbar", background=C["surface0"],
                    troughcolor=C["mantle"], arrowcolor=C["overlay0"],
                    borderwidth=0, arrowsize=11, width=10)
        s.map("TScrollbar", background=[("active", C["surface1"])])

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        # ── TOP BAR ──────────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=C["crust"], height=52)
        topbar.pack(side=tk.TOP, fill=tk.X)
        topbar.pack_propagate(False)

        # Brand
        brand = tk.Frame(topbar, bg=C["crust"])
        brand.pack(side=tk.LEFT, padx=14, fill=tk.Y)
        tk.Label(brand, text="⚡ Harry Plotter", bg=C["crust"],
                 fg=C["mauve"], font=("Sans", 12, "bold")).pack(side=tk.LEFT)
        tk.Label(brand, text=f"  {APP_VERSION}", bg=C["crust"],
                 fg=C["overlay0"], font=("Sans", 9)).pack(side=tk.LEFT)

        # Separator
        tk.Frame(topbar, bg=C["surface1"], width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=10, padx=6)

        # Action buttons
        btn_area = tk.Frame(topbar, bg=C["crust"])
        btn_area.pack(side=tk.LEFT, fill=tk.Y, pady=8)

        self._tbtn(btn_area, "  Open HDF5", self.open_file,
                   "Open an HDF5 file  (Ctrl+O)", accent=True)
        self._tbtn(btn_area, "  Add File", self.add_file,
                   "Add signals from another HDF5 file into the current session")
        self._tbtn(btn_area, "  Clear Plots", self.clear_graphs,
                   "Remove all plots  (Ctrl+L)", danger=True)
        self._tbtn(btn_area, "  GPS Map", self.plot_gps,
                   "Plot GPS track in browser")

        # Separator
        tk.Frame(topbar, bg=C["surface1"], width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=10, padx=10)

        # Checkboxes
        opts = tk.Frame(topbar, bg=C["crust"])
        opts.pack(side=tk.LEFT, fill=tk.Y)
        self._tcheck(opts, "Overlay",    self.plot_together_var,
                     "Overlay all selected signals on one plot")
        self._tcheck(opts, "Time axis",  self.use_time_as_xaxis_var,
                     "Use time/timestamp channel as X axis")
        self._tcheck(opts, "Grid",       self.grid_var,
                     "Show grid lines on plots")
        self._tcheck(opts, "Skip first", self.skip_first_sample_var,
                     "Skip the first sample (index 0)")

        # File label on the right
        self.file_label = tk.Label(topbar, text="  No file loaded",
                                   bg=C["crust"], fg=C["overlay0"],
                                   font=("Sans", 9))
        self.file_label.pack(side=tk.RIGHT, padx=16)

        # ── MAIN PANE ─────────────────────────────────────────────────────────
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # ── LEFT SIDEBAR ──────────────────────────────────────────────────────
        sidebar = tk.Frame(self.paned, bg=C["mantle"], width=290)
        sidebar.pack_propagate(False)
        self.paned.add(sidebar, weight=0)

        # Section label + counter
        sec = tk.Frame(sidebar, bg=C["mantle"])
        sec.pack(fill=tk.X, padx=12, pady=(14, 6))
        tk.Label(sec, text="SIGNALS", bg=C["mantle"], fg=C["overlay0"],
                 font=("Sans", 8, "bold")).pack(side=tk.LEFT)
        self._cnt_label = tk.Label(sec, text="", bg=C["mantle"],
                                   fg=C["overlay0"], font=("Sans", 8))
        self._cnt_label.pack(side=tk.LEFT, padx=6)

        # expand/collapse row
        exp_row = tk.Frame(sidebar, bg=C["mantle"])
        exp_row.pack(fill=tk.X, padx=12, pady=(0, 4))
        for txt, expand in [("Expand all", True), ("Collapse all", False)]:
            lbl = tk.Label(exp_row, text=txt, bg=C["mantle"], fg=C["blue"],
                           cursor="hand2", font=("Sans", 8))
            lbl.pack(side=tk.LEFT)
            lbl.bind("<Button-1>",
                     (lambda e, v=expand: self._expand_all(v)))
            if txt == "Expand all":
                tk.Label(exp_row, text="  ·  ", bg=C["mantle"],
                         fg=C["overlay0"], font=("Sans", 8)).pack(side=tk.LEFT)

        # Search box
        sb = tk.Frame(sidebar, bg=C["surface0"],
                      highlightbackground=C["surface1"], highlightthickness=1)
        sb.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Label(sb, text=" 🔍", bg=C["surface0"], fg=C["overlay0"],
                 font=("Sans", 9)).pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._do_search())
        se = tk.Entry(sb, textvariable=self.search_var,
                      bg=C["surface0"], fg=C["text"],
                      insertbackground=C["text"], relief="flat",
                      font=("Sans", 9), highlightthickness=0, bd=0)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=4)
        clr = tk.Label(sb, text="✕", bg=C["surface0"], fg=C["overlay0"],
                       cursor="hand2", font=("Sans", 9), padx=6)
        clr.pack(side=tk.RIGHT)
        clr.bind("<Button-1>", lambda _: self.search_var.set(""))
        Tooltip(clr, "Clear search")

        # Tree
        tree_wrap = tk.Frame(sidebar, bg=C["mantle"])
        tree_wrap.pack(fill=tk.BOTH, expand=True, padx=12)
        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="extended")
        vsb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL,
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>",    self._on_tree_double_click)
        self.tree.bind("<Return>",      lambda _: self.plot_selected_signals())
        self.tree.bind("<Button-3>",    self._ctx_menu_show)

        # Context menu
        self._ctx = tk.Menu(self.root, tearoff=0,
                            bg=C["surface0"], fg=C["text"],
                            activebackground=C["surface1"],
                            activeforeground=C["text"],
                            relief="flat", bd=1, font=("Sans", 9))
        self._ctx.add_command(label="▶  Plot selected",
                              command=self.plot_selected_signals)
        self._ctx.add_command(label="✕  Clear plots",
                              command=self.clear_graphs)

        # Plot button
        btn_bottom = tk.Frame(sidebar, bg=C["mantle"])
        btn_bottom.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btn_bottom, text="▶  Plot Selected",
                   style="Accent.TButton",
                   command=self.plot_selected_signals).pack(fill=tk.X, ipady=5)
        tk.Label(btn_bottom,
                 text="Ctrl+click or Shift+click to select multiple\nDouble-click · Enter · Space to plot",
                 bg=C["mantle"], fg=C["overlay0"],
                 font=("Sans", 7), justify="center").pack(pady=(4, 0))

        # ── RIGHT AREA ────────────────────────────────────────────────────────
        right = tk.Frame(self.paned, bg=C["base"])
        self.paned.add(right, weight=1)

        # Drop zone (shown when empty)
        self._drop_zone = tk.Frame(right, bg=C["base"])
        self._drop_zone.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(self._drop_zone, text="⬇", bg=C["base"],
                 fg=C["surface1"], font=("Sans", 52)).pack(expand=True)
        tk.Label(self._drop_zone,
                 text="Drop an HDF5 file here  or  click  Open HDF5",
                 bg=C["base"], fg=C["surface2"],
                 font=("Sans", 12)).pack()
        tk.Label(self._drop_zone, text=".h5  ·  .hdf5  ·  .hdf",
                 bg=C["base"], fg=C["overlay0"],
                 font=("Sans", 9)).pack(pady=(6, 0))

        # Scrollable canvas
        canvas_area = tk.Frame(right, bg=C["base"])
        canvas_area.pack(fill=tk.BOTH, expand=True)

        self.canvas_scroll = tk.Canvas(canvas_area, bg=C["base"],
                                       highlightthickness=0)
        vscr = ttk.Scrollbar(canvas_area, orient=tk.VERTICAL,
                              command=self.canvas_scroll.yview)
        self.canvas_scroll.configure(yscrollcommand=vscr.set)
        vscr.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas_scroll.pack(fill=tk.BOTH, expand=True)

        self.canvas_frame = tk.Frame(self.canvas_scroll, bg=C["base"])
        self._cwin = self.canvas_scroll.create_window(
            (0, 0), window=self.canvas_frame, anchor="nw")

        self.canvas_frame.bind("<Configure>",
                               lambda _: self._sync_scroll())
        self.canvas_scroll.bind("<Configure>",
                                lambda e: self.canvas_scroll.itemconfig(
                                    self._cwin, width=e.width))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas_scroll.bind(ev, self._mousewheel)

        # ── STATUS BAR ────────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg=C["crust"], height=26)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        self._status = tk.Label(bar, text="Ready  —  open or drop an HDF5 file",
                                bg=C["crust"], fg=C["overlay0"],
                                font=("Sans", 8), anchor="w")
        self._status.pack(side=tk.LEFT, padx=12)
        self._plot_info = tk.Label(bar, text="", bg=C["crust"],
                                   fg=C["overlay0"], font=("Sans", 8))
        self._plot_info.pack(side=tk.RIGHT, padx=12)

    # ── widget factory helpers ─────────────────────────────────────────────────

    def _tbtn(self, parent, text, cmd, tip="", accent=False, danger=False):
        st = ("Accent.TButton" if accent
              else "Danger.TButton" if danger
              else "TButton")
        b = ttk.Button(parent, text=text, command=cmd, style=st)
        b.pack(side=tk.LEFT, padx=3)
        if tip:
            Tooltip(b, tip)
        return b

    def _tcheck(self, parent, text, var, tip=""):
        cb = ttk.Checkbutton(parent, text=text, variable=var)
        cb.pack(side=tk.LEFT, padx=7)
        if tip:
            Tooltip(cb, tip)

    # ── status helpers ─────────────────────────────────────────────────────────

    def _status_set(self, msg, color=None):
        self._status.config(text=msg, fg=color or C["overlay0"])

    def _sync_scroll(self):
        self.canvas_scroll.configure(
            scrollregion=self.canvas_scroll.bbox("all"))

    def _mousewheel(self, event):
        if event.num == 4:
            self.canvas_scroll.yview_scroll(-3, "units")
        elif event.num == 5:
            self.canvas_scroll.yview_scroll(3, "units")
        else:
            self.canvas_scroll.yview_scroll(
                int(-1 * event.delta / 120), "units")

    # ── resize ────────────────────────────────────────────────────────────────

    def _on_resize(self, event):
        if event.widget != self.root:
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w == self._prev_w and h == self._prev_h:
            return
        self._prev_w, self._prev_h = w, h
        if self._resize_id:
            self.root.after_cancel(self._resize_id)
        self._resize_id = self.root.after(350, self._redraw_all)

    # ── drag-and-drop ─────────────────────────────────────────────────────────

    def _on_drop(self, event):
        paths = [p for p in self.root.tk.splitlist(event.data)
                 if p.lower().endswith((".h5", ".hdf5", ".hdf"))]
        if not paths:
            messagebox.showwarning("Wrong file type",
                                   "Please drop an HDF5 file (.h5 / .hdf5 / .hdf).")
            return
        self.load_file(paths[0], replace=True)
        for p in paths[1:]:
            self.load_file(p, replace=False)

    # ── open / load ───────────────────────────────────────────────────────────

    def open_file(self):
        p = filedialog.askopenfilename(
            title="Open HDF5 file",
            filetypes=[("HDF5 files", "*.h5 *.hdf5 *.hdf"),
                       ("All files", "*.*")])
        if p:
            self.load_file(p, replace=True)

    def add_file(self):
        p = filedialog.askopenfilename(
            title="Add signals from HDF5 file",
            filetypes=[("HDF5 files", "*.h5 *.hdf5 *.hdf"),
                       ("All files", "*.*")])
        if p:
            self.load_file(p, replace=False)

    def load_file(self, path, replace=True):
        fname = os.path.basename(path)

        # If same filename already loaded, make it unique
        base, ext = os.path.splitext(fname)
        count = 1
        while fname in self.hdf_files:
            fname = f"{base}_{count}{ext}"
            count += 1

        # Close + clear everything if replacing
        if replace:
            for f in self.hdf_files.values():
                try:
                    f.close()
                except Exception:
                    pass
            self.hdf_files.clear()
            self.signals.clear()
            self.clear_graphs()

        # Open the new file
        try:
            hf = h5py.File(path, "r")
        except Exception as exc:
            messagebox.showerror("Cannot open file", str(exc))
            return

        new_datasets = collect_datasets(hf)

        if not replace and len(self.hdf_files) == 0:
            # Adding to an empty session — treat as replace
            replace = True

        if not replace and len(self.hdf_files) >= 1:
            # Multi-file mode: prefix everything
            # Re-prefix already loaded signals with their own filename prefix
            # (only needed when going from 1 -> 2 files)
            if len(self.hdf_files) == 1:
                existing_fname = next(iter(self.hdf_files))
                reprefixed = {f"{existing_fname}/{k}": v
                              for k, v in self.signals.items()
                              if not k.startswith(existing_fname + "/")}
                already_prefixed = {k: v for k, v in self.signals.items()
                                    if k.startswith(existing_fname + "/")}
                self.signals = already_prefixed
                self.signals.update(reprefixed)
            # Add new file's signals with its prefix
            for k, v in new_datasets.items():
                self.signals[f"{fname}/{k}"] = v
        else:
            # Single-file mode: no prefix
            self.signals.update(new_datasets)

        self.hdf_files[fname] = hf
        self.hdf_file = hf
        self.file_path = path

        self._drop_zone.place_forget()
        self._update_tree()
        self._extract_gps()

        n_new = len(new_datasets)
        n_files = len(self.hdf_files)
        if n_files == 1:
            self.file_label.config(text=f"  📂 {fname}", fg=C["green"])
            self.root.title(f"{APP_TITLE} {APP_VERSION}  —  {fname}")
            self._status_set(
                f"Loaded {len(self.signals):,} signals from {fname}", C["green"])
        else:
            self.file_label.config(text=f"  📂 {n_files} files", fg=C["teal"])
            self.root.title(f"{APP_TITLE} {APP_VERSION}  —  {n_files} files")
            self._status_set(
                f"Added {n_new:,} signals from {fname}  "
                f"({len(self.signals):,} total)", C["teal"])

    def _extract_gps(self):
        self.latitude, self.longitude = [], []
        for path, ds in self.signals.items():
            lp = path.lower()
            if "latitude"  in lp or lp.endswith("lat"):
                self.latitude  = load_signal(ds).tolist()
            if "longitude" in lp or lp.endswith("lon"):
                self.longitude = load_signal(ds).tolist()

    # ── signal tree ───────────────────────────────────────────────────────────

    def _update_tree(self, paths=None):
        self.tree.delete(*self.tree.get_children())
        if paths is None:
            paths = list(self.signals.keys())
        self.filtered_signals = paths
        total  = len(self.signals)
        shown  = len(paths)
        self._cnt_label.config(
            text=f"({shown} / {total})" if shown != total else f"({total})")

        groups: dict = {}

        def ensure_group(gpath):
            if gpath in groups:
                return groups[gpath]
            parts  = gpath.split("/")
            parent = ""
            for d in range(len(parts)):
                partial = "/".join(parts[: d + 1])
                if partial not in groups:
                    iid = self.tree.insert(
                        parent, "end", iid=f"grp:{partial}",
                        text=f"  📁  {parts[d]}", open=True)
                    groups[partial] = iid
                parent = groups[partial]
            return groups[gpath]

        for path in paths:
            ds = self.signals[path]
            shape_str = (f"  {list(ds.shape)}  {ds.dtype}"
                         if ds.shape else f"  scalar  {ds.dtype}")
            if "/" in path:
                group, name = path.rsplit("/", 1)
                parent = ensure_group(group)
            else:
                parent, name = "", path
            self.tree.insert(parent, "end", iid=f"sig:{path}",
                             text=f"    {name}   {shape_str}")

    def _do_search(self):
        q = self.search_var.get().strip()
        if not q or not self.signals:
            self._update_tree()
            return
        words = re.split(r"[ &+]", q.lower())
        filtered = [p for p in self.signals
                    if all(w in p.lower() for w in words if w)]
        self._update_tree(filtered)

    def _expand_all(self, expand):
        def walk(item):
            self.tree.item(item, open=expand)
            for child in self.tree.get_children(item):
                walk(child)
        for item in self.tree.get_children():
            walk(item)

    def _sel_paths(self):
        out = []
        for iid in self.tree.selection():
            if iid.startswith("sig:"):
                out.append(iid[4:])
            elif iid.startswith("grp:"):
                g = iid[4:]
                for p in self.signals:
                    if p.startswith(g + "/") or p == g:
                        out.append(p)
        return list(dict.fromkeys(out))

    def _on_tree_double_click(self, event):
        # Don't reset multi-selection on double-click — just plot whatever is selected
        self.plot_selected_signals()

    def _ctx_menu_show(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self._ctx.post(event.x_root, event.y_root)

    # ── time vector ───────────────────────────────────────────────────────────

    def _time_vec(self, n):
        for path, ds in self.signals.items():
            lp = path.lower()
            if "time" in lp or "timestamp" in lp:
                t = load_signal(ds)
                if t.ndim == 1 and len(t) == n:
                    return t
        return np.arange(n, dtype=float)

    def _redraw_all(self):
        if not self._plotted_paths or not self.signals:
            return
        paths = [p for p in self._plotted_paths if p in self.signals]
        if not paths:
            return
        skip  = self.skip_first_sample_var.get()
        utime = self.use_time_as_xaxis_var.get()
        grid  = self.grid_var.get()
        tog   = self.plot_together_var.get()
        cw    = max(self.canvas_frame.winfo_width(),
                    self.canvas_scroll.winfo_width(), 600)
        dpi   = 96
        fig_w = cw / dpi
        # Clear visuals only, preserve _plotted_paths
        for cv in self.graphs:
            try:
                cv.get_tk_widget().master.destroy()
            except Exception:
                pass
        self.graphs.clear()
        self.toolbars.clear()
        plt.close("all")
        if tog:
            self._plot_overlay(paths, fig_w, dpi, utime, grid, skip)
        else:
            for path in paths:
                self._plot_single(path, fig_w, dpi, utime, grid, skip)
        self._sync_scroll()

    # ── plotting ──────────────────────────────────────────────────────────────

    def plot_selected_signals(self, _e=None):
        sel = self._sel_paths()
        if not sel:
            self._status_set("No signals selected — click signals in the tree", C["yellow"])
            return
        self._sel_cache = sel
        self._drop_zone.place_forget()

        # Only add signals not already plotted
        new_sel = [p for p in sel if p not in self._plotted_paths]
        if not new_sel:
            return
        self._plotted_paths.extend(new_sel)

        skip  = self.skip_first_sample_var.get()
        utime = self.use_time_as_xaxis_var.get()
        grid  = self.grid_var.get()
        tog   = self.plot_together_var.get()

        cw = max(self.canvas_frame.winfo_width(),
                 self.canvas_scroll.winfo_width(), 600)
        dpi    = 96
        fig_w  = cw / dpi

        if tog:
            self._plot_overlay(new_sel, fig_w, dpi, utime, grid, skip)
        else:
            for path in new_sel:
                self._plot_single(path, fig_w, dpi, utime, grid, skip)

        self._sync_scroll()
        n = len(self.graphs)
        self._plot_info.config(
            text=f"{n} plot{'s' if n != 1 else ''}  ·  {n} signal{'s' if n != 1 else ''}")
        self._status_set(f"Plotted {len(new_sel)} signal(s)  ({n} total)")

    def _get_y(self, path, skip):
        y = load_signal(self.signals[path])
        if skip and y.ndim >= 1 and len(y) > 1:
            y = y[1:]
        return y

    def _ax_style(self, ax, fig):
        fig.patch.set_facecolor(C["base"])
        ax.set_facecolor(C["mantle"])
        ax.tick_params(colors=C["subtext0"], labelsize=8,
                       length=3, width=0.5)
        for sp in ax.spines.values():
            sp.set_edgecolor(C["surface1"])
            sp.set_linewidth(0.8)
        ax.xaxis.label.set_color(C["subtext0"])
        ax.yaxis.label.set_color(C["subtext0"])

    def _plot_overlay(self, paths, fw, dpi, utime, grid, skip):
        fh = max(4.2, fw * 0.36)
        fig, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)
        self._ax_style(ax, fig)
        names = [p.split("/")[-1] for p in paths]
        title = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        ax.set_title(title, color=C["mauve"], fontsize=8.5,
                     pad=7, loc="left")

        for i, path in enumerate(paths):
            y = self._get_y(path, skip)
            if y.ndim != 1:
                continue
            x   = self._time_vec(len(y)) if utime else np.arange(len(y))
            col = PLOT_COLORS[i % len(PLOT_COLORS)]
            ax.plot(x, y, color=col, label=names[i],
                    linewidth=1.5, alpha=0.9)

        ax.set_xlabel("Time [s]" if utime else "Sample", fontsize=8)
        ax.legend(loc="upper right", fontsize=7.5, framealpha=0.85,
                  facecolor=C["surface0"], edgecolor=C["surface1"],
                  labelcolor=C["text"])
        if grid:
            ax.grid(True, color=C["surface1"], linestyle="--",
                    linewidth=0.5, alpha=0.6)
        fig.tight_layout(pad=1.5)
        self._embed(fig, ax)

    def _plot_single(self, path, fw, dpi, utime, grid, skip):
        y     = self._get_y(path, skip)
        label = path.split("/")[-1]

        fh  = max(2.5, fw * 0.21)
        fig, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)
        self._ax_style(ax, fig)
        ax.set_title(path, color=C["overlay1"], fontsize=7.5,
                     pad=5, loc="left")

        if y.ndim == 1:
            x = self._time_vec(len(y)) if utime else np.arange(len(y))
            if y.dtype.kind in ("U", "S", "O"):
                uniq = list(dict.fromkeys(y.tolist()))
                mp   = {v: i for i, v in enumerate(uniq)}
                yn   = np.array([mp[v] for v in y])
                ax.step(x, yn, color=PLOT_COLORS[0],
                        linewidth=1.5, where="post")
                ax.set_yticks(range(len(uniq)))
                ax.set_yticklabels(uniq, fontsize=7.5, color=C["subtext0"])
            else:
                ax.plot(x, y, color=PLOT_COLORS[0], linewidth=1.5)
                ax.fill_between(x, y, alpha=0.07, color=PLOT_COLORS[0])
        elif y.ndim == 2:
            im = ax.imshow(y.T, aspect="auto", origin="lower",
                           cmap="magma", interpolation="nearest",
                           extent=[0, y.shape[0], 0, y.shape[1]])
            fig.colorbar(im, ax=ax, fraction=0.018, pad=0.02)
        else:
            ax.text(0.5, 0.5, f"Cannot display {y.ndim}D data  {y.shape}",
                    ha="center", va="center", color=C["red"],
                    fontsize=9, transform=ax.transAxes)

        ax.set_xlabel("Time [s]" if utime else "Sample", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        if grid:
            ax.grid(True, color=C["surface1"], linestyle="--",
                    linewidth=0.5, alpha=0.6)
        fig.tight_layout(pad=1.2)
        self._embed(fig, ax)

    def _embed(self, fig, ax):
        # Card
        card = tk.Frame(self.canvas_frame, bg=C["mantle"],
                        highlightbackground=C["surface1"], highlightthickness=1)
        card.pack(fill=tk.X, padx=8, pady=4)

        mpl_canvas = FigureCanvasTkAgg(fig, master=card)
        mpl_canvas.draw()
        mpl_canvas.get_tk_widget().pack(fill=tk.X, expand=True)

        tb_frame = tk.Frame(card, bg=C["surface0"])
        tb_frame.pack(fill=tk.X)
        toolbar = NavigationToolbar2Tk(mpl_canvas, tb_frame)
        toolbar.config(background=C["surface0"])
        for child in toolbar.winfo_children():
            try:
                child.config(background=C["surface0"],
                             foreground=C["subtext0"],
                             highlightbackground=C["surface0"])
            except Exception:
                pass
        toolbar.update()

        if MPLCURSORS_AVAILABLE:
            mplcursors.cursor(ax, hover=True)

        self.graphs.append(mpl_canvas)
        self.toolbars.append(toolbar)
        plt.close(fig)

    # ── GPS ───────────────────────────────────────────────────────────────────

    def plot_gps(self):
        if not FOLIUM_AVAILABLE:
            messagebox.showerror("Missing dependency",
                                 "folium is not installed.\n"
                                 "Run:  pip install folium")
            return
        if not self.latitude or not self.longitude:
            messagebox.showinfo("GPS Map",
                                "No GPS coordinates found in the loaded file.")
            return
        coords = list(zip(self.latitude, self.longitude))
        m = folium.Map(location=[np.mean(self.latitude),
                                  np.mean(self.longitude)],
                       zoom_start=15, tiles="CartoDB dark_matter")
        folium.PolyLine(coords, color=C["blue"],
                        weight=3, opacity=0.9).add_to(m)
        folium.Marker(coords[0],  icon=folium.DivIcon(
            html='<div style="font:bold 11px sans-serif;color:#a6e3a1">'
                 '▶ Start</div>')).add_to(m)
        folium.Marker(coords[-1], icon=folium.DivIcon(
            html='<div style="font:bold 11px sans-serif;color:#f38ba8">'
                 '■ Stop</div>')).add_to(m)
        m.save(self.temp_map)
        webbrowser.open(f"file://{self.temp_map}")
        self._status_set("GPS map opened in browser", C["green"])

    # ── clear / cleanup ────────────────────────────────────────────────────────

    def clear_graphs(self):
        for cv in self.graphs:
            try:
                cv.get_tk_widget().master.destroy()
            except Exception:
                pass
        self.graphs.clear()
        self.toolbars.clear()
        self._plotted_paths.clear()
        plt.close("all")
        self._plot_info.config(text="")
        if not self.file_path:
            self._drop_zone.place(relx=0, rely=0, relwidth=1, relheight=1)

    def cleanup(self):
        for f in self.hdf_files.values():
            try:
                f.close()
            except Exception:
                pass
        if os.path.exists(self.temp_map):
            try:
                os.remove(self.temp_map)
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────

def main():
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    icon = os.path.join(os.path.dirname(__file__),
                        "icons", "harryplotter_icon.ico")
    if os.path.exists(icon):
        try:
            root.iconphoto(True, tk.PhotoImage(file=icon))
        except Exception:
            pass
    HarryPlotterApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
