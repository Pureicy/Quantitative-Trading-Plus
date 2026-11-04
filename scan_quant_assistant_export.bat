@echo off
setlocal
cd /d "%~dp0"

python app_bootstrap.py --scan --top-n 10 --export-csv exports\latest-scan.csv

endlocal
