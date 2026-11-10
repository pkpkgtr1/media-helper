#!/bin/sh
# 容器入口：确认状态与媒体目录可写，补齐监听参数，然后交给 python -m media_helper。
# 额外参数追加在最后，argparse 取最后一个值，因此可以覆盖这里的默认值。
set -eu

STATE_DIR="${MEDIA_STATE_DIR:-/app/config}"
# 输出目录只在显式指定时才覆盖，否则用界面里设置过的值。
OUTPUT_ROOT="${MEDIA_OUTPUT_ROOT:-}"

for dir in "$STATE_DIR" "${OUTPUT_ROOT:-/app/media}"; do
    mkdir -p "$dir" 2>/dev/null || true
    if [ ! -w "$dir" ]; then
        echo "目录不可写：$dir（容器内以 uid $(id -u) 运行，请调整挂载目录属主）" >&2
        exit 1
    fi
done

set -- --state-dir "$STATE_DIR" --no-browser "$@"
if [ -n "$OUTPUT_ROOT" ]; then
    set -- --output-root "$OUTPUT_ROOT" "$@"
fi
if [ "${MEDIA_ALLOW_LAN:-1}" = "0" ]; then
    # 不放行局域网时必须绑回环，否则服务自己就会拒绝启动。
    set -- --host 127.0.0.1 "$@"
else
    set -- --host "${MEDIA_HOST:-0.0.0.0}" --lan "$@"
fi
set -- --port "${MEDIA_PORT:-8766}" "$@"

exec python -m media_helper "$@"
