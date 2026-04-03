"""
Tkinter GUI for Media Stack Manager.
"""
import json
import os
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import queue, threading, ctypes
from pathlib import Path
from datetime import datetime, time as dt_time

from constants import (
    VERSION, APPS, THEMES, HELP_FAQ, CONFIG_PORT_KEYS, DEFAULTS,
    C_ACCENT, C_LOG_BG, C_LOG_FG, C_LOG_OK, C_LOG_WRN, C_LOG_ERR,
    F_MAIN, F_BOLD, F_TITLE, F_MONO,
)
from config import Config
from ops import Ops
from deps import check_environment, app_memory_mb


class _Tooltip:
    """Simple hover tooltip; colors follow the app theme when `app` is set."""
    def __init__(self, widget, text, app=None):
        self.widget = widget
        self.text = text
        self.app = app
        self._tip = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)

    def _theme_colors(self):
        if self.app:
            t = self.app._t()
            return (
                t.get("tooltip_bg", "#fffde7"),
                t.get("tooltip_fg", "#111111"),
                t.get("tooltip_border", "#c5c5c5"),
            )
        return "#fffde7", "#111111", "#c5c5c5"

    def _enter(self, _=None):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except Exception:
            return
        bg, fg, bd = self._theme_colors()
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg=bd)
        lbl = tk.Label(
            tw, text=self.text, justify="left",
            background=bg, foreground=fg,
            highlightbackground=bd, highlightthickness=1,
            font=("Segoe UI", 9), wraplength=360, padx=8, pady=4)
        lbl.pack()

    def _leave(self, _=None):
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


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
        self._backup_narrow = False
        self._last_root_w = 0
        self._onboarding_win = None
        self._onboarding_txt = None
        self._json_editor_win = None
        self._json_editor_txt = None

        self._theme_name = self.cfg.get("theme", "light")

        self.root = tk.Tk()
        self.root.title(f"Media Stack Manager v{VERSION}")
        self.root.geometry("1050x740")
        self.root.minsize(640, 520)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_root_configure)

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_task_progress()
        self._build_log()
        self._build_statusbar()
        self._apply_theme()
        self._check_queue()

        if self.cfg.load_error:
            self.log(f"WARNING: Config file could not be loaded: {self.cfg.load_error}", "warn")
            self.log("Using default settings.", "warn")
        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.log("WARNING: Not running as Administrator. Some operations may fail.", "warn")

        self.root.after(400, self._refresh_status)
        self.root.after(250, self._update_dashboard_env_ui)
        self._schedule_next_poll()
        if not self.cfg.get("onboarding_complete"):
            self.root.after(700, self._show_onboarding)

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
        if self._onboarding_win and self._onboarding_txt:
            try:
                self._onboarding_win.configure(bg=t["bg"])
                self._onboarding_txt.configure(
                    bg=t["entry_bg"], fg=t["fg"], insertbackground=t["fg"],
                    selectbackground=t["card"], selectforeground=t["fg"])
            except Exception:
                self._onboarding_win = None
                self._onboarding_txt = None
        if self._json_editor_win and self._json_editor_txt:
            try:
                self._json_editor_win.configure(bg=t["bg"])
                self._json_editor_txt.configure(
                    bg=t["entry_bg"], fg=t["fg"], insertbackground=t["fg"])
            except Exception:
                self._json_editor_win = None
                self._json_editor_txt = None

    def _toggle_theme(self):
        self._theme_name = "dark" if self._theme_name == "light" else "light"
        self.cfg["theme"] = self._theme_name
        self.cfg.save()
        self._apply_theme()

    def _tw_add(self, widget, **props):
        """Register a tk widget for theme updates. props maps configure-key -> theme-key."""
        self._tw.append(lambda t, w=widget, p=props: w.configure(**{k: t[v] for k, v in p.items()}))

    def _tw_label_frame(self, lf):
        """LabelFrame: theme bg/fg and hide default light border in dark mode."""
        self._tw_add(lf, bg="lf_bg", fg="lf_fg")
        self._tw.append(
            lambda t, w=lf: w.configure(
                highlightbackground=t["lf_bg"], highlightcolor=t["lf_bg"]))

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
        self._build_dashboard_tab()
        self._build_install_tab()
        self._build_backup_tab()
        self._build_settings_tab()
        self._build_help_tab()

    def _on_root_configure(self, event):
        if event.widget != self.root:
            return
        w = event.width
        if abs(w - self._last_root_w) < 8:
            return
        self._last_root_w = w
        narrow = w < 920
        if narrow != self._backup_narrow:
            self._backup_narrow = narrow
            self._layout_backup_columns()

    def _layout_backup_columns(self):
        if not getattr(self, "_backup_lf", None):
            return
        outer = self._backup_outer
        if self._backup_narrow:
            outer.columnconfigure(0, weight=1)
            outer.columnconfigure(1, weight=0)
            self._backup_lf.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
            self._backup_rf.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 12))
        else:
            outer.columnconfigure(0, weight=1)
            outer.columnconfigure(1, weight=1)
            self._backup_lf.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
            self._backup_rf.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)

    # --- Task progress (install / uninstall / auto-configure) ---

    def _build_task_progress(self):
        self._task_pf = ttk.Frame(self.root)
        self._task_pf.pack(fill="x", padx=10, pady=(0, 4))
        self._progress_msg = tk.StringVar(value="")
        ttk.Label(self._task_pf, textvariable=self._progress_msg, font=F_MAIN).pack(
            side="left", anchor="w", padx=(0, 8))
        self._progress_bar = ttk.Progressbar(
            self._task_pf, mode="determinate", length=280, maximum=100, value=0)
        self._progress_bar.pack(side="left", fill="x", expand=True)

    def _get_poll_interval_ms(self):
        try:
            s = int(self.cfg.get("poll_interval_seconds") or 45)
            return max(15, min(3600, s)) * 1000
        except Exception:
            return 45000

    def _in_quiet_hours(self):
        if not self.cfg.get("quiet_hours_enabled"):
            return False
        try:
            a = str(self.cfg.get("quiet_hours_start", "22:00")).strip().split(":")
            b = str(self.cfg.get("quiet_hours_end", "07:00")).strip().split(":")
            sh, sm = int(a[0]), int(a[1])
            eh, em = int(b[0]), int(b[1])
            t_start = dt_time(sh, sm)
            t_end = dt_time(eh, em)
        except Exception:
            return False
        now = datetime.now().time()
        if t_start <= t_end:
            return t_start <= now <= t_end
        return now >= t_start or now <= t_end

    def _schedule_next_poll(self):
        self.root.after(self._get_poll_interval_ms(), self._schedule_status_poll)

    def _enqueue_task_progress(self, cur, total, msg):
        self.q.put(lambda: self._apply_task_progress(cur, total, msg))

    def _apply_task_progress(self, cur, total, msg):
        self._progress_msg.set(msg)
        try:
            self._progress_bar.stop()
        except Exception:
            pass
        self._progress_bar.configure(mode="determinate", maximum=max(1, total), value=cur)

    def _clear_task_progress_ui(self):
        self._progress_msg.set("")
        try:
            self._progress_bar.stop()
        except Exception:
            pass
        self._progress_bar.configure(mode="determinate", maximum=100, value=0)

    def _enqueue_clear_task_progress(self):
        self.q.put(self._clear_task_progress_ui)

    # --- Dashboard ---

    def _build_dashboard_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Dashboard  ")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        env_fr = tk.LabelFrame(
            outer, text=" System & dependencies ", font=F_BOLD, padx=10, pady=8,
            highlightthickness=0)
        self._tw_label_frame(env_fr)
        env_fr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self._dash_env_inner = tk.Frame(env_fr)
        self._tw_add(self._dash_env_inner, bg="lf_bg")
        self._dash_env_inner.pack(fill="x")
        self._dash_env_labels = {}
        for key, title in [
            ("winget", "winget (installs)"),
            ("docker_cli", "Docker CLI"),
            ("docker_daemon", "Docker running"),
            ("admin", "Administrator"),
            ("disk_free_gb", "Free disk (C:)"),
        ]:
            row = tk.Frame(self._dash_env_inner)
            self._tw_add(row, bg="lf_bg")
            row.pack(fill="x", pady=1)
            lbl_t = tk.Label(row, text=title + ":", font=F_MAIN, width=22, anchor="w")
            self._tw_add(lbl_t, bg="lf_bg", fg="fg_dim")
            lbl_t.pack(side="left")
            sv = tk.StringVar(value="—")
            self._dash_env_labels[key] = sv
            lb = tk.Label(row, textvariable=sv, font=F_MONO, anchor="w")
            self._tw_add(lb, bg="lf_bg", fg="fg")
            lb.pack(side="left", fill="x", expand=True)

        ck_fr = tk.LabelFrame(
            outer, text=" First-time checklist ", font=F_BOLD, padx=10, pady=8,
            highlightthickness=0)
        self._tw_label_frame(ck_fr)
        ck_fr.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        self._checklist_vars = {}
        ck_items = [
            ("checklist_folders_saved", "Saved valid folder paths in Settings", 3),
            ("checklist_deps_reviewed", "Reviewed system dependencies (above)", None),
            ("checklist_apps_installed", "Installed apps from the Install tab", 1),
            ("checklist_auto_configure_done", "Ran Auto-Configure successfully", 1),
            ("checklist_jellyfin_api", "Set Jellyfin API key (for library setup)", 3),
        ]
        ck_inner = tk.Frame(ck_fr)
        self._tw_add(ck_inner, bg="lf_bg")
        ck_inner.pack(fill="x")
        for key, ctext, tab_idx in ck_items:
            var = tk.BooleanVar(value=bool(self.cfg.get(key)))
            self._checklist_vars[key] = var

            def _mk_toggle(k, v=var):
                def _t():
                    self.cfg[k] = v.get()
                    self.cfg.save()
                return _t

            row_f = tk.Frame(ck_inner)
            self._tw_add(row_f, bg="lf_bg")
            row_f.pack(fill="x", pady=1)

            cb = ttk.Checkbutton(
                row_f, text=ctext, variable=var, command=_mk_toggle(key))
            cb.pack(side="left", anchor="w")
            
            if tab_idx is not None:
                lbl_go = tk.Label(row_f, text="[Go \u2192]", font=F_MAIN, cursor="hand2", fg=C_ACCENT)
                self._tw_add(lbl_go, bg="lf_bg")
                lbl_go.bind("<Button-1>", lambda e, idx=tab_idx: self.nb.select(idx))
                lbl_go.pack(side="left", padx=8)
        _Tooltip(
            ck_fr,
            "Check items as you complete them. Stored in your config file.",
            self)

        self._dash_alert_var = tk.StringVar(value="")
        alert = tk.Label(outer, textvariable=self._dash_alert_var, font=F_MAIN, anchor="w",
                         wraplength=900, justify="left")
        self._tw_add(alert, bg="bg", fg="fg")
        alert.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 8))

        apps_fr = tk.LabelFrame(
            outer, text=" Applications ", font=F_BOLD, padx=8, pady=8,
            highlightthickness=0)
        self._tw_label_frame(apps_fr)
        apps_fr.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        apps_fr.columnconfigure(0, weight=1)
        apps_fr.columnconfigure(1, weight=1)

        self._dashboard_status_vars = {}
        self._dashboard_status_labels = {}
        self._dashboard_mem_vars = {}
        for i, app in enumerate(APPS):
            r, c = divmod(i, 2)
            card = tk.Frame(apps_fr, padx=8, pady=6, cursor="hand2")
            self._tw_add(card, bg="card")
            card.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
            name = app["name"]
            port_k = app.get("port_key")
            port_txt = f"Port {self.cfg[port_k]}" if port_k else "—"
            nl = tk.Label(card, text=name, font=F_BOLD, anchor="w")
            self._tw_add(nl, bg="card", fg="fg")
            nl.pack(anchor="w")
            pl = tk.Label(card, text=port_txt, font=F_MONO, anchor="w")
            self._tw_add(pl, bg="card", fg="fg_dim")
            pl.pack(anchor="w")
            sv = tk.StringVar(value="…")
            self._dashboard_status_vars[name] = sv
            sl = tk.Label(card, textvariable=sv, font=F_MAIN, anchor="w")
            self._tw_add(sl, bg="card", fg="fg")
            sl.pack(anchor="w")
            self._dashboard_status_labels[name] = sl
            mv = tk.StringVar(value="")
            self._dashboard_mem_vars[name] = mv
            ml = tk.Label(card, textvariable=mv, font=F_MONO, anchor="w")
            self._tw_add(ml, bg="card", fg="fg_dim")
            ml.pack(anchor="w")
            
            btn_frame = tk.Frame(card)
            self._tw_add(btn_frame, bg="card")
            btn_frame.pack(fill="x", pady=(4, 0))
            
            btn_web = ttk.Button(btn_frame, text="🌐 Web UI", style="Small.TButton",
                                 command=lambda a=app: self._open_app_web_ui(a))
            btn_web.pack(side="right")
            
            tip = "Double-click to open web UI when the app is running."
            for w in (card, nl, pl, sl, ml, btn_frame):
                w.bind("<Double-1>", lambda e, a=app: self._open_app_web_ui(a))
            _Tooltip(card, tip, self)

        btn_row = ttk.Frame(outer)
        btn_row.grid(row=4, column=0, sticky="w", padx=12, pady=(0, 10))
        b1 = ttk.Button(btn_row, text="Refresh status", style="Small.TButton",
                        command=self._refresh_status)
        b1.pack(side="left", padx=(0, 6))
        b2 = ttk.Button(btn_row, text="Re-check dependencies", style="Small.TButton",
                        command=self._update_dashboard_env_ui)
        b2.pack(side="left")
        self._action_buttons.extend([b1, b2])
        _Tooltip(b1, "Poll all app statuses and memory (if psutil is installed).", self)
        _Tooltip(b2, "Re-run winget / Docker / admin / disk checks.", self)

    def _update_dashboard_env_ui(self):
        env = check_environment()
        self._dash_env_labels["winget"].set(
            "OK" if env["winget"] else "Missing — install App Installer / winget")
        self._dash_env_labels["docker_cli"].set("OK" if env["docker_cli"] else "Not found")
        self._dash_env_labels["docker_daemon"].set(
            "OK" if env["docker_daemon"] else "Not running or unreachable")
        self._dash_env_labels["admin"].set("Yes" if env["admin"] else "No — some tasks may fail")
        df = env.get("disk_free_gb")
        self._dash_env_labels["disk_free_gb"].set(f"{df} GB" if df is not None else "—")

    def _update_dashboard_alert(self):
        issues = []
        for app in APPS:
            name = app["name"]
            if name not in self.status_vars:
                continue
            s = self.status_vars[name].get()
            if s == "Stopped":
                issues.append(f"{name} is stopped")
        env = check_environment()
        if not env["winget"]:
            issues.insert(0, "winget missing — automated installs may fail")
        if not env["docker_cli"] and any(a.get("container") for a in APPS):
            issues.append("Docker CLI missing — needed for Byparr/Seer")
        elif env["docker_cli"] and not env["docker_daemon"]:
            issues.append("Docker is not running")
        if issues:
            seen = []
            for x in issues:
                if x not in seen:
                    seen.append(x)
            short = seen[:8]
            self._dash_alert_var.set(
                "Attention: " + "; ".join(short) + (" …" if len(seen) > 8 else ""))
        else:
            self._dash_alert_var.set(
                "No blocking issues detected. Review per-app status above.")

    def _set_dashboard_mem(self, name, mb):
        if name not in self._dashboard_mem_vars:
            return
        app = next((a for a in APPS if a["name"] == name), None)
        if app and app.get("container"):
            self._dashboard_mem_vars[name].set("RAM: — (see Docker)")
            return
        if mb is None:
            self._dashboard_mem_vars[name].set("RAM: — (install psutil for usage)")
        else:
            self._dashboard_mem_vars[name].set(f"RAM: ~{mb} MB")

    def _build_help_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Help  ")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        txt = scrolledtext.ScrolledText(
            outer, wrap="word", font=F_MAIN, height=24, state="disabled",
            padx=12, pady=12)
        txt.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._help_txt = txt
        self._tw_add(txt, bg="entry_bg", fg="fg")
        self._tw.append(lambda t, w=txt: w.configure(insertbackground=t["fg"]))
        self._tw.append(lambda t, w=txt: w.tag_configure("bold", font=F_BOLD, foreground=t["section_fg"]))
        txt.configure(state="normal")
        txt.insert("1.0", HELP_FAQ.strip() + "\n\n")
        txt.insert("end", f"Media Stack Manager v{VERSION}\n", "bold")
        txt.configure(state="disabled")

        hf = ttk.Frame(outer)
        hf.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        ttk.Button(hf, text="Open config folder", style="Small.TButton",
                   command=self._open_config_folder).pack(side="left", padx=(0, 8))
        ttk.Button(hf, text="Show onboarding again", style="Small.TButton",
                   command=self._show_onboarding).pack(side="left")

    def _open_config_folder(self):
        from constants import CONF_FILE
        p = CONF_FILE.parent
        try:
            os.startfile(str(p))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _show_onboarding(self):
        win = tk.Toplevel(self.root)
        win.title("Getting started wizard")
        win.transient(self.root)
        win.grab_set()
        win.minsize(500, 420)
        th = self._t()
        win.configure(bg=th["bg"])
        
        container = ttk.Frame(win, padding=14)
        container.pack(fill="both", expand=True)
        
        pages = []
        
        # --- Page 1: Welcome & Checks ---
        p1 = tk.Frame(container, bg=th["bg"])
        tk.Label(p1, text="Welcome to Media Stack Manager", font=F_TITLE, bg=th["bg"], fg=th["fg"]).pack(pady=(0, 12))
        tk.Label(p1, text="Before we begin, let's check your system dependencies.", 
                 font=F_MAIN, bg=th["bg"], fg=th["fg"]).pack(anchor="w", pady=(0, 12))
        
        env_frame = tk.Frame(p1, bg=th["lf_bg"], padx=10, pady=10)
        env_frame.pack(fill="x", pady=8)
        env_labels = {}
        for key, title in [("winget", "winget (installs):"), ("docker_cli", "Docker CLI:"), ("docker_daemon", "Docker running:"), ("admin", "Administrator:")]:
            row = tk.Frame(env_frame, bg=th["lf_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=title, font=F_MAIN, bg=th["lf_bg"], fg=th["fg_dim"], width=20, anchor="w").pack(side="left")
            sv = tk.StringVar(value="Checking...")
            env_labels[key] = sv
            tk.Label(row, textvariable=sv, font=F_BOLD, bg=th["lf_bg"], fg=th["fg"]).pack(side="left")
            
        def _check_env():
            env = check_environment()
            env_labels["winget"].set("OK" if env["winget"] else "Missing")
            env_labels["docker_cli"].set("OK" if env["docker_cli"] else "Missing")
            env_labels["docker_daemon"].set("OK" if env["docker_daemon"] else "Not running")
            env_labels["admin"].set("Yes" if env["admin"] else "No")
        self.root.after(100, _check_env)
        pages.append(p1)
        
        # --- Page 2: Folders ---
        p2 = tk.Frame(container, bg=th["bg"])
        tk.Label(p2, text="Essential Folders Setup", font=F_TITLE, bg=th["bg"], fg=th["fg"]).pack(pady=(0, 12))
        tk.Label(p2, text="Where should your data be stored? (Paths must exist).", 
                 font=F_MAIN, bg=th["bg"], fg=th["fg"]).pack(anchor="w", pady=(0, 12))
                 
        f_frame = tk.Frame(p2, bg=th["bg"])
        f_frame.pack(fill="x", pady=8)
        
        def _field(parent, label, key):
            row = tk.Frame(parent, bg=th["bg"])
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, font=F_MAIN, bg=th["bg"], fg=th["fg"], width=16, anchor="w").pack(side="left")
            var = tk.StringVar(value=self.cfg.get(key, ""))
            e = ttk.Entry(row, textvariable=var, width=32)
            e.pack(side="left", padx=4)
            ttk.Button(row, text="...", width=3, style="Small.TButton",
                       command=lambda v=var: v.set(filedialog.askdirectory() or v.get())).pack(side="left")
            return var
            
        v_base = _field(f_frame, "Base folder:", "base_root")
        v_media = _field(f_frame, "Media folder:", "media_root")
        v_down = _field(f_frame, "Downloads folder:", "downloads_root")
        v_back = _field(f_frame, "Backup folder:", "backup_root")
        pages.append(p2)
        
        # --- Page 3: Summary ---
        p3 = tk.Frame(container, bg=th["bg"])
        tk.Label(p3, text="You're Ready!", font=F_TITLE, bg=th["bg"], fg=th["fg"]).pack(pady=(0, 12))
        body = (
            "1. Install apps from the Install tab, start them, then run Auto-Configure.\n\n"
            "2. Add a Jellyfin API key in Settings if you want libraries created automatically.\n\n"
            "See the Help tab for FAQ and documentation links."
        )
        t = tk.Label(p3, text=body, font=F_MAIN, bg=th["bg"], fg=th["fg"], justify="left")
        t.pack(anchor="w", pady=(0, 24))
        
        dont = tk.BooleanVar(value=True)
        ttk.Checkbutton(p3, text="Do not show this wizard again", variable=dont).pack(anchor="w")
        pages.append(p3)
        
        curr_page = [0]
        
        def _show_page(idx):
            for p in pages: p.pack_forget()
            pages[idx].pack(fill="both", expand=True)
            b_prev.pack_forget()
            b_next.pack_forget()
            b_finish.pack_forget()
            if idx > 0:
                b_prev.pack(side="left")
            if idx < len(pages) - 1:
                b_next.pack(side="right")
            else:
                b_finish.pack(side="right")
        
        bf = ttk.Frame(win)
        bf.pack(fill="x", padx=14, pady=14)
        
        def _next():
            if curr_page[0] == 1:
                self.cfg["base_root"] = v_base.get()
                self.cfg["media_root"] = v_media.get()
                self.cfg["downloads_root"] = v_down.get()
                self.cfg["backup_root"] = v_back.get()
                errs = self.cfg.validate()
                if errs:
                    messagebox.showwarning("Validation failed", "\n".join(errs), parent=win)
                    return
                self.cfg.save()
                self._reload_settings_from_cfg()
            if curr_page[0] < len(pages) - 1:
                curr_page[0] += 1
                _show_page(curr_page[0])
                
        def _prev():
            if curr_page[0] > 0:
                curr_page[0] -= 1
                _show_page(curr_page[0])
                
        def _finish():
            if dont.get():
                self.cfg["onboarding_complete"] = True
                self.cfg.save()
            win.destroy()
            
        b_prev = ttk.Button(bf, text="< Back", style="Small.TButton", command=_prev)
        b_next = ttk.Button(bf, text="Next >", style="Accent.TButton", command=_next)
        b_finish = ttk.Button(bf, text="Get started", style="Accent.TButton", command=_finish)
        
        _show_page(0)

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
        btn_ref = ttk.Button(top, text="Refresh Status", style="Small.TButton",
                   command=self._refresh_status)
        btn_ref.pack(side="left", padx=(8, 0))
        _Tooltip(btn_ref, "Re-query Windows services, Docker, and executables.", self)
        btn_inst = ttk.Button(top, text="Install All", style="Accent.TButton",
                   command=self._install_all)
        btn_inst.pack(side="right")
        self._action_buttons.append(btn_inst)
        btn_un = ttk.Button(top, text="Uninstall All", style="Accent.TButton",
                   command=self._uninstall_all)
        btn_un.pack(side="right", padx=(0, 6))
        self._action_buttons.append(btn_un)
        btn_auto = ttk.Button(top, text="Auto-Configure", style="Accent.TButton",
                   command=self._auto_configure)
        btn_auto.pack(side="right", padx=(0, 6))
        self._action_buttons.append(btn_auto)
        _Tooltip(btn_inst, "Install all apps in sequence (winget or Docker).", self)
        _Tooltip(btn_un, "Uninstall all apps (with confirmation).", self)
        _Tooltip(btn_auto, "Apply paths and app links (requires running services).", self)

        cf = ttk.Frame(outer)
        cf.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(cf, highlightthickness=0)
        self._tw_add(canvas, bg="bg")
        self._tw.append(lambda t, w=canvas: w.configure(
            highlightbackground=t["bg"], highlightcolor=t["bg"]))
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
        self._tw_add(status_lbl, bg="card", fg="fg")
        status_lbl.grid(row=1, column=2, sticky="w", padx=4, pady=(0, 6))
        self._status_labels[name] = status_lbl
        ttk.Button(row, text="Install", style="Small.TButton",
                   command=lambda a=app: self._install_one(a)
                   ).grid(row=0, column=3, rowspan=2, padx=8, pady=6)
        ttk.Button(row, text="Uninstall", style="Small.TButton",
                   command=lambda a=app: self._uninstall_one(a)
                   ).grid(row=0, column=4, rowspan=2, padx=6, pady=6)

    def _refresh_status(self):
        def run():
            for app in APPS:
                label, color_key = self.ops.check_app_status(app)
                name = app["name"]
                self.q.put(lambda n=name, lb=label, ck=color_key:
                           self._set_status(n, lb, ck))
            for app in APPS:
                mem = app_memory_mb(app)
                n = app["name"]
                self.q.put(lambda n=n, m=mem: self._set_dashboard_mem(n, m))
            self.q.put(self._update_dashboard_alert)
        self._run_bg(run)

    def _schedule_status_poll(self):
        if (
            self.cfg.get("auto_refresh_enabled", True)
            and not self._in_quiet_hours()
            and not self._busy
        ):
            self._refresh_status()
        self._schedule_next_poll()

    def _set_status(self, name, label, color_key):
        t = self._t()
        if name in self.status_vars:
            self.status_vars[name].set(label)
        if name in self._status_labels:
            color = t.get(color_key, t["fg_dim"])
            self._status_labels[name].configure(fg=color)
        if getattr(self, "_dashboard_status_vars", None) and name in self._dashboard_status_vars:
            self._dashboard_status_vars[name].set(label)
            if name in self._dashboard_status_labels:
                color = t.get(color_key, t["fg_dim"])
                self._dashboard_status_labels[name].configure(fg=color)

    def _browse_base(self):
        d = filedialog.askdirectory(initialdir=self.base_var.get())
        if d:
            self.base_var.set(d)
            self.cfg["base_root"] = d
            self.cfg.save()

    def _app_local_url(self, app):
        pk = app.get("port_key")
        if not pk:
            return None
        try:
            port = int(str(self.cfg[pk]).strip())
        except Exception:
            return None
        return f"http://127.0.0.1:{port}/"

    def _open_app_web_ui(self, app):
        name = app["name"]
        if name not in self.status_vars:
            return
        st = self.status_vars[name].get()
        if st == "Not installed":
            messagebox.showinfo("Open in browser", f"{name} is not installed yet.")
            return
        url = self._app_local_url(app)
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            self.log(f"Could not open browser: {e}", "err")

    def _install_one(self, app):
        self._run_bg(lambda: self.ops.install_app(app))

    def _uninstall_one(self, app):
        name = app["name"]
        if not messagebox.askyesno("Uninstall", f"Uninstall {name}?"):
            return
        remove_data = messagebox.askyesno(
            "Remove data/config?",
            "Also remove data/config folders?\n\n"
            "This is more destructive and may remove your settings and databases.")
        self._run_bg(lambda: self.ops.uninstall_app(app, remove_data=remove_data))

    def _install_all(self):
        self.cfg["base_root"] = self.base_var.get()
        self.cfg.save()
        n = len(APPS)

        def run():
            try:
                for i, a in enumerate(APPS, start=1):
                    self._enqueue_task_progress(
                        i, n, f"Installing {a['name']} ({i}/{n})…")
                    self.ops.install_app(a)
            finally:
                self._enqueue_clear_task_progress()

        self._run_bg(run)

    def _uninstall_all(self):
        if not messagebox.askyesno("Uninstall All", "Uninstall ALL apps?"):
            return
        remove_data = messagebox.askyesno(
            "Remove data/config?",
            "Also remove data/config folders for ALL apps?\n\n"
            "This is more destructive and may remove your settings and databases.")
        n = len(APPS)

        def run():
            try:
                for i, a in enumerate(APPS, start=1):
                    self._enqueue_task_progress(
                        i, n, f"Uninstalling {a['name']} ({i}/{n})…")
                    self.ops.uninstall_app(a, remove_data=remove_data)
            finally:
                self._enqueue_clear_task_progress()

        self._run_bg(run)

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

        def run():
            try:
                def progress(step, total, label):
                    self._enqueue_task_progress(step, total, f"Auto-Configure: {label}")

                self.ops.configure_all(progress_cb=progress)
            finally:
                self._enqueue_clear_task_progress()

        self._run_bg(run)

    # --- Backup / Restore tab ---

    def _build_backup_tab(self):
        outer = ttk.Frame(self.nb)
        self._backup_outer = outer
        self.nb.add(outer, text="  Backup & Restore  ")
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        lf = tk.LabelFrame(
            outer, text=" Backup ", font=F_BOLD, padx=10, pady=10,
            highlightthickness=0)
        self._backup_lf = lf
        self._tw_label_frame(lf)
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

        rf = tk.LabelFrame(
            outer, text=" Restore ", font=F_BOLD, padx=10, pady=10,
            highlightthickness=0)
        self._backup_rf = rf
        self._tw_label_frame(rf)
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
        self._layout_backup_columns()

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
        self._tw.append(lambda t, w=canvas: w.configure(
            highlightbackground=t["bg"], highlightcolor=t["bg"]))
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
        self._bool_setting_vars = {
            "auto_refresh_enabled": tk.BooleanVar(
                value=bool(self.cfg.get("auto_refresh_enabled"))),
            "quiet_hours_enabled": tk.BooleanVar(
                value=bool(self.cfg.get("quiet_hours_enabled"))),
        }

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

        section("Status refresh")
        ttk.Checkbutton(
            inner, text="Enable automatic status refresh (Dashboard)",
            variable=self._bool_setting_vars["auto_refresh_enabled"]).grid(
                row=row_idx[0], column=1, sticky="w", padx=4, pady=2)
        row_idx[0] += 1
        field("Refresh interval (seconds)", "poll_interval_seconds")
        ttk.Checkbutton(
            inner, text="Quiet hours — pause refresh between start and end",
            variable=self._bool_setting_vars["quiet_hours_enabled"]).grid(
                row=row_idx[0], column=1, sticky="w", padx=4, pady=2)
        row_idx[0] += 1
        field("Quiet hours start (24h)", "quiet_hours_start")
        field("Quiet hours end (24h)", "quiet_hours_end")

        section("Settings file")
        frow = ttk.Frame(inner)
        frow.grid(row=row_idx[0], column=0, columnspan=3, sticky="w", padx=14, pady=4)
        row_idx[0] += 1
        ttk.Button(frow, text="Export settings…", style="Small.TButton",
                   command=self._export_settings).pack(side="left", padx=(0, 8))
        ttk.Button(frow, text="Import settings…", style="Small.TButton",
                   command=self._import_settings).pack(side="left")

        inner.columnconfigure(1, weight=1)
        srow = ttk.Frame(inner)
        srow.grid(row=row_idx[0], column=0, columnspan=3, pady=14, padx=14, sticky="w")
        b_save = ttk.Button(srow, text="Save Settings", style="Accent.TButton",
                            command=self._save_settings)
        b_save.pack(side="left", padx=(0, 8))
        b_json = ttk.Button(srow, text="Advanced JSON…", style="Small.TButton",
                            command=self._edit_json_advanced)
        b_json.pack(side="left")
        _Tooltip(b_save, "Validate paths and ports, then write media-stack-config.json.", self)
        _Tooltip(b_json, "Edit the raw JSON (expert). Validates before save.", self)

    def _reload_settings_from_cfg(self):
        for key, var in self._setting_vars.items():
            var.set(str(self.cfg[key]))
        for key, var in getattr(self, "_bool_setting_vars", {}).items():
            var.set(bool(self.cfg.get(key)))
        for key, var in getattr(self, "_checklist_vars", {}).items():
            var.set(bool(self.cfg.get(key)))

    def _edit_json_advanced(self):
        from constants import CONF_FILE
        top = tk.Toplevel(self.root)
        top.title("Advanced — config JSON")
        top.geometry("680x560")
        top.transient(self.root)
        th = self._t()
        top.configure(bg=th["bg"])
        txt = scrolledtext.ScrolledText(
            top, font=F_MONO, wrap="none", height=24,
            bg=th["entry_bg"], fg=th["fg"], insertbackground=th["fg"],
            relief="flat", borderwidth=0)
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", json.dumps(self.cfg.data, indent=2))
        self._json_editor_win = top
        self._json_editor_txt = txt

        def _json_destroy(event):
            if event.widget is top:
                self._json_editor_win = None
                self._json_editor_txt = None

        top.bind("<Destroy>", _json_destroy)

        def save_json():
            raw = txt.get("1.0", "end").strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                messagebox.showerror("Invalid JSON", str(e))
                return
            if not isinstance(data, dict):
                messagebox.showerror("Invalid JSON", "Root must be a JSON object.")
                return
            merged = {**DEFAULTS, **data}
            self.cfg.data = merged
            errs = self.cfg.validate()
            if errs:
                messagebox.showwarning(
                    "Validation failed",
                    "Fix these issues, then save again:\n\n" + "\n".join(errs))
                return
            self.cfg.save()
            self._reload_settings_from_cfg()
            self.base_var.set(self.cfg["base_root"])
            self.log(f"Settings saved from JSON editor ({CONF_FILE.name}).", "ok")
            self._theme_name = self.cfg.get("theme", "light")
            self._apply_theme()
            top.destroy()

        bf = ttk.Frame(top)
        bf.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bf, text="Save", style="Accent.TButton", command=save_json).pack(side="right")
        ttk.Button(bf, text="Cancel", style="Small.TButton", command=top.destroy).pack(side="right", padx=(0, 8))

    def _export_settings(self):
        from constants import CONF_FILE
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialfile=f"{CONF_FILE.stem}-export.json",
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.cfg.data, indent=2), encoding="utf-8")
            self.log(f"Exported settings to {path}", "ok")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _import_settings(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
                "Import settings",
                "Replace current settings with this file?\n\n"
                "Invalid paths will fail validation. Continue?"):
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("File must contain a JSON object.")
            self.cfg.data = {**DEFAULTS, **data}
            errs = self.cfg.validate()
            if errs:
                messagebox.showwarning(
                    "Validation failed",
                    "Fix the file or your folders, then try again:\n\n" + "\n".join(errs))
                return
            self.cfg.save()
            self._reload_settings_from_cfg()
            self.base_var.set(self.cfg["base_root"])
            self.log(f"Imported settings from {path}", "ok")
            self._theme_name = self.cfg.get("theme", "light")
            self._apply_theme()
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def _save_settings(self):
        for key, var in self._setting_vars.items():
            val = var.get()
            if key in CONFIG_PORT_KEYS:
                if not val.isdigit() or not (1 <= int(val) <= 65535):
                    messagebox.showwarning("Invalid port",
                        f"{key} must be a number between 1 and 65535.")
                    return
            if key == "poll_interval_seconds":
                if not val.strip().isdigit() or not (15 <= int(val.strip()) <= 3600):
                    messagebox.showwarning(
                        "Invalid value",
                        "Refresh interval must be between 15 and 3600 seconds.")
                    return
            self.cfg[key] = val
        for key, var in getattr(self, "_bool_setting_vars", {}).items():
            self.cfg[key] = var.get()
        errs = self.cfg.validate()
        if errs:
            messagebox.showwarning(
                "Validation failed",
                "Fix these issues before saving:\n\n" + "\n".join(errs))
            return
        self.cfg.save()
        self.base_var.set(self.cfg["base_root"])
        self.log("Settings saved.", "ok")
        self._theme_name = self.cfg.get("theme", "light")
        self._apply_theme()

    # --- Log ---

    def _build_log(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=(4, 0))
        hdr = tk.Frame(frame, bg=C_LOG_BG)
        hdr.pack(fill="x")
        
        self._log_collapsed = True
        
        self._log_toggle_btn = tk.Button(
            hdr, text="[\u25B2] Output Log", bg=C_LOG_BG, fg="#888",
            font=F_MONO, bd=0, cursor="hand2", command=self._toggle_log
        )
        self._log_toggle_btn.pack(side="left", padx=6, pady=2)
        
        tk.Button(hdr, text="Clear", bg=C_LOG_BG, fg="#888", font=F_MONO,
                  bd=0, cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=6)
        self.log_txt = scrolledtext.ScrolledText(
            frame, height=10, bg=C_LOG_BG, fg=C_LOG_FG, font=F_MONO,
            insertbackground=C_LOG_FG, wrap="word", state="disabled",
            relief="flat", borderwidth=0)
        
        # log_txt is NOT packed initially, so it's collapsed by default
        
        self.log_txt.tag_configure("ok",   foreground=C_LOG_OK)
        self.log_txt.tag_configure("warn", foreground=C_LOG_WRN)
        self.log_txt.tag_configure("err",  foreground=C_LOG_ERR)
        self.log_txt.tag_configure("bold", foreground="#ffffff", font=("Consolas", 9, "bold"))
        self.log_txt.tag_configure("info", foreground=C_LOG_FG)

    def _toggle_log(self):
        self._log_collapsed = not self._log_collapsed
        if self._log_collapsed:
            self._log_toggle_btn.configure(text="[\u25B2] Output Log")
            self.log_txt.pack_forget()
        else:
            self._log_toggle_btn.configure(text="[\u25BC] Output Log")
            self.log_txt.pack(fill="x")

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
