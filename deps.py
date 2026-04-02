"""
Environment and dependency checks for Media Stack Manager (Windows).
"""
import ctypes
import os
import shutil
import subprocess
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def check_environment():
    """
    Returns a dict of checks for UI (dashboard / onboarding).
    """
    out = {
        "winget": shutil.which("winget") is not None,
        "docker_cli": shutil.which("docker") is not None,
        "docker_daemon": False,
        "admin": is_admin(),
        "disk_free_gb": None,
    }
    if out["docker_cli"]:
        try:
            kw = {"capture_output": True, "text": True, "timeout": 12}
            if os.name == "nt":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(["docker", "info"], **kw)
            out["docker_daemon"] = r.returncode == 0
        except Exception:
            out["docker_daemon"] = False
    try:
        vol = Path(os.environ.get("SystemDrive", "C:") + "\\")
        free = shutil.disk_usage(vol).free / (1024**3)
        out["disk_free_gb"] = round(free, 1)
    except Exception:
        pass
    return out


def app_memory_mb(app):
    """
    Best-effort RSS (MB) for matching process name(s). Requires psutil.
    Returns float MB or None if unknown.
    """
    if psutil is None:
        return None
    proc = app.get("process")
    if not proc:
        return None
    needle = proc.lower()
    rss = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (p.info.get("name") or "").lower()
            if needle in name or name.startswith(needle):
                mi = p.info.get("memory_info")
                if mi:
                    rss += mi.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    if rss <= 0:
        return None
    return round(rss / (1024 * 1024), 1)
