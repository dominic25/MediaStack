"""
Configuration persistence for Media Stack Manager.
"""
import json, sys
from constants import CONF_FILE, DEFAULTS


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
