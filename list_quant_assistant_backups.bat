@echo off
setlocal
cd /d "%~dp0"

python app_bootstrap.py --list-backups

endlocal
