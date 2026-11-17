@echo off
setlocal
python scripts\figure_06.py || exit /b 1
python scripts\table_08.py || exit /b 1
python scripts\table_09.py || exit /b 1
echo Public-subset reproduction PASSED.
