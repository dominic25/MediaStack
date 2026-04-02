#!/usr/bin/env python3
"""
Media Stack Manager - Entry point.
Requests admin elevation on Windows, then launches the GUI.
"""
import sys
import ctypes

from gui import App


if __name__ == "__main__":
    if sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    App().run()
