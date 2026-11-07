#!/bin/bash

# 设置编码（在Linux上可选，但保持兼容性）
# chcp 65001 >nul  # Windows命令，在Linux上忽略

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 检查 pnpm 环境
if ! command -v pnpm &> /dev/null; then
    echo "未找到 pnpm，请先安装 Node.js 并执行 npm install -g pnpm"
    exit 1
fi
# 运行主Python脚本
python3 start_media_helper.py "$@"

# 处理错误代码
if [ $? -ne 0 ]; then
    echo "启动失败，请查看日志"
    read -p "按回车键继续..."
fi
