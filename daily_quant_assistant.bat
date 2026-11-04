@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Current local state
python app_bootstrap.py --state-summary
if errorlevel 1 goto :fail
echo.

echo [2/4] Scan market and export latest top candidates
python app_bootstrap.py --scan --top-n 10 --export-csv exports\latest-scan.csv
if errorlevel 1 goto :fail
echo.

echo [3/4] Export latest snapshot summary
python app_bootstrap.py --export-latest-summary exports\latest-summary.txt
if errorlevel 1 goto :fail
echo.

echo [4/4] Backup local data
python app_bootstrap.py --backup-data
if errorlevel 1 goto :fail

endlocal
goto :eof

:fail
echo.
echo Daily workflow stopped because the previous step failed.
endlocal
exit /b 1
