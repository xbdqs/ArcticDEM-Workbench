@echo off
setlocal
cd /d "%~dp0"
echo ArcticDEM Workbench 0.11.1 public-source acceptance
echo Reuse a working Python 3.12 environment. No installation or data download.
echo Existing research data and runs are preserved.
python -I -X utf8 -u tools\verify_public_release.py --gui %*
if errorlevel 1 goto failed
echo.
echo [COMPLETED] Keep or upload the UPLOAD_PUBLIC_ACCEPTANCE ZIP printed above.
pause
exit /b 0
:failed
echo.
echo [FAILED] Keep the console output and verification ZIP. Do not rebuild the environment.
pause
exit /b 1
