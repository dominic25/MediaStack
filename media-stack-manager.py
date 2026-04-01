#!/usr/bin/env python3
"""
media-stack-manager.py
All-in-one GUI: install, backup, and restore your self-hosted media stack.
Requirements: Python 3.8+  |  Windows 10/11  |  No pip packages required.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import subprocess, threading, queue, os, json, shutil, zipfile
import tempfile, time, sys, ctypes, configparser
import urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION   = "1.0"
CONF_FILE = Path(__file__).with_name("media-stack-config.json")

C_BG      = "#f5f5f5"
C_CARD    = "#ffffff"
C_ACCENT  = "#1565c0"
C_ALT     = "#e3f2fd"
C_SUCCESS = "#2e7d32"
C_WARN    = "#e65100"
C_ERR     = "#c62828"
C_LOG_BG  = "#1e1e1e"
C_LOG_FG  = "#d4d4d4"
C_LOG_OK  = "#4ec9b0"
C_LOG_WRN = "#ce9178"
C_LOG_ERR = "#f48771"
F_MAIN    = ("Segoe UI", 10)
F_BOLD    = ("Segoe UI", 10, "bold")
F_TITLE   = ("Segoe UI", 13, "bold")
F_MONO    = ("Consolas", 9)

# ---------------------------------------------------------------------------
# App definitions
# ---------------------------------------------------------------------------
APPS = [
    {
        "name": "Jellyfin", "desc": "Media server",
        "install": "browser", "url": "https://jellyfin.org/downloads/windows/server",
        "service": "Jellyfin", "process": "jellyfin",
        "exe_candidates": ["jellyfin.exe", "JellyfinTray.exe"],
        "common_dirs": [r"C:\Program Files\Jellyfin\Server"],
        "config_paths": [r"C:\ProgramData\Jellyfin\Server", r"%LOCALAPPDATA%\jellyfin"],
        "backup": "jellyfin_api", "port_key": "jellyfin_port",
    },
    {
        "name": "Sonarr", "desc": "TV show management",
        "install": "winget", "winget_id": "TeamSonarr.Sonarr",
        "service": "Sonarr", "process": "Sonarr",
        "exe_candidates": ["Sonarr.exe"],
        "common_dirs": [r"C:\Program Files\Sonarr"],
        "config_paths": [r"C:\ProgramData\Sonarr", r"%APPDATA%\Sonarr"],
        "backup": "arr_api", "arr_version": "v3", "port_key": "sonarr_port",
    },
    {
        "name": "Radarr", "desc": "Movie management",
        "install": "winget", "winget_id": "TeamRadarr.Radarr",
        "service": "Radarr", "process": "Radarr",
        "exe_candidates": ["Radarr.exe"],
        "common_dirs": [r"C:\Program Files\Radarr"],
        "config_paths": [r"C:\ProgramData\Radarr", r"%APPDATA%\Radarr"],
        "backup": "arr_api", "arr_version": "v3", "port_key": "radarr_port",
    },
    {
        "name": "Prowlarr", "desc": "Indexer management",
        "install": "winget", "winget_id": "TeamProwlarr.Prowlarr",
        "service": "Prowlarr", "process": "Prowlarr",
        "exe_candidates": ["Prowlarr.exe"],
        "common_dirs": [r"C:\Program Files\Prowlarr"],
        "config_paths": [r"C:\ProgramData\Prowlarr", r"%APPDATA%\Prowlarr"],
        "backup": "arr_api", "arr_version": "v1", "port_key": "prowlarr_port",
    },
    {
        "name": "Bazarr", "desc": "Subtitle management",
        "install": "winget", "winget_id": "Morpheus.Bazarr",
        "service": "Bazarr", "process": "bazarr",
        "exe_candidates": ["bazarr.exe", "Bazarr.exe"],
        "common_dirs": [r"C:\Program Files\Bazarr"],
        "config_paths": [r"C:\ProgramData\Bazarr", r"%APPDATA%\Bazarr"],
        "backup": "bazarr_api", "port_key": "bazarr_port",
    },
    {
        "name": "qBittorrent", "desc": "Torrent download client",
        "install": "winget", "winget_id": "qBittorrent.qBittorrent.lt2",
        "service": "qBittorrent", "process": "qbittorrent",
        "exe_candidates": ["qbittorrent.exe", "qBittorrent.exe"],
        "common_dirs": [r"C:\Program Files\qBittorrent"],
        "config_paths": [r"%APPDATA%\qBittorrent", r"C:\ProgramData\qBittorrent"],
        "backup": "file_copy", "port_key": "qb_port",
    },
    {
        "name": "Byparr", "desc": "Cloudflare bypass helper (Docker)",
        "install": "docker", "docker_image_key": "byparr_image",
        "container": "byparr", "port_key": "byparr_port",
        "volume_subpath": "Byparr",
        "backup": None,
    },
    {
        "name": "Seer", "desc": "Media request manager (Docker)",
        "install": "docker", "docker_image_key": "seer_image",
        "container": "seer", "port_key": "seer_port",
        "volume_subpath": "Seer\\config",
        "backup": "file_copy",
    },
]

DEFAULTS = {
    "base_root":       r"C:\MediaStack",
    "media_root":      r"C:\MediaStack\Media",
    "downloads_root":  r"C:\MediaStack\Downloads",
    "backup_root":     r"C:\MediaStack\Backups",
    "jellyfin_port":   "8096",
    "sonarr_port":     "8989",
    "radarr_port":     "7878",
    "bazarr_port":     "6767",
    "prowlarr_port":   "9696",
    "qb_port":         "8080",
    "byparr_port":     "8191",
    "seer_port":       "5055",
    "jellyfin_api_key": "",
    "byparr_image":    "thetadev256/byparr:latest",
    "seer_image":      "seerr/seerr:latest",
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        if CONF_FILE.exists():
            try:
                saved = json.loads(CONF_FILE.read_text())
                self.data.update(saved)
            except Exception:
                pass

    def save(self):
        CONF_FILE.write_text(json.dumps(self.data, indent=2))

    def __getitem__(self, k): return self.data.get(k, "")
    def __setitem__(self, k, v): self.data[k] = v
    def get(self, k, d=""): return self.data.get(k, d)

# ---------------------------------------------------------------------------
# Backend operations
# ---------------------------------------------------------------------------
class Ops:
    """All install / backup / restore logic. Methods run on background threads.
    Use self.log() to emit messages - never call tkinter from here."""

    def __init__(self, config: Config, log_fn):
        self.cfg    = config
        self.log_fn = log_fn

    def log(self, msg, tag="info"):
        self.log_fn(msg, tag)

    # ---- helpers ----

    def resolve_path(self, candidates):
        for c in candidates:
            p = Path(os.path.expandvars(c))
            if p.exists():
                return p
        return None

    def find_exe(self, app):
        """Find app exe from service registry or common dirs."""
        # try common install dirs
        for d in app.get("common_dirs", []):
            for exe in app.get("exe_candidates", []):
                p = Path(d) / exe
                if p.exists():
                    return p
        # try Program Files variants
        for pf in [r"C:\Program Files", r"C:\Program Files (x86)"]:
            for exe in app.get("exe_candidates", []):
                p = Path(pf) / app["name"] / exe
                if p.exists():
                    return p
        return None

    def run(self, args, **kwargs):
        return subprocess.run(args, capture_output=True, text=True, **kwargs)

    def run_stream(self, args, **kwargs):
        """Run a command and stream stdout line-by-line to log."""
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, **kwargs)
        for line in proc.stdout:
            self.log(line.rstrip())
        proc.wait()
        return proc.returncode

    def http_post(self, url, headers, body=None, timeout=15):
        data = body.encode() if isinstance(body, str) else body
        req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())

    def http_get(self, url, headers, timeout=15):
        req  = urllib.request.Request(url, headers=headers, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())

    # ---- stop / start ----

    def stop_app(self, app):
        name = app["name"]
        if app.get("container"):
            self.log(f"  Stopping container: {app['container']}", "warn")
            self.run(["docker", "stop", app["container"]])
            time.sleep(4)
            return
        svc = app.get("service")
        if svc:
            r = self.run(["sc", "query", svc])
            if "RUNNING" in r.stdout:
                self.log(f"  Stopping service: {svc}", "warn")
                self.run(["net", "stop", svc, "/y"])
                time.sleep(2)
                return
        proc = app.get("process")
        if proc:
            r = self.run(["tasklist", "/fi", f"imagename eq {proc}.exe"])
            if proc.lower() in r.stdout.lower():
                self.log(f"  Stopping process: {proc}", "warn")
                self.run(["taskkill", "/f", "/im", f"{proc}.exe"])
                time.sleep(2)

    def start_app(self, app):
        name = app["name"]
        if app.get("container"):
            self.log(f"  Starting container: {app['container']}", "ok")
            self.run(["docker", "start", app["container"]])
            return
        svc = app.get("service")
        if svc:
            r = self.run(["sc", "query", svc])
            if r.returncode == 0 and "does not exist" not in r.stdout:
                self.log(f"  Starting service: {svc}", "ok")
                self.run(["net", "start", svc])
                return
        # No service - find and launch exe
        exe = self.find_exe(app)
        if exe:
            self.log(f"  Launching exe: {exe}", "ok")
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
        else:
            self.log(f"  Could not find {name} exe to launch - relaunch manually.", "warn")

    # ---- install ----

    def install_app(self, app):
        name = app["name"]
        method = app.get("install")
        self.log(f"=== Installing {name} ===", "bold")
        if method == "winget":
            rc = self.run_stream([
                "winget", "install", "--id", app["winget_id"], "-e",
                "--accept-package-agreements", "--accept-source-agreements"
            ])
            if rc == 0:
                self.log(f"  {name} installed.", "ok")
            else:
                self.log(f"  winget returned {rc} for {name}.", "warn")
        elif method == "browser":
            self.log(f"  Opening browser to {app['url']}", "info")
            os.startfile(app["url"])
            self.log("  Complete the installer, then click Refresh Status.", "warn")
        elif method == "docker":
            self._docker_install(app)

    def _docker_install(self, app):
        name      = app["name"]
        image     = self.cfg[app["docker_image_key"]]
        container = app["container"]
        port_host = self.cfg[app["port_key"]]
        base      = Path(self.cfg["base_root"])
        vol_sub   = app.get("volume_subpath")
        vol_path  = base / vol_sub if vol_sub else base / name
        vol_path.mkdir(parents=True, exist_ok=True)

        # 1. Remove the target container if it already exists (any state)
        r = self.run(["docker", "ps", "-a", "-q", "--filter", f"name=^/{container}$"])
        if r.stdout.strip():
            self.log(f"  Removing existing '{container}' container ...", "warn")
            self.run(["docker", "stop", container])
            self.run(["docker", "rm",   container])

        # 2. Kill ANY container that is already bound to the host port.
        #    This catches old containers with different names (e.g. 'jellyseerr' -> 'seer').
        r = self.run(["docker", "ps", "-q", "--filter", f"publish={port_host}"])
        for cid in r.stdout.strip().splitlines():
            cid = cid.strip()
            if not cid:
                continue
            # Get its name for a helpful log message
            nr = self.run(["docker", "inspect", "--format", "{{.Name}}", cid])
            cname = nr.stdout.strip().lstrip("/")
            self.log(f"  Port {port_host} in use by container '{cname}' - stopping it ...", "warn")
            self.run(["docker", "stop", cid])
            self.run(["docker", "rm",   cid])

        self.log(f"  Pulling {image} ...")
        self.run_stream(["docker", "pull", image])

        # Determine internal container port
        inner = "8191" if name == "Byparr" else port_host

        # Build run command
        # Seer (seerr/seerr) requires --init for correct signal handling
        cmd = ["docker", "run", "-d", "--name", container, "--restart", "unless-stopped"]
        if name == "Seer":
            cmd += ["--init"]
        cmd += ["-p", f"{port_host}:{inner}", "-v", f"{vol_path}:/app/config", image]

        r = self.run(cmd)
        if r.returncode == 0:
            self.log(f"  {name} container started on port {port_host}.", "ok")
        else:
            self.log(f"  docker run failed: {r.stderr.strip()}", "err")

    # ---- backup helpers ----

    def _arr_api_backup(self, app, config_dir, backup_set):
        port    = self.cfg[app["port_key"]]
        version = app["arr_version"]
        name    = app["name"]
        try:
            # Read api key from config.xml
            import xml.etree.ElementTree as ET
            xml_path = config_dir / "config.xml"
            if not xml_path.exists():
                self.log(f"  config.xml not found in {config_dir}", "err")
                return False
            root = ET.parse(xml_path).getroot()
            api_key = root.findtext("ApiKey")
            port    = root.findtext("Port") or port
            base    = f"http://localhost:{port}/api/{version}"
            hdrs    = {"X-Api-Key": api_key, "Content-Type": "application/json"}
            # Trigger backup
            self.log(f"  Triggering {name} API backup on port {port} ...")
            result = self.http_post(f"{base}/command", hdrs, '{"name":"Backup"}')
            cmd_id = result["id"]
            # Poll for completion
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(3)
                status = self.http_get(f"{base}/command/{cmd_id}", hdrs)
                if status["status"] in ("completed", "failed"):
                    break
            if status["status"] != "completed":
                self.log(f"  {name} backup command status: {status['status']}", "err")
                return False
            # Copy newest zip from app Backups folder
            app_bk_dir = config_dir / "Backups"
            zips = sorted(app_bk_dir.glob("**/*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not zips:
                self.log(f"  No zip found in {app_bk_dir}", "err")
                return False
            dest = Path(backup_set) / f"{name}.zip"
            shutil.copy2(zips[0], dest)
            mb = round(dest.stat().st_size / 1048576, 2)
            self.log(f"  OK - {zips[0].name} -> {name}.zip ({mb} MB)", "ok")
            return True
        except Exception as e:
            self.log(f"  {name} API backup failed: {e}", "err")
            return False

    def _bazarr_file_backup(self, app, config_dir, backup_set):
        config_dir = Path(config_dir)
        dest = Path(backup_set) / "Bazarr.zip"
        
        # Based on your directory listing: ['config', 'db'] are the essentials
        items_to_backup = ["config", "db"]
        
        try:
            self.log(f"  Starting file-based backup for Bazarr...")
            import zipfile
            import tempfile

            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
                for folder_name in items_to_backup:
                    source_path = config_dir / folder_name
                    
                    if not source_path.exists():
                        self.log(f"    Warning: {folder_name} not found, skipping.", "warn")
                        continue
                    
                    self.log(f"    Archiving {folder_name}...")
                    for file in source_path.rglob('*'):
                        if file.is_file():
                            try:
                                # Special handling for the database to avoid 'Locked' errors
                                if file.suffix == ".db":
                                    with tempfile.TemporaryDirectory() as tmpdir:
                                        tmp_file = Path(tmpdir) / file.name
                                        shutil.copy2(file, tmp_file)
                                        zf.write(tmp_file, file.relative_to(config_dir))
                                else:
                                    zf.write(file, file.relative_to(config_dir))
                            except Exception as fe:
                                self.log(f"    Could not backup {file.name}: {fe}", "warn")

            if dest.exists() and dest.stat().st_size > 0:
                mb = round(dest.stat().st_size / 1048576, 2)
                self.log(f"  OK - Created Bazarr.zip ({mb} MB)", "ok")
                return True
            
            return False

        except Exception as e:
            self.log(f"  Bazarr file backup failed: {e}", "err")
            return False

    def _jellyfin_api_backup(self, app, config_dir, backup_set):
        port    = self.cfg["jellyfin_port"]
        api_key = self.cfg["jellyfin_api_key"]
        if not api_key:
            self.log("  No Jellyfin API key set (Settings tab). Falling back to file copy.", "warn")
            return False
        try:
            self.log(f"  Triggering Jellyfin backup via API on port {port} ...")
            
            hdrs  = {
                "X-MediaBrowser-Token": api_key, 
                "Content-Type": "application/json"
            }
            
            payload = {
                "Database": True,
                "Metadata": True,
                "Subtitles": True,
                "Trickplay": False  # Usually kept False to keep backup size small
            }

            result = self.http_post(f"http://localhost:{port}/Backup/Create", hdrs, json.dumps(payload), timeout=300)
            
            # Find newest backup zip
            # Note: Ensure config_dir points to the actual Jellyfin config root
            bk_dir = Path(config_dir) / "data" / "backups"
            zips = sorted(bk_dir.glob("**/*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            if not zips:
                self.log("  No backup zip produced in 'backups' folder. Falling back to file copy.", "warn")
                return False
                
            dest = Path(backup_set) / "Jellyfin.zip"
            shutil.copy2(zips[0], dest)
            mb = round(dest.stat().st_size / 1048576, 2)
            self.log(f"  OK - {zips[0].name} -> Jellyfin.zip ({mb} MB)", "ok")
            return True
            
        except Exception as e:
            if "timeout" in str(e).lower():
                self.log("  API request timed out")
            else:
                self.log(f"  Jellyfin API backup failed: {e} - falling back to file copy.", "warn")
            return False


    def _file_copy_backup(self, app, src_dir, backup_set):
        """Robust per-file copy to temp dir, then zip. Skips locked files."""
        name = app["name"]
        tmp  = Path(tempfile.mkdtemp(prefix=f"mstack_{name}_"))
        skipped = []
        try:
            for item in src_dir.rglob("*"):
                rel    = item.relative_to(src_dir)
                target = tmp / rel
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    for attempt in range(3):
                        try:
                            shutil.copy2(item, target)
                            break
                        except (PermissionError, OSError):
                            if attempt < 2:
                                time.sleep(1)
                            else:
                                skipped.append(str(rel))
            if skipped:
                self.log(f"  Skipped {len(skipped)} locked file(s): {skipped[:3]}", "warn")
            dest  = Path(backup_set) / f"{name}.zip"
            files = list(tmp.rglob("*"))
            if not files:
                self.log(f"  Nothing to zip for {name}.", "warn")
                return False
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    if f.is_file():
                        zf.write(f, f.relative_to(tmp))
            mb = round(dest.stat().st_size / 1048576, 2)
            self.log(f"  OK - {name}.zip ({mb} MB)", "ok")
            return True
        except Exception as e:
            self.log(f"  File copy backup failed for {name}: {e}", "err")
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- backup orchestrator ----

    def backup_all(self, callback=None):
        ts  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bks = Path(self.cfg["backup_root"])
        bks.mkdir(parents=True, exist_ok=True)
        bk_set = bks / ts
        bk_set.mkdir()
        self.log(f"=== BACKUP -> {bk_set} ===", "bold")
        results = []
        for app in APPS:
            if app.get("backup") is None:
                continue  # Byparr: stateless, skip
            name   = app["name"]
            method = app["backup"]
            self.log(f"")
            self.log(f"--- {name} ---", "bold")
            if method == "arr_api":
                cfg_dir = self.resolve_path(app["config_paths"])
                if cfg_dir:
                    ok = self._arr_api_backup(app, cfg_dir, bk_set)
                else:
                    self.log(f"  Config dir not found for {name}.", "err")
                    ok = False
            elif method == "bazarr_api":
                cfg_dir = self.resolve_path(app["config_paths"])
                if cfg_dir:
                    ok = self._bazarr_file_backup(app, cfg_dir, bk_set)
                else:
                    self.log(f"  Config dir not found for {name}.", "err")
                    ok = False
            elif method == "jellyfin_api":
                cfg_dir = self.resolve_path(app["config_paths"])
                if cfg_dir:
                    ok = self._jellyfin_api_backup(app, cfg_dir, bk_set)
                    if not ok:
                        self.log("  Falling back to file copy ...")
                        self.stop_app(app)
                        ok = self._file_copy_backup(app, cfg_dir, bk_set)
                        self.start_app(app)
                else:
                    ok = False
            elif method == "file_copy":
                if app.get("container"):
                    vol_path = Path(self.cfg["base_root"]) / app["volume_subpath"]
                    src = vol_path
                else:
                    src = self.resolve_path(app["config_paths"])
                if src and src.exists():
                    self.stop_app(app)
                    ok = self._file_copy_backup(app, src, bk_set)
                    self.start_app(app)
                else:
                    self.log(f"  Source not found for {name}.", "err")
                    ok = False
            else:
                ok = False
            results.append((name, "OK" if ok else "FAILED"))
        # Write manifest
        manifest = {
            "timestamp": ts,
            "machine": os.environ.get("COMPUTERNAME", "?"),
            "results": [{"app": r[0], "status": r[1]} for r in results],
        }
        (bk_set / "manifest.json").write_text(json.dumps(manifest, indent=2))
        self.log("")
        self.log("=== Backup Summary ===", "bold")
        for name, status in results:
            tag = "ok" if status == "OK" else "err"
            self.log(f"  {name:<15} {status}", tag)
        self.log(f"Saved to: {bk_set}", "ok")
        if callback:
            callback(results)

    # ---- restore ----

    def list_backups(self):
        bks = Path(self.cfg["backup_root"])
        if not bks.exists():
            return []
        sets = []
        for d in sorted(bks.iterdir(), reverse=True):
            mf = d / "manifest.json"
            if d.is_dir() and mf.exists():
                try:
                    data = json.loads(mf.read_text())
                    count = len(list(d.glob("*.zip")))
                    sets.append({"path": d, "timestamp": data["timestamp"],
                                 "machine": data.get("machine","?"), "count": count})
                except Exception:
                    pass
        return sets

    def restore_backup(self, backup_path, app_names=None):
        bk_set = Path(backup_path)
        self.log(f"=== RESTORE from {bk_set.name} ===", "bold")
        results = []
        for app in APPS:
            name = app["name"]
            if app_names and name not in app_names:
                continue
            if app.get("backup") is None:
                continue
            zip_path = bk_set / f"{name}.zip"
            if not zip_path.exists():
                self.log(f"  No archive for {name} in this set.", "warn")
                continue
            self.log(f"--- {name} ---", "bold")
            if app.get("container"):
                dest = Path(self.cfg["base_root"]) / app["volume_subpath"]
            else:
                dest = self.resolve_path(app.get("config_paths", []))
                if dest is None:
                    dest = Path(os.path.expandvars(app["config_paths"][0]))
            self.stop_app(app)
            if dest.exists():
                bak = Path(str(dest) + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                self.log(f"  Renaming existing -> {bak.name}", "warn")
                dest.rename(bak)
            try:
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(dest)
                self.log(f"  Restored {name}", "ok")
                ok = True
            except Exception as e:
                self.log(f"  Restore failed for {name}: {e}", "err")
                ok = False
            self.start_app(app)
            results.append((name, "OK" if ok else "FAILED"))
        self.log("")
        self.log("=== Restore Summary ===", "bold")
        for name, status in results:
            self.log(f"  {name:<15} {status}", "ok" if status=="OK" else "err")

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self.cfg = Config()
        self.q   = queue.Queue()
        self.ops = Ops(self.cfg, self._enqueue_log)

        self.root = tk.Tk()
        self.root.title(f"Media Stack Manager v{VERSION}")
        self.root.geometry("1050x740")
        self.root.configure(bg=C_BG)
        self.root.minsize(800, 600)

        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_log()
        self._build_statusbar()
        self._check_queue()

        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.log("WARNING: Not running as Administrator. Some operations may fail.", "warn")

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=F_MAIN, background=C_BG)
        s.configure("TNotebook", background=C_BG, borderwidth=0)
        s.configure("TNotebook.Tab", font=F_BOLD, padding=[14, 6])
        s.map("TNotebook.Tab", background=[("selected", C_ACCENT)],
              foreground=[("selected", "white")])
        s.configure("TFrame", background=C_BG)
        s.configure("Card.TFrame", background=C_CARD, relief="flat")
        s.configure("TLabel", background=C_BG)
        s.configure("Card.TLabel", background=C_CARD)
        s.configure("Accent.TButton", font=F_BOLD, foreground="white",
                    background=C_ACCENT, borderwidth=0, padding=[10, 5])
        s.map("Accent.TButton", background=[("active", "#1976d2")])
        s.configure("Small.TButton", font=F_MAIN, padding=[6, 3])
        s.configure("TEntry", fieldbackground="white", padding=4)
        s.configure("TScrollbar", background=C_BG)

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=C_ACCENT, height=52)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Media Stack Manager", font=F_TITLE,
                 bg=C_ACCENT, fg="white").pack(side="left", padx=8, pady=12)
        tk.Label(hdr, text=f"v{VERSION}", font=F_MAIN,
                 bg=C_ACCENT, fg="#90caf9").pack(side="left")

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(8,0))
        self._build_install_tab()
        self._build_backup_tab()
        self._build_settings_tab()

    # ---- Install tab ----

    def _build_install_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Install  ")

        top = ttk.Frame(outer)
        top.pack(fill="x", padx=12, pady=8)
        ttk.Label(top, text="Base folder:").pack(side="left")
        self.base_var = tk.StringVar(value=self.cfg["base_root"])
        ttk.Entry(top, textvariable=self.base_var, width=38).pack(side="left", padx=6)
        ttk.Button(top, text="Browse", style="Small.TButton",
                   command=self._browse_base).pack(side="left")
        ttk.Button(top, text="Install All", style="Accent.TButton",
                   command=self._install_all).pack(side="right")

        # Scrollable app list
        canvas_frame = ttk.Frame(outer)
        canvas_frame.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(canvas_frame, bg=C_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.install_inner = ttk.Frame(canvas)
        win = canvas.create_window((0,0), window=self.install_inner, anchor="nw")
        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win, width=canvas.winfo_width())
        self.install_inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=canvas.winfo_width()))
        self.status_vars = {}
        for app in APPS:
            self._add_app_row(self.install_inner, app)

    def _add_app_row(self, parent, app):
        name = app["name"]
        row  = tk.Frame(parent, bg=C_CARD, pady=2)
        row.pack(fill="x", padx=2, pady=3)
        row.columnconfigure(2, weight=1)
        # Color bar
        clr = {"Jellyfin":"#00a4dc","Sonarr":"#35c5f4","Radarr":"#ffc230",
               "Prowlarr":"#ff6a00","Bazarr":"#9b59b6","qBittorrent":"#2ecc71",
               "Byparr":"#e74c3c","Seer":"#1abc9c"}.get(name, C_ACCENT)
        tk.Frame(row, bg=clr, width=6).grid(row=0, column=0, rowspan=2, sticky="ns")
        tk.Label(row, text=name, font=F_BOLD, bg=C_CARD, anchor="w",
                 width=14).grid(row=0, column=1, sticky="w", padx=(8,4), pady=(6,0))
        tk.Label(row, text=app["desc"], font=F_MAIN, bg=C_CARD, fg="#555",
                 anchor="w").grid(row=1, column=1, sticky="w", padx=(8,4), pady=(0,6))
        # Method badge
        method_colors = {"winget":"#1565c0","docker":"#0288d1","browser":"#6a1b9a"}
        method = app.get("install","?")
        mc = method_colors.get(method, "#555")
        badge = tk.Label(row, text=method.upper(), bg=mc, fg="white",
                         font=("Segoe UI", 8, "bold"), padx=5, pady=1)
        badge.grid(row=0, column=2, sticky="w", padx=4, pady=(6,0))
        # Status indicator
        sv = tk.StringVar(value="?")
        self.status_vars[name] = sv
        tk.Label(row, textvariable=sv, bg=C_CARD, fg="#888",
                 font=F_MAIN).grid(row=1, column=2, sticky="w", padx=4, pady=(0,6))
        # Install button
        btn = ttk.Button(row, text="Install", style="Small.TButton",
                         command=lambda a=app: self._install_one(a))
        btn.grid(row=0, column=3, rowspan=2, padx=8, pady=6)

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
        def run():
            for app in APPS:
                self.ops.install_app(app)
        self._run_bg(run)

    # ---- Backup / Restore tab ----

    def _build_backup_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Backup & Restore  ")
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # Left: Backup
        lf = tk.LabelFrame(outer, text=" Backup ", font=F_BOLD, bg=C_BG, padx=10, pady=10)
        lf.grid(row=0, column=0, sticky="nsew", padx=(12,6), pady=12)
        lf.columnconfigure(0, weight=1)
        ttk.Label(lf, text="Creates a timestamped snapshot of every app\n"
                            "using each app's built-in backup where available.").pack(anchor="w")
        ttk.Button(lf, text="Back Up All Now", style="Accent.TButton",
                   command=self._do_backup).pack(anchor="w", pady=(12,4))
        ttk.Label(lf, text="Individual apps:").pack(anchor="w", pady=(10,2))
        for app in APPS:
            if app.get("backup") is None:
                continue
            ttk.Button(lf, text=f"  Back up {app['name']}",
                       style="Small.TButton",
                       command=lambda a=app: self._backup_one(a)).pack(anchor="w", pady=1)

        # Right: Restore
        rf = tk.LabelFrame(outer, text=" Restore ", font=F_BOLD, bg=C_BG, padx=10, pady=10)
        rf.grid(row=0, column=1, sticky="nsew", padx=(6,12), pady=12)
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(1, weight=1)
        ttk.Label(rf, text="Select a backup set to restore from:").grid(row=0, column=0, sticky="w")
        self.backup_list = tk.Listbox(rf, font=F_MONO, height=12,
                                       selectmode="single", bg="white")
        self.backup_list.grid(row=1, column=0, sticky="nsew", pady=6)
        sb = ttk.Scrollbar(rf, command=self.backup_list.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=6)
        self.backup_list.configure(yscrollcommand=sb.set)
        btn_row = ttk.Frame(rf)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(btn_row, text="Refresh List", style="Small.TButton",
                   command=self._refresh_backup_list).pack(side="left", padx=(0,6))
        ttk.Button(btn_row, text="Restore Selected", style="Accent.TButton",
                   command=self._do_restore).pack(side="left")
        self._refresh_backup_list()

    def _refresh_backup_list(self):
        self.backup_list.delete(0, "end")
        self._backup_sets = self.ops.list_backups()
        for s in self._backup_sets:
            label = f"{s['timestamp']}  [{s['count']} archives | {s['machine']}]"
            self.backup_list.insert("end", label)

    def _do_backup(self):
        def after(results):
            self.root.after(0, self._refresh_backup_list)
        self._run_bg(lambda: self.ops.backup_all(callback=after))

    def _backup_one(self, app):
        ts     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bk_set = Path(self.cfg["backup_root"]) / f"{ts}_{app['name']}"
        bk_set.mkdir(parents=True, exist_ok=True)
        def run():
            method = app.get("backup")
            if method == "arr_api":
                cfg_dir = self.ops.resolve_path(app["config_paths"])
                if cfg_dir: self.ops._arr_api_backup(app, cfg_dir, bk_set)
            elif method == "bazarr_api":
                cfg_dir = self.ops.resolve_path(app["config_paths"])
                if cfg_dir: self.ops._bazarr_file_backup(app, cfg_dir, bk_set)
            elif method == "jellyfin_api":
                cfg_dir = self.ops.resolve_path(app["config_paths"])
                if cfg_dir: self.ops._jellyfin_api_backup(app, cfg_dir, bk_set)
            elif method == "file_copy":
                if app.get("container"):
                    src = Path(self.cfg["base_root"]) / app["volume_subpath"]
                else:
                    src = self.ops.resolve_path(app["config_paths"])
                if src and src.exists():
                    self.ops.stop_app(app)
                    self.ops._file_copy_backup(app, src, bk_set)
                    self.ops.start_app(app)
            self.root.after(0, self._refresh_backup_list)
        self._run_bg(run)

    def _do_restore(self):
        sel = self.backup_list.curselection()
        if not sel:
            messagebox.showwarning("Restore", "Select a backup set from the list first.")
            return
        bk = self._backup_sets[sel[0]]
        if not messagebox.askyesno("Confirm Restore",
                f"Restore from:\n{bk['timestamp']}\n\n"
                "Existing configs will be renamed to .bak_TIMESTAMP. Continue?"):
            return
        self._run_bg(lambda: self.ops.restore_backup(bk["path"]))

    # ---- Settings tab ----

    def _build_settings_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Settings  ")
        canvas = tk.Canvas(outer, bg=C_BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        win   = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=canvas.winfo_width()))
        self._setting_vars = {}

        def section(text):
            ttk.Label(inner, text=text, font=F_BOLD,
                      foreground=C_ACCENT).grid(row=section.row, column=0, columnspan=3,
                                                 sticky="w", padx=14, pady=(14,2))
            section.row += 1
        section.row = 0

        def field(label, key, is_dir=False):
            r = section.row
            ttk.Label(inner, text=label).grid(row=r, column=0, sticky="w", padx=(14,4), pady=3)
            var = tk.StringVar(value=self.cfg[key])
            self._setting_vars[key] = var
            ttk.Entry(inner, textvariable=var, width=44).grid(row=r, column=1, sticky="ew", padx=4)
            if is_dir:
                ttk.Button(inner, text="...", width=3, style="Small.TButton",
                           command=lambda v=var: v.set(filedialog.askdirectory() or v.get())
                           ).grid(row=r, column=2, padx=(0,14))
            section.row += 1

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
        field("Byparr image",     "byparr_image")
        field("Seer image",       "seer_image")

        section("API Keys")
        field("Jellyfin API key", "jellyfin_api_key")
        ttk.Label(inner, text="Create in Jellyfin Dashboard -> Advanced -> API Keys",
                  foreground="#888").grid(row=section.row, column=1, sticky="w", pady=(0,6))
        section.row += 1

        inner.columnconfigure(1, weight=1)
        ttk.Button(inner, text="Save Settings", style="Accent.TButton",
                   command=self._save_settings).grid(
                   row=section.row, column=0, columnspan=3, pady=14, padx=14, sticky="w")

    def _save_settings(self):
        for key, var in self._setting_vars.items():
            self.cfg[key] = var.get()
        self.cfg.save()
        self.base_var.set(self.cfg["base_root"])
        self.log("Settings saved.", "ok")

    # ---- Log area ----

    def _build_log(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=(4,0))
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

    # ---- Threading / queue ----

    def log(self, msg, tag="info"):
        self._enqueue_log(msg, tag)

    def _enqueue_log(self, msg, tag="info"):
        self.q.put((msg, tag))

    def _check_queue(self):
        try:
            while True:
                msg, tag = self.q.get_nowait()
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

    def _run_bg(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def run(self):
        self.root.mainloop()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Request elevation on Windows if needed
    if sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    App().run()