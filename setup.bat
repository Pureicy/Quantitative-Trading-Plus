@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  双低转债助手 - 环境安装
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.10+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
) else (
    echo [1/3] 复用已有虚拟环境 .venv
)

echo [2/3] 安装依赖 (flet / flet-desktop / pandas / akshare) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接。
    pause
    exit /b 1
)

echo [3/3] 初始化本地数据文件 ...
".venv\Scripts\python.exe" app_bootstrap.py

echo.
echo 安装完成。启动桌面应用：
echo     start_quant_assistant.bat
echo.
pause
endlocal
