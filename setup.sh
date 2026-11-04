#!/usr/bin/env bash
# 双低转债助手 - macOS / Linux 环境安装
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/3] 创建虚拟环境 .venv ..."
  python3 -m venv .venv
else
  echo "[1/3] 复用已有虚拟环境 .venv"
fi

echo "[2/3] 安装依赖 ..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] 初始化本地数据文件 ..."
./.venv/bin/python app_bootstrap.py

cat <<'MSG'

安装完成。启动桌面应用：
    ./.venv/bin/python mod.py
MSG
