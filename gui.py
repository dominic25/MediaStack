"""
Tkinter GUI for Media Stack Manager.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import queue, threading, ctypes
from pathlib import Path
from datetime import datetime

from constants import (
    VERSION, APPS, THEMES,
    C_ACCENT, C_LOG_BG, C_LOG_FG, C_LOG_OK, C_LOG_WRN, C_LOG_ERR,
    F_MAIN, F_BOLD, F_TITLE, F_MONO,
)
from config import Config
from ops import Ops


class App:
    def __init__(self):
        self.cfg  = Config()
        self.q    = queue.Queue()
        self.ops  = Ops(self.cfg, self._enqueue_log)
        self._tw  = []
        self._status_labels = {}
        self._backup_sets   = []
        self._busy = False
        self._action_buttons = []

        self._theme_name = self.cfg.get("theme", "light")

        self.root = tk.Tk()
        self.root.title(f"Media Stack Manager v{VERSION}")
        self.root.geometry("1050x740")
        self.root.minsize(800, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_log()
        self._build_statusbar()
        self._apply_theme()
        self._check_queue()

        if self.cfg.load_error:
            self.log(f"WARNING: Config file could not be loaded: {self.cfg.load_error}", "warn")
            self.log("Using default settings.", "warn")
        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.log("WARNING: Not running as Administrator. Some operations may fail.", "warn")

    # --- theme ---

    def _t(self):
        """Return current theme dict."""
        return THEMES[self._theme_name]

    def _setup_styles(self):
        t = self._t()
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".",             font=F_MAIN,  background=t["bg"],   foreground=t["fg"])
        s.configure("TFrame",        background=t["bg"])
        s.configure("Card.TFrame",   background=t["card"])
        s.configure("TLabel",        background=t["bg"],   foreground=t["fg"])
        s.configure("Card.TLabel",   background=t["card"], foreground=t["fg"])
        s.configure("TNotebook",     background=t["bg"],   borderwidth=0)
        s.configure("TNotebook.Tab", font=F_BOLD, padding=[14, 6])
        s.map("TNotebook.Tab",
              background=[("selected", C_ACCENT)],
              foreground=[("selected", "white")])
        s.configure("Accent.TButton", font=F_BOLD,  foreground="white",
                    background=C_ACCENT, borderwidth=0, padding=[10, 5])
        s.map("Accent.TButton", background=[("active", "#1976d2")])
        s.configure("Small.TButton", font=F_MAIN,  padding=[6, 3],
                    background=t["btn_bg"], foreground=t["btn_fg"])
        s.configure("TEntry",        fieldbackground=t["entry_bg"], foreground=t["fg"], padding=4)
        s.configure("TScrollbar",    background=t["bg"])

    def _apply_theme(self):
        t = self._t()
        self._setup_styles()
        self.root.configure(bg=t["bg"])
        for fn in self._tw:
            try: fn(t)
            except Exception: pass
        self.backup_list.configure(bg=t["listbox_bg"], fg=t["listbox_fg"],
                                   selectbackground=C_ACCENT, selectforeground="white")
        self._toggle_btn.configure(text=t["toggle_lbl"])

    def _toggle_theme(self):
        self._theme_name = "dark" if self._theme_name == "light" else "light"
        self.cfg["theme"] = self._theme_name
        self.cfg.save()
        self._apply_theme()

    def _tw_add(self, widget, **props):
        """Register a tk widget for theme updates. props maps configure-key -> theme-key."""
        self._tw.append(lambda t, w=widget, p=props: w.configure(**{k: t[v] for k, v in p.items()}))

    # --- mouse-wheel scrolling ---

    def _bind_scroll(self, region_widget, canvas):
        """Enable mouse-wheel on canvas whenever cursor is inside region_widget."""
        fn = lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        region_widget.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", fn))
        region_widget.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))
        canvas.bind(       "<Enter>", lambda e: self.root.bind_all("<MouseWheel>", fn))
        canvas.bind(       "<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

    # --- header ---

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=C_ACCENT, height=52)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Media Stack Manager", font=F_TITLE,
                 bg=C_ACCENT, fg="white").pack(side="left", padx=8, pady=12)
        tk.Label(hdr, text=f"v{VERSION}", font=F_MAIN,
                 bg=C_ACCENT, fg="#90caf9").pack(side="left")
        self._toggle_btn = tk.Button(
            hdr, text=self._t()["toggle_lbl"],
            font=F_MAIN, bg="#0d47a1", fg="white",
            activebackground="#1565c0", activeforeground="white",
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._toggle_theme)
        self._toggle_btn.pack(side="right", padx=12, pady=10)

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self._build_install_tab()
        self._build_backup_tab()
        self._build_settings_tab()

    # --- Install tab ---

    def _build_install_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Install  ")

        top = ttk.Frame(outer)
        top.pack(fill="x", padx=12, pady=8)
        ttk.Label(top, text="Base folder:").pack(side="left")
        self.base_var = tk.StringVar(value=self.cfg["base_root"])
        ttk.Entry(top, textvariable=self.base_var, width=34).pack(side="left", padx=6)
        ttk.Button(top, text="Browse", style="Small.TButton",
                   command=self._browse_base).pack(side="left")
        ttk.Button(top, text="Refresh Status", style="Small.TButton",
                   command=self._refresh_status).pack(side="left", padx=(8, 0))
        btn = ttk.Button(top, text="Install All", style="Accent.TButton",
                   command=self._install_all)
        btn.pack(side="right")
        self._action_buttons.append(btn)
        btn = ttk.Button(top, text="Auto-Configure", style="Accent.TButton",
                   command=self._auto_configure)
        btn.pack(side="right", padx=(0, 6))
        self._action_buttons.append(btn)

        cf = ttk.Frame(outer)
        cf.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(cf, highlightthickness=0)
        self._tw_add(canvas, bg="bg")
        vsb = ttk.Scrollbar(cf, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.install_inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=self.install_inner, anchor="nw")
        self.install_inner.bind(
            "<Configure>",
            lambda e: (canvas.configure(scrollregion=canvas.bbox("all")),
                       canvas.itemconfig(win, width=canvas.winfo_width())))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=canvas.winfo_width()))
        self._bind_scroll(cf, canvas)
        self.status_vars = {}
        for app in APPS:
            self._add_app_row(self.install_inner, app)

    def _add_app_row(self, parent, app):
        name = app["name"]
        t    = self._t()
        row  = tk.Frame(parent, pady=2)
        self._tw_add(row, bg="card")
        row.pack(fill="x", padx=2, pady=3)
        row.columnconfigure(2, weight=1)
        clr = {"Jellyfin":"#00a4dc","Sonarr":"#35c5f4","Radarr":"#ffc230",
               "Prowlarr":"#ff6a00","Bazarr":"#9b59b6","qBittorrent":"#2ecc71",
               "Byparr":"#e74c3c","Seer":"#1abc9c"}.get(name, C_ACCENT)
        tk.Frame(row, bg=clr, width=6).grid(row=0, column=0, rowspan=2, sticky="ns")
        lbl_name = tk.Label(row, text=name, font=F_BOLD, anchor="w", width=14)
        self._tw_add(lbl_name, bg="card", fg="fg")
        lbl_name.grid(row=0, column=1, sticky="w", padx=(8, 4), pady=(6, 0))
        lbl_desc = tk.Label(row, text=app["desc"], font=F_MAIN, anchor="w")
        self._tw_add(lbl_desc, bg="card", fg="fg_dim")
        lbl_desc.grid(row=1, column=1, sticky="w", padx=(8, 4), pady=(0, 6))
        method_colors = {"winget": "#1565c0", "docker": "#0288d1", "browser": "#6a1b9a"}
        method = app.get("install", "")
        mc     = method_colors.get(method, "#555")
        badge  = tk.Label(row, text=method.upper(), bg=mc, fg="white",
                          font=("Segoe UI", 8, "bold"), padx=5, pady=1)
        badge.grid(row=0, column=2, sticky="w", padx=4, pady=(6, 0))
        sv = tk.StringVar(value="")
        self.status_vars[name] = sv
        status_lbl = tk.Label(row, textvariable=sv, font=F_MAIN, anchor="w")
        self._tw_add(status_lbl, bg="card")
        status_lbl.grid(row=1, column=2, sticky="w", padx=4, pady=(0, 6))
        self._status_labels[name] = status_lbl
        ttk.Button(row, text="Install", style="Small.TButton",
                   command=lambda a=app: self._install_one(a)
                   ).grid(row=0, column=3, rowspan=2, padx=8, pady=6)

    def _refresh_status(self):
        def run():
            for app in APPS:
                label, color_key = self.ops.check_app_status(app)
                name = app["name"]
                self.q.put(lambda n=name, lb=label, ck=color_key:
                           self._set_status(n, lb, ck))
        self._run_bg(run)

    def _set_status(self, name, label, color_key):
        t = self._t()
        if name in self.status_vars:
            self.status_vars[name].set(label)
        if name in self._status_labels:
            color = t.get(color_key, t["fg_dim"])
            self._status_labels[name].configure(fg=color)

    def _browse_base(self):
        d = filedialog.askdirectory(initialdir=self.base_var.get())
        if d:
            self.base_var.set(d)
            self.cfg["base_root"] = d
            self.cfg.save()

    def _install_one(self, app):
        self._run_bg(lambda: self.ops.install_app(app))

    def _install_all(self):
        self.cfg["base_root"] = self.base_var.get()
        self.cfg.save()
        self._run_bg(lambda: [self.ops.install_app(a) for a in APPS])

    def _auto_configure(self):
        if not messagebox.askyesno(
                "Auto-Configure",
                "This will configure all apps automatically:\n\n"
                "  - qBittorrent: WebUI port, download path\n"
                "  - Sonarr/Radarr: root folder, qBittorrent client\n"
                "  - Prowlarr: link Sonarr + Radarr\n"
                "  - Bazarr: write Sonarr + Radarr connections\n"
                "  - Jellyfin: add Movies + TV libraries (needs API key in Settings)\n\n"
                "All apps must already be installed and running.\n"
                "Existing settings will NOT be overwritten. Continue?"):
            return
        self._run_bg(self.ops.configure_all)

    # --- Backup / Restore tab ---

    def _build_backup_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Backup & Restore  ")
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        lf = tk.LabelFrame(outer, text=" Backup ", font=F_BOLD, padx=10, pady=10)
        self._tw_add(lf, bg="lf_bg", fg="lf_fg")
        lf.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        lf.columnconfigure(0, weight=1)

        desc = tk.Label(lf, text="Creates a timestamped snapshot of every app\n"
                            "using each app's built-in backup where available.",
                        font=F_MAIN, justify="left", anchor="w")
        self._tw_add(desc, bg="lf_bg", fg="fg")
        desc.pack(anchor="w")

        btn = ttk.Button(lf, text="Back Up All Now", style="Accent.TButton",
                   command=self._do_backup)
        btn.pack(anchor="w", pady=(12, 4))
        self._action_buttons.append(btn)

        sep_lbl = tk.Label(lf, text="Individual apps:", font=F_MAIN, anchor="w")
        self._tw_add(sep_lbl, bg="lf_bg", fg="fg_dim")
        sep_lbl.pack(anchor="w", pady=(10, 2))

        for app in APPS:
            if app.get("backup") is None: continue
            ttk.Button(lf, text=f"  Back up {app['name']}",
                       style="Small.TButton",
                       command=lambda a=app: self._backup_one(a)).pack(anchor="w", pady=1)

        rf = tk.LabelFrame(outer, text=" Restore ", font=F_BOLD, padx=10, pady=10)
        self._tw_add(rf, bg="lf_bg", fg="lf_fg")
        rf.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(1, weight=1)

        hdr_lbl = tk.Label(rf, text="Select a backup set:", font=F_MAIN, anchor="w")
        self._tw_add(hdr_lbl, bg="lf_bg", fg="fg")
        hdr_lbl.grid(row=0, column=0, sticky="w")

        self.backup_list = tk.Listbox(rf, font=F_MONO, height=12,
                                      selectmode="single",
                                      bg="white", fg="#111",
                                      selectbackground=C_ACCENT, selectforeground="white")
        self.backup_list.grid(row=1, column=0, sticky="nsew", pady=6)
        sb = ttk.Scrollbar(rf, command=self.backup_list.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=6)
        self.backup_list.configure(yscrollcommand=sb.set)
        self.backup_list.bind("<MouseWheel>",
            lambda e: self.backup_list.yview_scroll(int(-1*(e.delta/120)), "units"))

        btn_row = ttk.Frame(rf)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(btn_row, text="Refresh", style="Small.TButton",
                   command=self._refresh_backup_list).pack(side="left", padx=(0, 4))
        btn = ttk.Button(btn_row, text="Restore Selected", style="Accent.TButton",
                   command=self._do_restore)
        btn.pack(side="left", padx=(0, 4))
        self._action_buttons.append(btn)
        btn = ttk.Button(btn_row, text="Delete Selected", style="Small.TButton",
                   command=self._delete_backup)
        btn.pack(side="left")
        self._action_buttons.append(btn)
        self._refresh_backup_list()

    def _refresh_backup_list(self):
        self.backup_list.delete(0, "end")
        self._backup_sets = self.ops.list_backups()
        for s in self._backup_sets:
            label = f"{s['timestamp']}  [{s['count']} archives | {s['machine']}]"
            self.backup_list.insert("end", label)

    def _do_backup(self):
        def after(results):
            self.q.put(self._refresh_backup_list)
        self._run_bg(lambda: self.ops.backup_all(callback=after))

    def _backup_one(self, app):
        ts     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bk_set = Path(self.cfg["backup_root"]) / f"{ts}_{app['name']}"
        bk_set.mkdir(parents=True, exist_ok=True)
        def run():
            method = app.get("backup")
            cfg_dir = self.ops.resolve_path(app.get("config_paths", []))
            if method == "arr_api" and cfg_dir:
                self.ops._arr_api_backup(app, cfg_dir, bk_set)
            elif method == "bazarr_api" and cfg_dir:
                self.ops._bazarr_file_backup(app, cfg_dir, bk_set)
            elif method == "jellyfin_api" and cfg_dir:
                self.ops._jellyfin_api_backup(app, cfg_dir, bk_set)
            elif method == "file_copy":
                src = Path(self.cfg["base_root"]) / app["volume_subpath"] \
                      if app.get("container") else cfg_dir
                if src and src.exists():
                    self.ops.stop_app(app)
                    self.ops._file_copy_backup(app, src, bk_set)
                    self.ops.start_app(app)
            self.q.put(self._refresh_backup_list)
        self._run_bg(run)

    def _do_restore(self):
        sel = self.backup_list.curselection()
        if not sel or sel[0] >= len(self._backup_sets):
            messagebox.showwarning("Restore", "Select a backup set from the list first.")
            return
        bk = self._backup_sets[sel[0]]
        if not messagebox.askyesno("Confirm Restore",
                f"Restore from:\n{bk['timestamp']}\n\n"
                "Existing configs will be renamed to .bak_TIMESTAMP. Continue?"):
            return
        self._run_bg(lambda: self.ops.restore_backup(bk["path"]))

    def _delete_backup(self):
        import shutil
        sel = self.backup_list.curselection()
        if not sel or sel[0] >= len(self._backup_sets):
            messagebox.showwarning("Delete", "Select a backup set to delete.")
            return
        bk = self._backup_sets[sel[0]]
        if not messagebox.askyesno("Confirm Delete",
                f"Permanently delete backup:\n{bk['timestamp']}\n\n"
                "This cannot be undone."):
            return
        try:
            shutil.rmtree(bk["path"])
            self.log(f"Deleted backup: {bk['timestamp']}", "warn")
        except Exception as e:
            self.log(f"Delete failed: {e}", "err")
        self._refresh_backup_list()

    # --- Settings tab ---

    def _build_settings_tab(self):
        outer  = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Settings  ")
        canvas = tk.Canvas(outer, highlightthickness=0)
        self._tw_add(canvas, bg="bg")
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        win   = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=canvas.winfo_width()))
        self._bind_scroll(outer, canvas)
        self._setting_vars = {}

        row_idx = [0]

        def section(text):
            lbl = ttk.Label(inner, text=text, font=F_BOLD)
            lbl.grid(row=row_idx[0], column=0, columnspan=3, sticky="w", padx=14, pady=(14, 2))
            self._tw.append(lambda t, w=lbl: w.configure(foreground=t["section_fg"]))
            row_idx[0] += 1

        def field(label, key, is_dir=False):
            r = row_idx[0]
            ttk.Label(inner, text=label).grid(row=r, column=0, sticky="w", padx=(14, 4), pady=3)
            var = tk.StringVar(value=self.cfg[key])
            self._setting_vars[key] = var
            ttk.Entry(inner, textvariable=var, width=44).grid(row=r, column=1, sticky="ew", padx=4)
            if is_dir:
                ttk.Button(inner, text="...", width=3, style="Small.TButton",
                           command=lambda v=var: v.set(filedialog.askdirectory() or v.get())
                           ).grid(row=r, column=2, padx=(0, 14))
            row_idx[0] += 1

        section("Folders")
        field("Base folder",      "base_root",      is_dir=True)
        field("Media folder",     "media_root",     is_dir=True)
        field("Downloads folder", "downloads_root", is_dir=True)
        field("Backup folder",    "backup_root",    is_dir=True)

        section("Ports")
        field("Jellyfin port",    "jellyfin_port")
        field("Sonarr port",      "sonarr_port")
        field("Radarr port",      "radarr_port")
        field("Bazarr port",      "bazarr_port")
        field("Prowlarr port",    "prowlarr_port")
        field("qBittorrent port", "qb_port")
        field("Byparr port",      "byparr_port")
        field("Seer port",        "seer_port")

        section("Docker Images")
        field("Byparr image", "byparr_image")
        field("Seer image",   "seer_image")

        section("API Keys")
        field("Jellyfin API key", "jellyfin_api_key")
        hint = ttk.Label(inner, text="Create in Jellyfin Dashboard -> Advanced -> API Keys")
        self._tw.append(lambda t, w=hint: w.configure(foreground=t["fg_dim"]))
        hint.grid(row=row_idx[0], column=1, sticky="w", pady=(0, 6))
        row_idx[0] += 1

        inner.columnconfigure(1, weight=1)
        ttk.Button(inner, text="Save Settings", style="Accent.TButton",
                   command=self._save_settings).grid(
            row=row_idx[0], column=0, columnspan=3, pady=14, padx=14, sticky="w")

    _PORT_KEYS = {"jellyfin_port", "sonarr_port", "radarr_port", "bazarr_port",
                   "prowlarr_port", "qb_port", "byparr_port", "seer_port"}

    def _save_settings(self):
        for key, var in self._setting_vars.items():
            val = var.get()
            if key in self._PORT_KEYS:
                if not val.isdigit() or not (1 <= int(val) <= 65535):
                    messagebox.showwarning("Invalid port",
                        f"{key} must be a number between 1 and 65535.")
                    return
            self.cfg[key] = val
        self.cfg.save()
        self.base_var.set(self.cfg["base_root"])
        self.log("Settings saved.", "ok")

    # --- Log ---

    def _build_log(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=(4, 0))
        hdr = tk.Frame(frame, bg=C_LOG_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text=" Output Log", bg=C_LOG_BG, fg="#888",
                 font=F_MONO).pack(side="left", padx=6, pady=2)
        tk.Button(hdr, text="Clear", bg=C_LOG_BG, fg="#888", font=F_MONO,
                  bd=0, cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=6)
        self.log_txt = scrolledtext.ScrolledText(
            frame, height=10, bg=C_LOG_BG, fg=C_LOG_FG, font=F_MONO,
            insertbackground=C_LOG_FG, wrap="word", state="disabled",
            relief="flat", borderwidth=0)
        self.log_txt.pack(fill="x")
        self.log_txt.tag_configure("ok",   foreground=C_LOG_OK)
        self.log_txt.tag_configure("warn", foreground=C_LOG_WRN)
        self.log_txt.tag_configure("err",  foreground=C_LOG_ERR)
        self.log_txt.tag_configure("bold", foreground="#ffffff", font=("Consolas", 9, "bold"))
        self.log_txt.tag_configure("info", foreground=C_LOG_FG)

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = tk.Frame(self.root, bg=C_ACCENT, height=22)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status_var, bg=C_ACCENT, fg="white",
                 font=F_MONO, anchor="w").pack(side="left", padx=8)

    # --- Queue / threading ---

    def log(self, msg, tag="info"):
        self._enqueue_log(msg, tag)

    def _enqueue_log(self, msg, tag="info"):
        self.q.put((msg, tag))

    def _check_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if callable(item):
                    item()
                else:
                    msg, tag = item
                    self.log_txt.configure(state="normal")
                    self.log_txt.insert("end", msg + "\n", tag)
                    self.log_txt.see("end")
                    self.log_txt.configure(state="disabled")
                    self.status_var.set(msg[:90] if msg.strip() else "Ready")
        except queue.Empty:
            pass
        self.root.after(50, self._check_queue)

    def _clear_log(self):
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0", "end")
        self.log_txt.configure(state="disabled")

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            try: btn.configure(state=state)
            except Exception: pass
        if busy:
            self.status_var.set("Working...")
        else:
            self.status_var.set("Ready")

    def _run_bg(self, fn):
        def wrapper():
            self.q.put(lambda: self._set_busy(True))
            try:
                fn()
            except Exception as e:
                self.log(f"Error: {e}", "err")
            finally:
                self.q.put(lambda: self._set_busy(False))
        threading.Thread(target=wrapper, daemon=True).start()

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno("Quit",
                    "An operation is still running. Quit anyway?"):
                return
        self.root.destroy()

    def run(self):
        self.root.mainloop()
