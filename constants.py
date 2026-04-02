"""
Shared constants for Media Stack Manager.
"""
from pathlib import Path

VERSION   = "1.3"
CONF_FILE = Path(__file__).with_name("media-stack-config.json")

# Accent and log colors are fixed across themes
C_ACCENT   = "#1565c0"
C_LOG_BG   = "#1e1e1e"
C_LOG_FG   = "#d4d4d4"
C_LOG_OK   = "#4ec9b0"
C_LOG_WRN  = "#ce9178"
C_LOG_ERR  = "#f48771"
F_MAIN     = ("Segoe UI", 10)
F_BOLD     = ("Segoe UI", 10, "bold")
F_TITLE    = ("Segoe UI", 13, "bold")
F_MONO     = ("Consolas", 9)

THEMES = {
    "light": {
        "bg":         "#f5f5f5",
        "card":       "#ffffff",
        "fg":         "#111111",
        "fg_dim":     "#555555",
        "entry_bg":   "#ffffff",
        "listbox_bg": "#ffffff",
        "listbox_fg": "#111111",
        "section_fg": "#1565c0",
        "btn_bg":     "#e0e0e0",
        "btn_fg":     "#111111",
        "lf_bg":      "#f5f5f5",
        "lf_fg":      "#333333",
        "toggle_lbl": "Dark mode",
        "status_ok":  "#2e7d32",
        "status_warn":"#b71c1c",
        "status_info":"#1565c0",
        "status_dim": "#888888",
        "tooltip_bg":   "#fffde7",
        "tooltip_fg":   "#111111",
        "tooltip_border": "#c5c5c5",
    },
    "dark": {
        "bg":         "#1e1e2e",
        "card":       "#2a2a3e",
        "fg":         "#cdd6f4",
        "fg_dim":     "#a6adc8",
        "entry_bg":   "#313244",
        "listbox_bg": "#2a2a3e",
        "listbox_fg": "#cdd6f4",
        "section_fg": "#89b4fa",
        "btn_bg":     "#45475a",
        "btn_fg":     "#cdd6f4",
        "lf_bg":      "#1e1e2e",
        "lf_fg":      "#a6adc8",
        "toggle_lbl": "Light mode",
        "status_ok":  "#a6e3a1",
        "status_warn":"#f38ba8",
        "status_info":"#89b4fa",
        "status_dim": "#6c7086",
        "tooltip_bg":   "#313244",
        "tooltip_fg":   "#cdd6f4",
        "tooltip_border": "#45475a",
    },
}

HELP_FAQ = """
FREQUENTLY ASKED QUESTIONS

What is Media Stack Manager?
  A Windows helper to install, configure, back up, and restore common media apps
  (Jellyfin, *arr, qBittorrent, Docker helpers) from one place.

Why run as Administrator?
  Starting/stopping Windows services and some installers expect elevation. The app
  relaunches elevated automatically when possible.

What does Auto-Configure do?
  Writes paths and client links (qBittorrent, Sonarr/Radarr, Prowlarr, Bazarr) and
  adds Jellyfin libraries if an API key is set in Settings. It does not wipe existing
  settings.

Where is the config file?
  media-stack-config.json next to the application. Back it up before experiments.

Jellyfin libraries need an API key
  Dashboard → Advanced → API Keys. Paste the key in Settings for Auto-Configure.

Docker apps (Byparr, Seer)
  Require Docker Desktop (or Engine) running. Install Docker and ensure `docker info` works.

Backups
  Use Backup & Restore. Restores rename existing folders to .bak_TIMESTAMP first.

Dashboard
  Double-click an app card to open its local web UI when the app is installed.
  Adjust automatic refresh under Settings → Status refresh (interval and quiet hours).
  Export or import the full JSON config under Settings → Settings file.

Long operations
  Install All, Uninstall All, and Auto-Configure show step progress above the log.

Need more help?
  Jellyfin: https://jellyfin.org/docs/
  Sonarr / Radarr / Prowlarr: see each project's wiki.
"""

APPS = [
    {
        "name": "Jellyfin", "desc": "Media server",
        "install": "winget", "winget_id": "Jellyfin.Server",
        "url": "https://jellyfin.org/downloads/windows/server",
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

CONFIG_PORT_KEYS = (
    "jellyfin_port", "sonarr_port", "radarr_port", "bazarr_port",
    "prowlarr_port", "qb_port", "byparr_port", "seer_port",
)
CONFIG_FOLDER_KEYS = ("base_root", "media_root", "downloads_root", "backup_root")

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
    "theme":           "light",
    "onboarding_complete": False,
    "auto_refresh_enabled": True,
    "poll_interval_seconds": 45,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "checklist_folders_saved": False,
    "checklist_deps_reviewed": False,
    "checklist_apps_installed": False,
    "checklist_auto_configure_done": False,
    "checklist_jellyfin_api": False,
}
