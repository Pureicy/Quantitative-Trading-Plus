@echo off
setlocal
cd /d "%~dp0"

python app_bootstrap.py --export-data exports\state

endlocal
