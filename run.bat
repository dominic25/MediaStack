@echo off
cd /d "%~dp0"
py main.py 2>nul || python main.py 2>nul || (
    echo Python not found. Install Python 3.8+ and ensure it is on your PATH.
    pause
    exit /b 1
)
pause
