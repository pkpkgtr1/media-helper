# 媒体下载助手

一个本地 Web 服务，把两件事合在一起：按月批量整理 **hanime1.me** 的元数据与视频，
以及订阅 **AI 短剧**（黄果、野果两个源）并自动追更下载。产物都是 Emby / Jellyfin
能直接识别的目录结构 —— NFO + 封面 + 规范文件名的视频。

后端是 Python 3.11+ 标准库 `http.server` 加 `requests`，前端 React 19 + Vite 8 +
Tailwind v4，深浅两套主题，桌面与手机同一套布局。默认端口 **8766**。

## 快速开始

```bash
cd /vol2/1000/app/media-helper
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
| `--no-auth` | 跳过登录校验（密码保留），只给本机脚本调试用 |

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

## 登录

设置过密码之后，**本机与局域网访问都要先过登录页**，没有例外。没设密码时保持原来的
直接进入，界面会提示去设置（首次打开会直接弹出设置页，也可以选「稍后设置，先进入」）。

- 密码只存本机 `config/auth.json`，PBKDF2-HMAC-SHA256（26 万次迭代 + 16 字节随机盐），
  不写进 `settings.json`，所以导出设置、分享配置都不会带出密码。
- 登录状态靠 `HttpOnly` 的 `mh_session` Cookie，令牌只放内存 —— 重启服务后需要重新
  登录，30 天未使用自动失效，使用中自动续期。
- 同一来源连续错 8 次锁 60 秒，锁定期内连正确密码也不放行。
- 密码 6–128 位，不能有首尾空格。改密码需要先输当前密码，改完其他设备上的会话全部作废。
- 忘记密码：停掉服务，删除 `config/auth.json`，重启后重新设置。文件里没有明文，
  恢复只能走这一步。
- `--no-auth` 只跳过校验、不动密码，适合本机脚本调试；对外开的实例别加这个参数。

密码设置页在「设置 → 安全」，可以看登录状态、改密码、退出登录。接口是
`/api/auth/status`、`/api/auth/setup`、`/api/auth/login`、`/api/auth/password`、
`/api/auth/logout`。

## Docker

```bash
docker compose up -d --build      # 首次构建大约 2–3 分钟
docker compose logs -f            # 看启动日志
```

起来之后打开 `http://<宿主机IP>:8766`，第一次会要求设置访问密码。也可以不用 compose：

```bash
docker build -t media-helper .
docker run -d --name media-helper -p 8766:8766 \
  -v "$PWD/config:/app/config" -v "$PWD/media:/app/media" \
  media-helper
```

镜像分两段构建：`node:22-alpine` 里 `pnpm build` 出 `web/dist`，再拷进
`python:3.12-slim` 运行时，所以镜像里没有 Node 和 `node_modules`。运行时装了
`ffmpeg` 与 `yt-dlp`，直链和 m3u8 都能直接下。

| 挂载 / 变量 | 说明 |
| --- | --- |
| `/app/config` | 设置、任务、日志与登录密码，**必须持久化**，否则每次重建都要重设密码 |
| `/app/media` | 默认输出目录，换成大容量盘即可 |
| `MEDIA_PORT` | 容器内监听端口，默认 `8766`，改完记得同步 `ports` |
| `MEDIA_ALLOW_LAN` | 默认 `1`；设成 `0` 就只绑回环，容器外访问不到 |
| `MEDIA_STATE_DIR` / `MEDIA_OUTPUT_ROOT` | 想改上面两个路径时用，改了要同步改挂载点 |

容器里以 uid 1000 的 `app` 用户运行。挂载宿主机目录时如果属主不同，入口脚本会直接
报「目录不可写」并退出，改一下目录属主（`chown -R 1000:1000 config media`）即可。

宿主机上 `config/` 与 `media/` 和本机直接运行是同一份，两种方式不要同时开 —— 端口
会冲突，任务记录也可能互相覆盖。

### 常见报错

**`/bin/sh: 0: cannot open /usr/local/bin/entrypoint.sh: Permission denied`**

