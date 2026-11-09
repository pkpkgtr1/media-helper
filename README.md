# 媒体下载助手

一个本地 Web 服务，把两件事合在一起：按月批量整理 **hanime1.me** 的元数据与视频，
以及订阅 **AI 短剧**（黄果、野果两个源）并自动追更下载。产物都是 Emby / Jellyfin
能直接识别的目录结构 —— NFO + 封面 + 规范文件名的视频。

后端是 Python 3.11+ 标准库 `http.server` 加 `requests`，前端 React 19 + Vite 8 +
Tailwind v4，深浅两套主题，桌面与手机同一套布局。默认端口 **8766**。

## 快速开始

```bash
cd media-helper/web
pnpm build
cd media-helper
python3 start.py          # 首次运行会装依赖、构建界面，然后监听 0.0.0.0:8766
bash 启动.sh              # 同上，额外先检查 pnpm 是否存在
```

启动日志会打印本机与局域网地址（`来源限制` 那行末尾还会提示用哪个地址访问）：

```
媒体下载助手已启动：http://127.0.0.1:8766
局域网地址：http://192.168.11.250:8766
来源限制：10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7；同网段其他设备请用以上地址访问
```

`start.py` 按顺序做这些事：低于 Python 3.11 直接报错 → 检查 `requirements.txt` 的
依赖，缺就在项目内建 `.venv` 并安装（不会去猜旧路径下的虚拟环境）→ 已有实例在跑就
直接打开浏览器、不抢端口 → `pnpm install` / `pnpm build`（只在 `dist` 缺失或源码比
产物新时构建）→ 补上局域网监听参数 → 启动服务。

### Windows

