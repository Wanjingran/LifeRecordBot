@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.11+ first.
  echo Download: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
python bot.py >> "%~dp0bot.log" 2>&1
