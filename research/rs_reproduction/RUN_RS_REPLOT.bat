@echo off
setlocal
cd /d "%~dp0"
echo Remote Sensing manuscript figures and tables
echo Reuse the active environment. No installation, download or DEM fitting.
python -X utf8 -u reproduce_rs.py
if errorlevel 1 (
  echo [FAILED] Keep this console output. Do not rebuild the environment.
  pause
  exit /b 1
)
echo [COMPLETED] New figures, tables and verification record were saved under output.
pause
