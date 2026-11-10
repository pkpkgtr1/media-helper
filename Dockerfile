# 构建界面 → 装依赖 → 只把产物和代码带进运行时镜像。
# 两段式的原因：Node 与 pnpm 只在构建时需要，运行时镜像不必背 300 MB 的 node_modules。

FROM node:22-alpine AS web
WORKDIR /build/web
# 固定 pnpm 大版本，避免 corepack 拉到与本地不一致的版本改坏 lockfile。
RUN npm install -g pnpm@10
# 先只拷清单，依赖没变时这层能命中缓存。
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build


FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MEDIA_HOST=0.0.0.0 \
    MEDIA_PORT=8766 \
    MEDIA_ALLOW_LAN=1

# ffmpeg 用于合并 m3u8 分片；--no-install-recommends 免得拉进一堆图形库。
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
# yt-dlp 不在 requirements 里（本机是可选项），但容器里没有它直链/m3u8 就下不了，装上更省事。
RUN pip install --no-cache-dir -r requirements.txt yt-dlp

COPY media_helper/ ./media_helper/
COPY --from=web /build/web/dist ./web/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
# 拷贝进来的文件权限跟着构建上下文走，别指望它有可执行位。

# 状态与媒体都放在固定路径，方便挂载成卷；用户用非 root 的 app。
# 权限全部显式给：源目录里可能是 600，`chmod +x` 只会补出 711（其他用户可执行但不可读），
# 以 app 身份跑 /bin/sh 读不到入口脚本，就会报 "cannot open ...: Permission denied"。
RUN chmod 755 /usr/local/bin/entrypoint.sh \
 && chmod -R a+rX /app \
 && useradd --create-home --uid 1000 app \
 && mkdir -p /app/config /app/media \
 && chown -R app:app /app
USER app

VOLUME ["/app/config", "/app/media"]
EXPOSE 8766

# 未登录也返回 200，能在设置密码后继续用来探活。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8766/api/auth/status', timeout=4).status == 200 else 1)"

# 用 sh 显式解释，这样只要求可读，不再依赖可执行位。
ENTRYPOINT ["/bin/sh", "/usr/local/bin/entrypoint.sh"]
