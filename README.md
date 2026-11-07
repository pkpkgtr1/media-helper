## 软件界面

### 主界面

![主界面](ScreenShot_2026-09-05_173940_153.png)

### 媒体库

![媒体库](ScreenShot_2026-09-05_173950_938.png)

### 设置界面

![下载界面](ScreenShot_2026-09-05_173958_992.png)

# 媒体下载助手 V1.0

使用 Python 后端和 React 界面的本地媒体整理工具，支持按月份获取元数据、生成 NFO、保存封面及下载视频。

## 功能

- 媒体库中查看图片、NFO、视频状态和来源分辨率。
- 首页显示逐条处理进度，支持取消、重试和查看日志。
- 分类与标签共用勾选列表，只把资源本身包含且已勾选的标签写入 NFO。
- 预览并批量更新已有 NFO 的分类字段，可保留备份。
- 支持 HTTP/SOCKS 代理（含账号密码），设置-高级中可开关并测试连通；爬虫、封面下载与视频下载统一生效，本机与局域网地址始终直连。
- 黄果短剧（huangguoai.com）：搜索、订阅、按订阅独立周期检查更新、手动/自动下载，输出 Emby 电视剧目录（S01E01 命名、tvshow.nfo、分集 nfo、海报与首帧缩略图）。
- 黄果短剧模块可独立运行；旧 Tk 图形界面已由 Web 界面取代并移除。

## 安装与启动（Windows/Linux）

需要 Python 3.11+、Node.js 22.12+ 或 24+，以及 pnpm。

在项目根目录执行（Windows，PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-media-helper.txt
npm install -g pnpm
.\.venv\Scripts\python.exe start_media_helper.py
```

首次启动会自动下载 Chromium 到项目内 `ms-playwright\`、安装前端依赖、检查类型并构建界面，然后打开 `http://127.0.0.1:8765`。后续可双击 `启动新界面.bat`。保留服务终端窗口，按 Ctrl+C 停止服务。

若启动时自动下载失败（如无网络/代理不通），可手动执行（PowerShell，浏览器装进项目目录，与运行用户无关）：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\ms-playwright"
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 安装与启动（Linux）

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-media-helper.txt
npm install -g pnpm
./.venv/bin/python start_media_helper.py
```

浏览器安装到项目内 `ms-playwright/` 可避免多用户环境（如 fnOS）下"装的人"和"跑服务的人" HOME 不一致导致找不到浏览器的报错；程序会自动优先使用该目录，写进 Windows 计划任务或开机脚本同样有效；Windows/Linux 启动脚本检测到缺失时都会自动补装。若直接执行 `python -m playwright install chromium`，浏览器会装进当前用户的 `~/.cache/ms-playwright`，仅当服务与安装使用同一用户时才可找到。

首次启动会安装前端依赖、检查类型并构建界面，然后打开 `http://127.0.0.1:8765`。后续可执行 `./启动新界面.sh`。保留服务终端窗口，按 Ctrl+C 停止服务。

视频处理需要另行安装 FFmpeg 和 yt-dlp，将可执行文件放入根目录 `bin/` 或加入 PATH。离线翻译为可选功能，需要自行安装 `argostranslate` 和相应模型；模型文件可放在 `models/`，不可用时保留原文或使用现有在线翻译回退。

## 黄果短剧

左侧导航“黄果短剧”提供搜索、我的订阅、下载任务与默认设置四个区域：

- **依赖代理**：huangguoai.com 在多数网络不可直连，请先在“设置 → 高级”开启代理，页面顶部有提示。
- 搜索页展示名称、封面、简介、更新状态与评分，可查看详情、分集列表、打开原始网页并添加订阅（已订阅有标识）。
- 每条订阅可独立设置：自动检查开关、检查周期（分钟/小时/天）、保存路径、自动下载开关与下载范围（全部下载/仅后续新增/指定集数，新订阅默认“全部下载”）。默认值在“默认设置”区域，仅影响新订阅。
- 检查/下载任务有等待、进行中、完成、失败、取消状态与进度；失败可在任务列表重试，自动重试次数与间隔在默认设置中配置；同一订阅的运行任务不会重复启动。
- 站点 HLS 为 AES-128 加密且地址签名会过期，程序即时解析、并发拉取分片解密后用 ffmpeg 混流；下载与混流验证成功才改名入库并记录，临时 `.part` 文件不会被 Emby 当作正式视频。
- 输出结构：`保存路径/剧名 (年份)/tvshow.nfo、poster.jpg、Season 01/剧名 - S01E01.mp4|.nfo|-thumb.jpg`；年份未知则省略，同名剧自动追加来源编号目录后缀。分集缩略图取第 10 帧（黑屏自动顺延第 30/50 帧，不足 10 帧回退首帧），失败可单独补做而不重新下载视频。
- 订阅、下载记录与检查计划存于 `.media-helper/huangguo/`，重启服务后保留。删除订阅默认保留文件，勾选后才删除对应剧集目录。
- 站点图片使用固定 AES 密钥加密传输，界面封面经本机 `/api/hg/image` 解密代理显示。
- 需要 FFmpeg 与 Python `cryptography`（已加入 requirements）；站点无公开 JSON API，解析基于页面结构，页面改版时可能需要更新 `huangguo_client.py` 选择器。

