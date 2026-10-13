@echo off
setlocal
cd /d "%~dp0"
where conda >nul 2>nul
if errorlevel 1 goto missing
call conda activate arcticdem_dod
if errorlevel 1 goto failed
if not exist "%CONDA_PREFIX%\python.exe" goto failed
echo ArcticDEM Workbench 0.11.1 GUI
echo Reuse the existing environment. No installation or data download.
"%CONDA_PREFIX%\python.exe" -X utf8 -u "%~dp0tools\start_gui.py"
if errorlevel 1 goto failed
echo.
echo [COMPLETED] GUI closed.
exit /b 0
:failed
echo.
echo [FAILED] Keep the console and upload any ZIP printed above.
echo Do not reinstall or rebuild the environment.
pause
exit /b 1
:missing
echo [ERROR] Open Anaconda Prompt, enter this folder, then run RUN_02_START_GUI.bat.
pause
exit /b 1
