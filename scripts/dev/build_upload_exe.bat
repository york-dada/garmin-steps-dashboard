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
rmdir /S /Q build 2>nul
rmdir /S /Q dist 2>nul
del /Q GarminUploadToGitHub.spec 2>nul
echo.
pause