## 局域网访问

服务默认只监听 `127.0.0.1`，因此用 `http://192.168.11.250:8765/` 这类局域网地址访问不了，这是设计上的限制，不是安装问题。需要让同网段的电脑或手机访问时，显式开启局域网模式：

```bash
./.venv/bin/python start_media_helper.py --lan --host 0.0.0.0 --lan-cidr 192.168.11.0/24
```

`启动新界面.sh` 与 `启动新界面.bat` 会原样透传参数，例如 `./启动新界面.sh --host 0.0.0.0 --lan`；不带参数时也可用环境变量开启，Windows 为 `set MEDIA_HOST=0.0.0.0 && set MEDIA_ALLOW_LAN=1`，Linux 为 `MEDIA_HOST=0.0.0.0 MEDIA_ALLOW_LAN=1 ./启动新界面.sh`。开启后启动日志会额外打印可访问的局域网地址。建议同时用 `--lan-cidr` 收紧到实际网段，例如 `192.168.11.0/24`。

| 参数 | 环境变量 | 作用 |
| --- | --- | --- |
| `--host` | `MEDIA_HOST` | 监听地址，默认 `127.0.0.1`；局域网用 `0.0.0.0` |
| `--lan` | `MEDIA_ALLOW_LAN=1` | 允许非本机来源访问界面与 API |
| `--lan-cidr` | `MEDIA_LAN_CIDRS` | 放行来源网段，可重复；默认 RFC1918 与 `fc00::/7` |
| — | `MEDIA_DEV_ORIGINS` | 追加允许的调试 Origin，默认含 `http://127.0.0.1:8443` |

局域网模式下仍保留两层防护：来源 IP 必须命中白名单网段，`Host` 必须是回环地址、白名单内的 IP 或本机无点主机名（带点的域名一律拒绝，避免 DNS rebinding）。只给 `--host 0.0.0.0` 而不给 `--lan` 会直接报错，避免误暴露。

开放后局域网内其他设备可触发下载和整理任务，请只在可信网络使用，必要时用防火墙把 `8765` 限制到指定设备。该服务没有鉴权，也不建议通过端口转发暴露到公网。

## 源码结构

| 路径 | 用途 |
| --- | --- |
| `Design app interface/src/` | React 界面 |
| `media_server.py` | 本地 API 与任务调度 |
| `media_worker.py` | 后台任务执行 |
| `media_storage.py` | 设置、媒体索引和 NFO 更新 |
| `media_resolution.py` | 来源分辨率解析 |
| `hanime_nfo_crawler.py` | 元数据获取和 NFO 生成 |
| `download_move.py` | 下载相关功能 |
| `translator_offline.py` | 翻译支持 |
| `tests/` | 自动化测试 |

详细操作见 [使用说明](README-new-ui.md)。

## 开发与验证

```bash
./.venv/bin/python -m unittest discover -s tests -v
cd "Design app interface"
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
```

开发时分别运行 `python media_server.py --no-browser` 和前端目录中的 `pnpm dev`；开发界面端口为 8443，API 端口为 8765。

## 本地文件与 Git

源码、依赖清单、前端锁文件和测试应提交到仓库。`.gitignore` 已排除虚拟环境、前端依赖、构建产物、浏览器、第三方可执行文件、模型、下载媒体，以及 `.media-helper/` 中的个人设置和任务日志。这些本地依赖需在新机器上重新安装。

自定义媒体输出目录若位于仓库内，也应加入 `.gitignore`，避免提交下载文件及月份索引。