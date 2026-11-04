@echo off
setlocal
cd /d "%~dp0"

python app_bootstrap.py --backup-data

endlocal
