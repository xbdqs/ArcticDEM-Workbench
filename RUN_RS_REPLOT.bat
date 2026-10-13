@echo off
setlocal
cd /d "%~dp0"
python -I -X utf8 -u tools\run_rs_replot.py %*
if errorlevel 1 goto failed
echo [COMPLETED] Figures and tables regenerated. Registration was not repeated.
pause
exit /b 0
:failed
echo [FAILED] Keep console output. Do not rebuild the environment.
pause
exit /b 1
