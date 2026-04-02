"""
Backend operations for Media Stack Manager.
Handles install, configure, backup, and restore of all apps.
"""
import subprocess, os, json, shutil, zipfile, tempfile, time, configparser
import urllib.request
from pathlib import Path
from datetime import datetime

from constants import APPS
from config import Config


class Ops:
    def __init__(self, config: Config, log_fn):
        self.cfg    = config
        self.log_fn = log_fn

    def log(self, msg, tag="info"):
        self.log_fn(msg, tag)

    def resolve_path(self, candidates):
        for c in candidates:
            p = Path(os.path.expandvars(c))
            if p.exists():
                return p
        return None

    def find_exe(self, app):
        for d in app.get("common_dirs", []):
            for exe in app.get("exe_candidates", []):
                p = Path(d) / exe
                if p.exists():
                    return p
        for pf in [r"C:\Program Files", r"C:\Program Files (x86)"]:
            for exe in app.get("exe_candidates", []):
                p = Path(pf) / app["name"] / exe
                if p.exists():
                    return p
        return None

    def run(self, args, **kwargs):
        return subprocess.run(args, capture_output=True, text=True, **kwargs)

    def run_stream(self, args, **kwargs):
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

    # --- stop / start ---

    def stop_app(self, app):
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
        exe = self.find_exe(app)
        if exe:
            self.log(f"  Launching exe: {exe}", "ok")
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
        else:
            self.log(f"  Could not find {app['name']} exe - relaunch manually.", "warn")

    def check_app_status(self, app):
        """Returns (label, color_key)."""
        if app.get("container"):
            r = self.run(["docker", "ps", "-q", "--filter", f"name=^/{app['container']}$"])
            if r.stdout.strip(): return ("Running", "status_ok")
            r2 = self.run(["docker", "ps", "-a", "-q", "--filter", f"name=^/{app['container']}$"])
            return ("Stopped", "status_warn") if r2.stdout.strip() else ("Not installed", "status_dim")
        svc = app.get("service")
        if svc:
            r = self.run(["sc", "query", svc])
            if "RUNNING" in r.stdout: return ("Running", "status_ok")
            if "STOPPED" in r.stdout: return ("Stopped", "status_warn")
        if self.find_exe(app):
            return ("Installed", "status_info")
        return ("Not installed", "status_dim")

    # --- install ---

    def install_app(self, app):
        name   = app["name"]
        method = app.get("install")
        self.log(f"=== Installing {name} ===", "bold")
        if method == "winget":
            rc = self.run_stream([
                "winget", "install", "--id", app["winget_id"], "-e",
                "--accept-package-agreements", "--accept-source-agreements"
            ])
            if rc == 0: self.log(f"  {name} installed.", "ok")
            else:       self.log(f"  winget returned {rc} for {name}.", "warn")
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
        r = self.run(["docker", "ps", "-a", "-q", "--filter", f"name=^/{container}$"])
        if r.stdout.strip():
            self.log(f"  Removing existing '{container}' container ...", "warn")
            self.run(["docker", "stop", container])
            self.run(["docker", "rm",   container])
        r = self.run(["docker", "ps", "-q", "--filter", f"publish={port_host}"])
        for cid in r.stdout.strip().splitlines():
            cid = cid.strip()
            if not cid: continue
            nr    = self.run(["docker", "inspect", "--format", "{{.Name}}", cid])
            cname = nr.stdout.strip().lstrip("/")
            self.log(f"  Port {port_host} already used by '{cname}' - removing it ...", "warn")
            self.run(["docker", "stop", cid])
            self.run(["docker", "rm",   cid])
        self.log(f"  Pulling {image} ...")
        self.run_stream(["docker", "pull", image])
        inner = "8191" if name == "Byparr" else port_host
        cmd = ["docker", "run", "-d", "--name", container, "--restart", "unless-stopped"]
        if name == "Seer": cmd += ["--init"]
        cmd += ["-p", f"{port_host}:{inner}", "-v", f"{vol_path}:/app/config", image]
        r = self.run(cmd)
        if r.returncode == 0: self.log(f"  {name} started on port {port_host}.", "ok")
        else:                 self.log(f"  docker run failed: {r.stderr.strip()}", "err")

    # --- auto-configure helpers ---

    def _read_arr_xml(self, config_dir):
        """Parse config.xml -> (api_key, port). Returns (None, None) on failure."""
        import xml.etree.ElementTree as ET
        xml_path = Path(config_dir) / "config.xml"
        if not xml_path.exists():
            return None, None
        try:
            root = ET.parse(xml_path).getroot()
            return root.findtext("ApiKey"), root.findtext("Port")
        except Exception:
            return None, None

    def _wait_for_api(self, url, headers, name="", timeout=90):
        """Poll url every 4 s until it returns 200 or timeout expires."""
        self.log(f"  Waiting for {name} API to be ready ...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.http_get(url, headers)
                self.log(f"  {name} API is up.", "ok")
                return True
            except Exception:
                time.sleep(4)
        self.log(f"  {name} API did not respond within {timeout}s.", "err")
        return False

    def _wait_for_config_xml(self, app, timeout=90):
        """Wait for an *arr app to generate its config.xml on first start."""
        cfg_dir = self.resolve_path(app.get("config_paths", []))
        if not cfg_dir:
            self.log(f"  Config dir not found for {app['name']}.", "err")
            return None, None
        xml_path = cfg_dir / "config.xml"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if xml_path.exists():
                key, port = self._read_arr_xml(cfg_dir)
                if key:
                    return key, port
            self.log(f"  Waiting for {app['name']} config.xml ...")
            time.sleep(5)
        self.log(f"  {app['name']} config.xml not ready after {timeout}s.", "err")
        return None, None

    def _configure_arr_app(self, app, root_folder, qbit_category, qbit_port, api_key, port):
        """Set root folder and qBittorrent download client on a Sonarr/Radarr instance."""
        name    = app["name"]
        version = app["arr_version"]
        base    = f"http://localhost:{port}/api/{version}"
        hdrs    = {"X-Api-Key": api_key, "Content-Type": "application/json"}

        if not self._wait_for_api(f"{base}/system/status", hdrs, name=name):
            return False

        # Root folder
        try:
            folders  = self.http_get(f"{base}/rootfolder", hdrs)
            existing = [f["path"].lower() for f in folders]
            if root_folder.lower() not in existing:
                self.http_post(f"{base}/rootfolder", hdrs, json.dumps({"path": root_folder}))
                self.log(f"  Root folder added: {root_folder}", "ok")
            else:
                self.log(f"  Root folder already set.", "ok")
        except Exception as e:
            self.log(f"  Root folder config failed: {e}", "warn")

        # qBittorrent download client
        try:
            clients  = self.http_get(f"{base}/downloadclient", hdrs)
            has_qbit = any(c.get("implementation") == "QBittorrent" for c in clients)
            if not has_qbit:
                cat_key = "tvCategory" if name == "Sonarr" else "movieCategory"
                body = {
                    "enable": True, "protocol": "torrent", "priority": 1,
                    "name": "qBittorrent",
                    "fields": [
                        {"name": "host",      "value": "localhost"},
                        {"name": "port",      "value": int(qbit_port)},
                        {"name": "useSsl",    "value": False},
                        {"name": "urlBase",   "value": ""},
                        {"name": "username",  "value": ""},
                        {"name": "password",  "value": ""},
                        {"name": cat_key,     "value": qbit_category},
                        {"name": "initialState",     "value": 0},
                        {"name": "sequentialOrder",  "value": False},
                        {"name": "firstAndLast",     "value": False},
                    ],
                    "implementationName": "qBittorrent",
                    "implementation": "QBittorrent",
                    "configContract": "QBittorrentSettings",
                    "tags": []
                }
                self.http_post(f"{base}/downloadclient", hdrs, json.dumps(body))
                self.log(f"  qBittorrent download client added.", "ok")
            else:
                self.log(f"  qBittorrent already configured.", "ok")
        except Exception as e:
            self.log(f"  Download client config failed: {e}", "warn")

        return True

    def configure_qbittorrent(self):
        """Write qBittorrent.conf with WebUI settings and download path."""
        candidates = [r"%APPDATA%\qBittorrent", r"C:\ProgramData\qBittorrent"]
        cfg_dir = self.resolve_path(candidates)
        if cfg_dir is None:
            cfg_dir = Path(os.path.expandvars(r"%APPDATA%\qBittorrent"))
            cfg_dir.mkdir(parents=True, exist_ok=True)

        conf_path   = cfg_dir / "qBittorrent.conf"
        port        = self.cfg["qb_port"]
        dl_root     = self.cfg["downloads_root"].replace("\\", "/")
        incomplete  = (Path(self.cfg["downloads_root"]) / "incomplete").as_posix()

        cp = configparser.ConfigParser(strict=False)
        cp.optionxform = str
        if conf_path.exists():
            cp.read(conf_path, encoding="utf-8")

        for sec in ("BitTorrent", "LegalNotice", "Preferences"):
            if not cp.has_section(sec):
                cp.add_section(sec)

        cp.set("BitTorrent",  "Session\\DefaultSavePath",  dl_root + "/")
        cp.set("BitTorrent",  "Session\\TempPath",          incomplete + "/")
        cp.set("LegalNotice", "Accepted",                   "true")
        cp.set("Preferences", "WebUI\\Enabled",             "true")
        cp.set("Preferences", "WebUI\\Port",                str(port))
        cp.set("Preferences", "WebUI\\LocalHostAuth",       "false")

        with open(conf_path, "w", encoding="utf-8") as f:
            cp.write(f)

        Path(self.cfg["downloads_root"]).mkdir(parents=True, exist_ok=True)
        Path(incomplete).mkdir(parents=True, exist_ok=True)
        self.log(f"  Written: {conf_path}", "ok")
        return True

    def configure_prowlarr(self, sonarr_key, sonarr_port, radarr_key, radarr_port,
                           prowlarr_key, prowlarr_port):
        """Connect Prowlarr to Sonarr and Radarr."""
        base = f"http://localhost:{prowlarr_port}/api/v1"
        hdrs = {"X-Api-Key": prowlarr_key, "Content-Type": "application/json"}

        if not self._wait_for_api(f"{base}/system/status", hdrs, name="Prowlarr"):
            return False

        try:
            apps     = self.http_get(f"{base}/applications", hdrs)
            existing = {a.get("implementation") for a in apps}
            pl_url   = f"http://localhost:{prowlarr_port}"

            for impl, name, api_key, port, cats in [
                ("Sonarr", "Sonarr", sonarr_key, sonarr_port,
                 [5000, 5010, 5020, 5030, 5040, 5045, 5050]),
                ("Radarr", "Radarr", radarr_key, radarr_port,
                 [2000, 2010, 2020, 2030, 2040, 2045, 2050]),
            ]:
                if impl in existing:
                    self.log(f"  Prowlarr -> {name} already linked.", "ok")
                    continue
                body = {
                    "syncLevel": "fullSync", "name": name,
                    "fields": [
                        {"name": "prowlarrUrl",    "value": pl_url},
                        {"name": "baseUrl",        "value": f"http://localhost:{port}"},
                        {"name": "apiKey",         "value": api_key},
                        {"name": "syncCategories", "value": cats},
                    ],
                    "implementationName": impl,
                    "implementation":     impl,
                    "configContract":     f"{impl}Settings",
                    "tags": []
                }
                self.http_post(f"{base}/applications", hdrs, json.dumps(body))
                self.log(f"  Prowlarr -> {name} linked.", "ok")
        except Exception as e:
            self.log(f"  Prowlarr link failed: {e}", "warn")

        return True

    def configure_bazarr(self, sonarr_key, sonarr_port, radarr_key, radarr_port):
        """Write Bazarr config.ini with Sonarr + Radarr connection details."""
        cfg_dir = self.resolve_path([r"C:\ProgramData\Bazarr", r"%APPDATA%\Bazarr"])
        if cfg_dir is None:
            cfg_dir = Path(os.path.expandvars(r"C:\ProgramData\Bazarr"))
        config_sub = cfg_dir / "config"
        config_sub.mkdir(parents=True, exist_ok=True)
        ini_path = config_sub / "config.ini"

        cp = configparser.ConfigParser(strict=False)
        cp.optionxform = str
        if ini_path.exists():
            cp.read(ini_path, encoding="utf-8")

        def ensure(section, items):
            if not cp.has_section(section):
                cp.add_section(section)
            for k, v in items.items():
                cp.set(section, k, str(v))

        ensure("sonarr", {
            "enabled": "True", "apikey": sonarr_key or "",
            "host": "localhost", "port": str(sonarr_port), "ssl": "False",
        })
        ensure("radarr", {
            "enabled": "True", "apikey": radarr_key or "",
            "host": "localhost", "port": str(radarr_port), "ssl": "False",
        })

        with open(ini_path, "w", encoding="utf-8") as f:
            cp.write(f)
        self.log(f"  Written: {ini_path}", "ok")
        return True

    def configure_jellyfin(self):
        """Add Movies and TV libraries to Jellyfin via API."""
        port    = self.cfg["jellyfin_port"]
        api_key = self.cfg["jellyfin_api_key"]
        if not api_key:
            self.log("  No Jellyfin API key set in Settings. Skipping library setup.", "warn")
            return False
        base = f"http://localhost:{port}"
        hdrs = {"X-MediaBrowser-Token": api_key, "Content-Type": "application/json"}

        if not self._wait_for_api(f"{base}/System/Info", hdrs, name="Jellyfin"):
            return False

        media_root = Path(self.cfg["media_root"])
        libs = [
            ("Movies",   str(media_root / "Movies"), "movies"),
            ("TV Shows", str(media_root / "TV"),      "tvshows"),
        ]

        try:
            folders = self.http_get(f"{base}/Library/VirtualFolders", hdrs)
            existing_paths = set()
            for f in folders:
                for loc in f.get("Locations", []):
                    existing_paths.add(loc.lower())

            for lib_name, path, col_type in libs:
                Path(path).mkdir(parents=True, exist_ok=True)
                if path.lower() in existing_paths:
                    self.log(f"  Jellyfin library '{lib_name}' already exists.", "ok")
                    continue
                body = {
                    "Name": lib_name,
                    "Paths": [path],
                    "PathInfos": [{"Path": path}],
                    "EnableRealTimeMonitor": True,
                }
                url = (f"{base}/Library/VirtualFolders"
                       f"?collectionType={col_type}&refreshLibrary=false")
                self.http_post(url, hdrs, json.dumps(body))
                self.log(f"  Jellyfin library added: {lib_name} -> {path}", "ok")
        except Exception as e:
            self.log(f"  Jellyfin library config failed: {e}", "warn")

        return True

    def configure_all(self):
        """Orchestrate post-install configuration for the full stack."""
        self.log("=== Auto-Configure ===", "bold")

        for key in ("media_root", "downloads_root"):
            Path(self.cfg[key]).mkdir(parents=True, exist_ok=True)
        for sub in ("Movies", "TV"):
            (Path(self.cfg["media_root"]) / sub).mkdir(parents=True, exist_ok=True)

        self.log("")
        self.log("--- qBittorrent ---", "bold")
        self.configure_qbittorrent()

        arr_info = {}
        arr_apps = {a["name"]: a for a in APPS if a.get("arr_version")}
        for name, app in arr_apps.items():
            self.log("")
            self.log(f"--- {name} (reading config) ---", "bold")
            key, port = self._wait_for_config_xml(app)
            if key:
                arr_info[name] = {"key": key, "port": port, "app": app}
                self.log(f"  {name} API key found.", "ok")
            else:
                self.log(f"  Skipping {name} configuration.", "warn")

        sonarr   = arr_info.get("Sonarr",   {})
        radarr   = arr_info.get("Radarr",   {})
        prowlarr = arr_info.get("Prowlarr", {})

        if sonarr:
            self.log("")
            self.log("--- Sonarr ---", "bold")
            tv_path = str(Path(self.cfg["media_root"]) / "TV")
            self._configure_arr_app(
                sonarr["app"], tv_path, "sonarr",
                self.cfg["sonarr_port"], sonarr["key"], sonarr["port"])

        if radarr:
            self.log("")
            self.log("--- Radarr ---", "bold")
            movies_path = str(Path(self.cfg["media_root"]) / "Movies")
            self._configure_arr_app(
                radarr["app"], movies_path, "radarr",
                self.cfg["radarr_port"], radarr["key"], radarr["port"])

        if prowlarr and sonarr and radarr:
            self.log("")
            self.log("--- Prowlarr ---", "bold")
            self.configure_prowlarr(
                sonarr["key"],   sonarr["port"],
                radarr["key"],   radarr["port"],
                prowlarr["key"], prowlarr["port"])

        if sonarr or radarr:
            self.log("")
            self.log("--- Bazarr ---", "bold")
            self.configure_bazarr(
                sonarr.get("key", ""),  sonarr.get("port",  self.cfg["sonarr_port"]),
                radarr.get("key", ""),  radarr.get("port",  self.cfg["radarr_port"]))

        self.log("")
        self.log("--- Jellyfin ---", "bold")
        self.configure_jellyfin()

        self.log("")
        self.log("=== Auto-Configure complete ===", "bold")

    # --- backup helpers ---

    def _arr_api_backup(self, app, config_dir, backup_set):
        port    = self.cfg[app["port_key"]]
        version = app["arr_version"]
        name    = app["name"]
        try:
            import xml.etree.ElementTree as ET
            xml_path = config_dir / "config.xml"
            if not xml_path.exists():
                self.log(f"  config.xml not found in {config_dir}", "err")
                return False
            root    = ET.parse(xml_path).getroot()
            api_key = root.findtext("ApiKey")
            if not api_key:
                self.log(f"  No API key found in {xml_path}", "err")
                return False
            port    = root.findtext("Port") or port
            base    = f"http://localhost:{port}/api/{version}"
            hdrs    = {"X-Api-Key": api_key, "Content-Type": "application/json"}
            self.log(f"  Triggering {name} API backup on port {port} ...")
            result = self.http_post(f"{base}/command", hdrs, '{"name":"Backup"}')
            cmd_id = result["id"]
            status = {"status": "unknown"}
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(3)
                status = self.http_get(f"{base}/command/{cmd_id}", hdrs)
                if status["status"] in ("completed", "failed"): break
            if status["status"] != "completed":
                self.log(f"  {name} backup status: {status['status']}", "err")
                return False
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
        items_to_backup = ["config", "db"]
        try:
            self.log("  Starting file-based backup for Bazarr...")
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for folder_name in items_to_backup:
                    source_path = config_dir / folder_name
                    if not source_path.exists():
                        self.log(f"    Warning: {folder_name} not found, skipping.", "warn")
                        continue
                    self.log(f"    Archiving {folder_name}...")
                    for file in source_path.rglob("*"):
                        if file.is_file():
                            try:
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
            hdrs = {"X-MediaBrowser-Token": api_key, "Content-Type": "application/json"}
            payload = {"Database": True, "Metadata": True, "Subtitles": True, "Trickplay": False}
            self.http_post(f"http://localhost:{port}/Backup/Create", hdrs, json.dumps(payload), timeout=300)
            bk_dir = Path(config_dir) / "data" / "backups"
            zips   = sorted(bk_dir.glob("**/*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not zips:
                self.log("  No backup zip found. Falling back to file copy.", "warn")
                return False
            dest = Path(backup_set) / "Jellyfin.zip"
            shutil.copy2(zips[0], dest)
            mb = round(dest.stat().st_size / 1048576, 2)
            self.log(f"  OK - {zips[0].name} -> Jellyfin.zip ({mb} MB)", "ok")
            return True
        except Exception as e:
            self.log(f"  Jellyfin API backup failed: {e} - falling back to file copy.", "warn")
            return False

    def _file_copy_backup(self, app, src_dir, backup_set):
        name    = app["name"]
        tmp     = Path(tempfile.mkdtemp(prefix=f"mstack_{name}_"))
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
                            if attempt < 2: time.sleep(1)
                            else: skipped.append(str(rel))
            if skipped:
                self.log(f"  Skipped {len(skipped)} locked file(s): {skipped[:3]}", "warn")
            dest  = Path(backup_set) / f"{name}.zip"
            files = list(tmp.rglob("*"))
            if not files:
                self.log(f"  Nothing to zip for {name}.", "warn")
                return False
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    if f.is_file(): zf.write(f, f.relative_to(tmp))
            mb = round(dest.stat().st_size / 1048576, 2)
            self.log(f"  OK - {name}.zip ({mb} MB)", "ok")
            return True
        except Exception as e:
            self.log(f"  File copy backup failed for {name}: {e}", "err")
            return False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def backup_all(self, callback=None):
        ts     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bks    = Path(self.cfg["backup_root"])
        bks.mkdir(parents=True, exist_ok=True)
        bk_set = bks / ts
        bk_set.mkdir(exist_ok=True)
        self.log(f"=== BACKUP -> {bk_set} ===", "bold")
        results = []
        for app in APPS:
            if app.get("backup") is None: continue
            name   = app["name"]
            method = app["backup"]
            self.log("")
            self.log(f"--- {name} ---", "bold")
            if method == "arr_api":
                cfg_dir = self.resolve_path(app["config_paths"])
                ok = self._arr_api_backup(app, cfg_dir, bk_set) if cfg_dir else False
                if not cfg_dir: self.log(f"  Config not found for {name}.", "err")
            elif method == "bazarr_api":
                cfg_dir = self.resolve_path(app["config_paths"])
                ok = self._bazarr_file_backup(app, cfg_dir, bk_set) if cfg_dir else False
                if not cfg_dir: self.log(f"  Config not found for {name}.", "err")
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
                    src = Path(self.cfg["base_root"]) / app["volume_subpath"]
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
        manifest = {
            "timestamp": ts, "machine": os.environ.get("COMPUTERNAME", "?"),
            "results": [{"app": r[0], "status": r[1]} for r in results],
        }
        (bk_set / "manifest.json").write_text(json.dumps(manifest, indent=2))
        self.log("")
        self.log("=== Backup Summary ===", "bold")
        for name, status in results:
            self.log(f"  {name:<15} {status}", "ok" if status == "OK" else "err")
        self.log(f"Saved to: {bk_set}", "ok")
        if callback: callback(results)

    def list_backups(self):
        bks = Path(self.cfg["backup_root"])
        if not bks.exists(): return []
        sets = []
        for d in sorted(bks.iterdir(), reverse=True):
            mf = d / "manifest.json"
            if d.is_dir() and mf.exists():
                try:
                    data  = json.loads(mf.read_text())
                    count = len(list(d.glob("*.zip")))
                    sets.append({"path": d, "timestamp": data["timestamp"],
                                 "machine": data.get("machine", "?"), "count": count})
                except Exception:
                    pass
        return sets

    def restore_backup(self, backup_path, app_names=None):
        bk_set = Path(backup_path)
        self.log(f"=== RESTORE from {bk_set.name} ===", "bold")
        results = []
        for app in APPS:
            name = app["name"]
            if app_names and name not in app_names: continue
            if app.get("backup") is None: continue
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
                try:
                    dest.rename(bak)
                except Exception as e:
                    self.log(f"  Failed to rename {dest}: {e}", "err")
                    self.start_app(app)
                    results.append((name, "FAILED"))
                    continue
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
            self.log(f"  {name:<15} {status}", "ok" if status == "OK" else "err")
