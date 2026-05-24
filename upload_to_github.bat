@echo off
setlocal
cd /d "%~dp0"
python scripts\upload_to_github.py
echo.
pause
