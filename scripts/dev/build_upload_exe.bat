@echo off
setlocal
cd /d "%~dp0..\.."
python -m PyInstaller --onefile --name GarminUploadToGitHub scripts\upload_to_github.py
if errorlevel 1 (
  echo.
  echo PyInstaller is not installed yet.
  echo Run: python -m pip install pyinstaller
  echo Then run this file again.
  echo.
  pause
  exit /b 1
)
copy /Y dist\GarminUploadToGitHub.exe GarminUploadToGitHub.exe >nul
echo Updated GarminUploadToGitHub.exe in the project root.
echo.
pause
