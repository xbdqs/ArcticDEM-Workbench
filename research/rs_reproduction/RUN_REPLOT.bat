@echo off
setlocal
cd /d "%~dp0"
echo ArcticDEM paper figure and table reproduction
echo Reuse the existing environment. No registration or data download.
python -I -X utf8 -u reproduce_paper.py %*
if errorlevel 1 goto failed
echo.
echo [COMPLETED] Read the figures, tables and reproduction record in the output directory.
pause
exit /b 0
:failed
echo.
echo [FAILED] Keep the console output. Frozen scientific inputs were not modified.
pause
exit /b 1
