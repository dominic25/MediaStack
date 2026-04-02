"""
Configuration persistence for Media Stack Manager.
"""
import json, os, sys
from pathlib import Path

from constants import CONF_FILE, DEFAULTS, CONFIG_PORT_KEYS, CONFIG_FOLDER_KEYS


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load_error = None
        self.load()

    def load(self):
        if CONF_FILE.exists():
            try:
                saved = json.loads(CONF_FILE.read_text(encoding="utf-8"))
                self.data.update(saved)
            except Exception as e:
                self.load_error = str(e)
                print(f"Warning: failed to load {CONF_FILE}: {e}", file=sys.stderr)

    def save(self):
        CONF_FILE.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def __getitem__(self, k): return self.data.get(k, "")
    def __setitem__(self, k, v): self.data[k] = v
    def get(self, k, d=""): return self.data.get(k, d)

    def validate(self):
        """
        Return a list of human-readable validation errors (empty if OK).
        """
        errors = []
        seen_ports = {}
        for key in CONFIG_PORT_KEYS:
            val = str(self.data.get(key, "")).strip()
            if not val.isdigit():
                errors.append(f"{key}: must be a whole number.")
                continue
            n = int(val)
            if not (1 <= n <= 65535):
                errors.append(f"{key}: must be between 1 and 65535.")
                continue
            if n in seen_ports:
                errors.append(
                    f"Port {n} is used by both {seen_ports[n]} and {key}."
                )
            else:
                seen_ports[n] = key

        for key in CONFIG_FOLDER_KEYS:
            raw = self.data.get(key, "")
            if not raw or not str(raw).strip():
                errors.append(f"{key}: cannot be empty.")
                continue
            try:
                p = Path(os.path.expandvars(str(raw).strip()))
            except Exception:
                errors.append(f"{key}: invalid path.")
                continue
            if not p.exists():
                errors.append(f"{key}: path does not exist: {p}")

        pi = str(self.data.get("poll_interval_seconds", "45")).strip()
        if not pi.isdigit() or not (15 <= int(pi) <= 3600):
            errors.append("poll_interval_seconds: must be a number from 15 to 3600.")

        for qh in ("quiet_hours_start", "quiet_hours_end"):
            raw = str(self.data.get(qh, "00:00")).strip()
            parts = raw.split(":")
            if len(parts) != 2:
                errors.append(f"{qh}: use HH:MM (24h), e.g. 22:00.")
                continue
            try:
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError()
            except Exception:
                errors.append(f"{qh}: invalid time (use 00:00–23:59).")

        return errors