镜像里的入口脚本没有可读权限。根因是源文件权限为 `600`（或在 Windows / 某些共享盘上
丢失了可读位），而 Dockerfile 当时用的是 `chmod +x` —— `600` 补上 `x` 只得到 `711`
（`rwx--x--x`）：属主可读写执行，**其他人只能执行、不能读**。容器以 `app`（uid 1000）
启动 `/bin/sh 脚本`，读文件这一步就失败了，于是报这个错（和
`/bin/sh /etc/shadow` 的报错一模一样）。

现在 Dockerfile 已改成 `chmod 755` + `chmod -R a+rX /app`，并且
`ENTRYPOINT ["/bin/sh", "..."]`，只要求可读，不再依赖可执行位。重建即可：

```bash
docker compose build --no-cache && docker compose up -d
```

手上只有旧镜像、想立刻验证别的东西时，可以暂时用 root 启动（属主位可读），
但以 root 跑会在 `/app/config` 里留下 root 属主的文件，验证完记得改回来：

```bash
docker run --rm -it --user root -p 8766:8766 \
  -v "$PWD/config:/app/config" -v "$PWD/media:/app/media" media-helper:latest
```

**`目录不可写：/app/config`**

挂载目录属主不是 uid 1000。宿主机上执行 `chown -R 1000:1000 config media`，或在
compose 里加 `user: "$(id -u):$(id -g)"` 用当前用户跑。



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

### Jasna 资源库

第三个分类，读的是 `config/ltxdb/ltx.db`（SQLite），与根目录的 `ltxdb.py` 命令行
脚本共用同一份数据，任一边同步另一边立刻可见。

数据来自 `https://ltx.libray.workers.dev/api/items`，该站点只有一个公开接口，一次
返回全量（约 2800 条）。同步 = 拉一次 → 写 `items.json` 原始快照（原子替换）→
upsert 进库；单次约 4–6 秒。

- **搜索**：关键词同时匹配番号、标题、中文标题、演员、厂商与导演；番号大小写与
  连字符不敏感（`ssis834`、`SSIS-834` 都能命中）。
- **筛选**：按厂商、分类、排序（发行日期 / 评分 / 热度 / 收录时间）过滤，分页显示，
  每页 48 条。
- **详情**：点卡片打开，显示演员、导演、分类、评分与全部 ed2k / 磁力链接（含文件名
  与体积），可一键复制链接或字幕地址。
- **同步**：页面顶部「立即同步」手动拉一次；也可以按「设置 → 常规 → Jasna 资源库」
  里设定的周期自动同步（默认每 6 小时，服务启动时若从没同步过会立刻补一次）。

封面经 `/api/ltx/cover` 代理，只放行 `jdbstatic.com` 与 `javdb.com` 两个域名，结果
按 URL 缓存 12 小时，避免这个接口被当成任意 URL 代理。

命令行仍可直接用：

```bash
python3 ltxdb.py sync                 # 拉全量
python3 ltxdb.py stats                # 库统计
python3 ltxdb.py lookup SSIS-834      # 按番号查
python3 ltxdb.py search 三上 --limit 10
```

`LTXDB_HOME` 可覆盖库位置，默认 `config/ltxdb`。

## 设置

设置存在 `config/settings.json`，界面「设置」里分六组：

- **常规**：默认输出目录、启动月份、完成后打开输出目录、Jasna 资源库自动同步开关与
  同步周期（1–9999 分钟 / 小时 / 天，默认 6 小时）、海报模式（网页截图已下线，封面与
  背景图统一从站点下载）、封面来源（DMM / ani-map / 自动选择）、已有图片处理
  （跳过 / 重新下载）。
- **下载**：已有视频处理（跳过 / 重新下载）、失败重试次数（0–20，0 表示不重试）、
  下载间隔、请求超时。
- **网络**：代理开关与地址（`http` / `socks5`，支持 `http://用户:密码@主机:端口`）、
  User-Agent、FlareSolverr 开关 / 地址 / 会话 ID。
