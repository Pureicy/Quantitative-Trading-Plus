@echo off
setlocal
cd /d "%~dp0"

python app_bootstrap.py --export-latest-summary exports\latest-summary.txt

endlocal
