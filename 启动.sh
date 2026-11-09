#!/bin/bash
# 一键启动新版界面：构建前端（如有改动）后启动服务。
# 默认监听 0.0.0.0:8766，整个局域网可访问；只给本机用加 --local-only。
cd "$(dirname "$0")" || exit 1
if ! command -v pnpm &> /dev/null; then
    echo "未找到 pnpm，请先安装 Node.js 并执行 npm install -g pnpm"
    exit 1
fi
exec python3 start.py "$@"