- **分类与标签**：NFO 保留的分类与标签、更新已有 NFO。
- **安全**：登录状态、修改 / 设置访问密码、退出登录。
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
ltxdb.py            Jasna 资源库命令行（sync / stats / lookup / search / export）
启动.sh / 启动.bat   启动包装脚本（Linux / Windows）
media_helper/
  config.py         设置读写、月份索引、NFO 生成与预览
  net.py            HTTP 会话、UA、代理、FlareSolverr 桥接
  crawler.py        hanime 月度抓取、图片、NFO、视频下载
  worker.py         子进程任务，JSONL 事件流回传进度
  resolution.py     m3u8 分辨率探测
  translator.py     离线日中翻译（可选依赖，缺失时原样返回）
  auth.py           登录密码、会话令牌、失败冷却
  server.py         HTTP 服务、访问控制、登录拦截、任务调度、接口路由
  ltx.py            Jasna 资源库：抓取、SQLite 入库、检索与定时同步
  sources/          短剧源：huangguo、yeguo 与统一订阅管理器
web/                前端源码，构建产物 dist/ 由后端托管
docker/             容器入口脚本
Dockerfile / docker-compose.yml  容器构建与编排
design-system/      设计令牌与页面规范
tests/              单元测试
config/             运行时数据（已 gitignore），含 ltxdb/ltx.db
media/              默认输出目录（已 gitignore）
```

`config/` 里放着 `settings.json`、`tasks.json`、`operations.log`、`auth.json`（登录密码）、
`jobs/`（每个任务的输出与 stderr）、`huangguo/`（`subscriptions.json`、`downloads.json`）
和 `ltxdb/`（`ltx.db` 与接口原始快照 `items.json`）。旧版本的
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
| `/api/auth/status` | 是否设置密码、当前请求是否已登录 |
| `/api/auth/setup`、`/api/auth/password` | 首次设置密码、修改密码 |
| `/api/auth/login`、`/api/auth/logout` | 登录（下发 Cookie）、退出 |
| `/api/choose-directory`、`/api/open-path` | 选目录、在文件管理器中打开 |
| `/api/hg/search`、`/api/hg/detail` | 短剧搜索（`source` 可为 `all`）与详情 |
| `/api/hg/subscriptions`、`/api/hg/tasks`、`/api/hg/records` | 订阅、任务、下载记录 |
| `/api/hg/subscribe` | 新增订阅 |
| `/api/hg/subscription/update`、`/api/hg/subscription/remove`、`/api/hg/subscription/repair` | 修改、删除订阅，修复封面 |
| `/api/hg/check`、`/api/hg/download`、`/api/hg/thumb` | 检查更新、下载指定集、补截图 |
| `/api/hg/task/cancel`、`/api/hg/task/retry`、`/api/hg/task/clear` | 短剧任务控制 |
| `/api/ltx/status` | Jasna 资源库状态：条数、上次 / 下次同步、周期、失败原因 |
| `/api/ltx/items?keyword=&maker=&genre=&sort=&page=&limit=` | 检索资源库（关键词、厂商、分类、排序、分页） |
| `/api/ltx/detail?code=` | 单条详情，含链接文件名与体积 |
| `/api/ltx/filters` | 可选厂商与分类列表 |
| `/api/ltx/sync` | 立即同步（POST，同步完成才返回） |
| `/api/ltx/cover?url=` | 封面代理，仅放行站点 CDN |

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
.venv/bin/python -m unittest discover -s tests -q      # 286 个用例
cd web && pnpm typecheck && pnpm build
```

涉及文件读写的用例都在 `tempfile.TemporaryDirectory` 里跑，不会动 `config/` 与
`media/`；整套约 10 秒。

## ⚠️ 免责声明

- 本项目仅用于**个人学习与技术研究**，不提供任何资源内容，也不存储任何受版权保护的文件。
- 所有数据均来自公开网络，由使用者自行配置的账号与网络环境获取，**使用者需自行承担合规责任**。
- 请勿用于商业用途、二次分发或任何违反当地法律法规的场景。
- 因使用本工具导致的账号封禁、数据丢失等后果，由使用者自行承担。
