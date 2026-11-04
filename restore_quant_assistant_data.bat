@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: restore_quant_assistant_data.bat data\backups\YYYY-MM-DD\backup-HHMMSS
  exit /b 1
)

python app_bootstrap.py --restore-data "%~1"

endlocal