先装 [Python 3.11+](https://www.python.org/downloads/)（勾选 *Add python.exe to PATH*）
和 [Node.js](https://nodejs.org/)，然后在项目目录执行 `python start.py`。

> `启动.bat` 里写的是 `python3 start.py`，官方 Windows 安装包默认只提供 `python.exe`，
> 双击可能一闪而过。用 `python start.py` 更稳妥。

> **已知问题**：`npm install -g pnpm` 在 Windows 上装出的是 `pnpm.CMD`（批处理），
> `subprocess` 直接执行会报 `[WinError 193] %1 不是有效的 Win32 应用程序`。当前
> `start.py` 未做 `.cmd` 转发，遇到该报错请先在 `web/` 下手动执行
> `pnpm install && pnpm build`，之后启动就会跳过构建。

## 启动参数

`start.py` 会把参数原样转给 `media_helper.server`，两边都可用：

| 参数 | 说明 |
| --- | --- |
| `--port` | 监听端口，默认 `8766` |
| `--host` | 监听地址，默认 `127.0.0.1`；填 `0.0.0.0` 或本机内网 IP 可供局域网访问 |
| `--lan` / `--allow-lan` | 确认允许同网段设备访问（等价 `MEDIA_ALLOW_LAN=1`） |
| `--lan-cidr CIDR` | 放行来源网段，可重复；默认 `10/8`、`172.16/12`、`192.168/16`、`fc00::/7` |
| `--local-only` | `start.py` 独有，改回只听 `127.0.0.1` |
| `--state-dir` | 运行时数据目录，默认 `config/`；测试实例用它避开正式数据 |
| `--output-root` | 覆盖 hanime 媒体库根目录 |
| `--no-browser` | 启动后不自动打开浏览器 |

只监听回环时其他设备根本连不上，所以 `start.py` 在没给任何监听参数时会自动补上
`--host 0.0.0.0 --lan`；来源仍受网段白名单约束。监听外部地址却不加 `--lan` 会被
直接拒绝，避免误开放。

```bash
python3 start.py --lan-cidr 192.168.11.0/24   # 只放行本网段
python3 start.py --local-only                 # 退回只监听 127.0.0.1
python3 start.py --host 192.168.11.250 --lan  # 只绑某块网卡
```

只跑后端（默认仍是回环，监听参数要自己给）：

```bash
.venv/bin/python -m media_helper --host 0.0.0.0 --lan --port 8766 --no-browser
```

### 访问控制

服务只放行三类请求，其余一律 403：

- **Host 头**：`127.0.0.1`、`localhost`、`::1`、本机主机名，或（开了 `--lan` 时）
  落在白名单网段里的 IP。
- **来源地址**：回环，或白名单网段。
- **Origin**：同源地址；`Origin: null` 直接拒绝。

带点号的外部域名一律不认，哪怕它解析到内网 —— 这一条用来挡 DNS rebinding。局域网
访问必须用 `http://192.168.x.x:8766` 这种 IP 直连，`Host` 对不上就是 403。

## 功能

### 媒体库（hanime1.me）

按「年 + 月」操作，一个月份对应 `outputRoot` 下的一个子目录：

1. **获取图片与 NFO** 抓当月列表，写 `YYYY-MM.json` / `YYYY-MM.csv` 索引，以及每条的
   NFO、封面（`-poster.jpg`）与背景图（`-fanart.jpg`）。
2. 勾选后 **下载所选** 拉视频，或 **下载本月视频** 全量下；**重新下载封面** 只补图；
   **补齐缺失文件** 按缺失类型补 NFO / 图片 / 视频。
3. 列表可按状态筛选（全部 / 待下载 / 下载中 / 已完成 / 失败 / 缺少图片 / 缺少 NFO），
   也可按标题、编号搜索；详情面板显示编号、分辨率、原始分类、写入分类与三条文件路径。

单个条目的产物命名：

```
[厂商] 标题-poster.jpg      封面
[厂商] 标题-fanart.jpg      背景图
[厂商] 标题.nfo             影片 NFO
[厂商] 标题.mp4             视频
```

NFO 里写入哪些分类与标签由「设置 → 分类与标签」决定，未勾选的不写入。已有 NFO 可在
该页先预览再应用，应用前会自动备份。

### AI 短剧

四个页签：

- **搜索**：关键词同时查黄果与野果（也可限定单一源），结果卡片带来源徽标，直接
  「添加订阅」。
- **我的订阅**：每条一行，显示已下载集数、待下载集数、下次检查时间，可手动「检查」、
  「下载」、编辑、暂停；删除时可选是否同时删掉已下载目录。
- **下载任务**：按时间倒序（最新的在最前），进行中的任务带进度条，可取消、重试、
  补截图。「清空记录」只清已结束的任务，进行中的保留，且不会删任何已下载文件。
- **默认设置**：新订阅的默认保存路径、检查周期、自动检查、自动下载、下载范围
  （仅后续新增 / 全部下载 / 指定集数）。

每条订阅独立计时，后台线程按各自周期检查更新，发现新集数时按设置自动下载或只提示。
输出结构与 Emby 剧集库一致：

```
<保存路径>/<剧名>/tvshow.nfo
<保存路径>/<剧名>/poster.jpg
<保存路径>/<剧名>/Season 01/<剧名> - S01E01.mp4
<保存路径>/<剧名>/Season 01/<剧名> - S01E01.nfo
<保存路径>/<剧名>/Season 01/<剧名> - S01E01-thumb.jpg
```

短剧默认保存在 `media/AI短剧`。保存路径支持相对路径（如 `./media/AI短剧`），一律按
项目根目录解析，不受启动时工作目录影响。

## 设置

设置存在 `config/settings.json`，界面「设置」里分五组：

- **常规**：默认输出目录、海报模式（网页截图已下线，封面与背景图统一从站点下载）、
  封面来源（DMM / ani-map / 自动选择）、已有图片处理（跳过 / 重新下载）。
- **下载**：已有视频处理（跳过 / 重新下载）、失败重试次数（0–20，0 表示不重试）、
  下载间隔、请求超时。
- **网络**：代理开关与地址（`http` / `socks5`，支持 `http://用户:密码@主机:端口`）、
  User-Agent、FlareSolverr 开关 / 地址 / 会话 ID。
- **分类与标签**：NFO 保留的分类与标签、更新已有 NFO。
- **维护**：运行环境检测（Python、FFmpeg、yt-dlp、依赖、FlareSolverr 状态，只报告
  不安装）、导出日志、导入 / 导出设置。

改动对后续任务生效，正在跑的任务不受影响。开启代理时必须填地址，否则保存被拒。

### 代理与 FlareSolverr

黄果与野果直连通常不可用，需要代理。代理对所有出口统一生效：页面请求、封面，以及
视频下载（`yt-dlp` 带 `--proxy`、`ffmpeg` 带 `-http_proxy`）。本机地址
（`127.0.0.1`、`localhost`、`::1`）始终直连，不会绕进代理。

站点出现 Cloudflare 挑战页时启用 FlareSolverr。一旦启用，页面 UA 由它决定，
`userAgent` 设置只在未启用时生效；会话 ID 随每次调用下发，会话被清理时自动重建并
重试一次。

### 环境变量

界面里的设置是首选，下列变量用于不改配置文件的临时覆盖：

| 变量 | 作用 |
| --- | --- |
| `MEDIA_HOST` / `MEDIA_PORT` | 默认监听地址与端口 |
| `MEDIA_ALLOW_LAN` | `1` / `true` / `yes` / `on` 等价于 `--lan` |
| `MEDIA_LAN_CIDRS` | 放行网段，逗号或空格分隔 |
| `MEDIA_DEV_ORIGINS` | 开发模式额外放行的 Origin |
| `MEDIA_USER_AGENT` | 覆盖默认 UA |
| `MEDIA_PROXY` | 子进程使用的代理地址 |
| `MEDIA_FLARESOLVERR` / `_URL` / `_SESSION` | FlareSolverr 开关、地址、会话 |

## 目录结构

```
start.py            一键启动：准备依赖、构建前端、补监听参数、起服务
启动.sh / 启动.bat   启动包装脚本（Linux / Windows）
media_helper/
  config.py         设置读写、月份索引、NFO 生成与预览
  net.py            HTTP 会话、UA、代理、FlareSolverr 桥接
  crawler.py        hanime 月度抓取、图片、NFO、视频下载
  worker.py         子进程任务，JSONL 事件流回传进度
  resolution.py     m3u8 分辨率探测
  translator.py     离线日中翻译（可选依赖，缺失时原样返回）
  server.py         HTTP 服务、访问控制、任务调度、接口路由
  sources/          短剧源：huangguo、yeguo 与统一订阅管理器
web/                前端源码，构建产物 dist/ 由后端托管
design-system/      设计令牌与页面规范
tests/              单元测试
config/             运行时数据（已 gitignore）
media/              默认输出目录（已 gitignore）
```

`config/` 里放着 `settings.json`、`tasks.json`、`operations.log`、`jobs/`（每个任务的
输出与 stderr）和 `huangguo/`（`subscriptions.json`、`downloads.json`）。旧版本的
`.media-helper/` 目录首次启动会自动改名迁移，目标已有 `settings.json` 时不覆盖。

## 接口

前端就是这些接口的消费者，本地调试可以直接用。`GET` 读、`POST` 写，收发都是 JSON。

| 路径 | 说明 |
| --- | --- |
| `/api/bootstrap` | 设置、默认值与加载错误 |
| `/api/state` | 任务列表与操作日志快照 |
| `/api/environment` | 运行环境检测结果 |
| `/api/library?year=&month=` | 某月的媒体库条目 |
| `/api/settings` | 读取（GET）/ 保存（POST）设置 |
| `/api/tasks` | 新建任务，`kind` 为 `metadata` / `covers` / `video` / `repair` / `resolutions` |
| `/api/task-action` | `cancel` / `retry` / `clear-completed` / `retry-failed` |
| `/api/nfo/preview`、`/api/nfo/apply` | NFO 分类预览与写入 |
| `/api/logs/clear`、`/api/proxy/test` | 清空日志、测试代理连通性 |
| `/api/choose-directory`、`/api/open-path` | 选目录、在文件管理器中打开 |
| `/api/hg/search`、`/api/hg/detail` | 短剧搜索（`source` 可为 `all`）与详情 |
| `/api/hg/subscriptions`、`/api/hg/tasks`、`/api/hg/records` | 订阅、任务、下载记录 |
| `/api/hg/subscribe` | 新增订阅 |
| `/api/hg/subscription/update`、`/api/hg/subscription/remove`、`/api/hg/subscription/repair` | 修改、删除订阅，修复封面 |
| `/api/hg/check`、`/api/hg/download`、`/api/hg/thumb` | 检查更新、下载指定集、补截图 |
| `/api/hg/task/cancel`、`/api/hg/task/retry`、`/api/hg/task/clear` | 短剧任务控制 |

图片走 `<img>` 标签，所以单列几个二进制接口：`/api/asset?path=`（本地封面，限已选
目录）、`/api/hg/image?url=`（站点图片，SSRF 防护后代理解密）、
`/api/hg/cover?subscriptionId=`。

## 开发

```bash
cd web && pnpm install
pnpm dev          # Vite 开发服务器，127.0.0.1:8444，/api 转发到 8766
pnpm typecheck    # tsc --noEmit
pnpm build        # 类型检查 + 构建到 web/dist
```

先把后端跑起来（`python3 start.py --no-browser`），再开 `pnpm dev`。开发端口刻意避开
8766，两个可以同时开着；要指向别的后端时设 `MEDIA_API_URL`。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -q      # 216 个用例
cd web && pnpm typecheck && pnpm build
```

涉及文件读写的用例都在 `tempfile.TemporaryDirectory` 里跑，不会动 `config/` 与
`media/`；整套约 10 秒。

## 依赖

- Python 3.11+，必需包见 `requirements.txt`：`requests`、`beautifulsoup4`、`lxml`、
  `Pillow`；短剧接口的 AES 解密需要 `cryptography`，缺了短剧功能不可用。
- Node.js + pnpm：只在构建界面时需要。
- 可选 `ffmpeg` 与 `yt-dlp`，用于下载直链与 m3u8（放在项目 `bin/` 下也会被认）。
  「设置 → 维护 → 运行环境」会显示是否找到。
- 可选 `argostranslate`，启用离线日中翻译；未安装时保留原文，不影响抓取。

## 备注

- 端口默认 8766，可与旧版的 8765 并存。
- 短剧源走注册表（`SOURCES` / `make_client`），新增站点只需实现同名 Client 并登记。
- 后端已去掉 Playwright 抓取路径，hanime 只走 requests + FlareSolverr，安装体积更小。
- 前端用语义化颜色令牌做深浅主题；状态不只靠颜色区分，表格、抽屉、弹窗都支持键盘操作。
