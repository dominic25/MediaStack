"""
Configuration persistence for Media Stack Manager.
"""
import json
from constants import CONF_FILE, DEFAULTS


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
