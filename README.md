# 媒体下载助手 V2

`media-helper` 的重构版：后端拆成 `media_helper` 包，前端用 React 19 + Vite 8 +
Tailwind v4 重写，深浅两套主题，桌面与手机同一套布局。

## 快速开始

```bash
cd /vol2/1000/app/media-helper
python3 start.py            # 自动安装/构建前端，监听 0.0.0.0:8766，整个局域网可访问
bash 启动.sh                # 同上（先检查 pnpm 再交给 start.py）
```

启动日志会打印本机与局域网地址：

```
媒体下载助手已启动：http://127.0.0.1:8766
局域网地址：http://192.168.11.250:8766
来源限制：10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7
```

默认只放行私网网段，公网域名与白名单之外的来源一律 403（防 DNS rebinding）。
需要更严或更窄时：

```bash
python3 start.py --lan-cidr 192.168.11.0/24   # 只放行本网段
python3 start.py --local-only                 # 退回只监听 127.0.0.1
python3 start.py --host 192.168.11.250 --lan  # 只绑某块网卡
```

`start.py` 会优先使用项目自带 `.venv`，没有则复用同级 `media-helper/.venv`
（两者依赖相同）。首次运行会执行 `pnpm install` 与 `pnpm build`。

只跑后端（默认仍是回环，监听参数要自己给）：

```bash
.venv/bin/python -m media_helper --host 0.0.0.0 --lan --port 8766 --no-browser
```

## 目录结构

```
media_helper/
  config.py        设置读写、分类目录、月份索引、NFO 预览/写入
  net.py           UA、代理、FlareSolverr 会话与拦截页回退
  crawler.py       hanime 月度抓取、图片、NFO、视频下载
  worker.py        子进程任务：metadata / download / repair
  resolution.py    m3u8 分辨率探测
  translator.py    离线日中翻译（可选依赖，缺失时原样返回）
  server.py        HTTP 服务、路由、任务调度
  sources/         短剧站点：huangguo、yeguo，manager 统一订阅与任务
web/               前端源码（Vite 工程，构建产物 dist/ 由后端托管）
tests/             单元测试（python -m unittest discover -s tests）
config/            运行时数据：settings.json、日志、订阅、下载记录
media/             默认输出目录
```

## 配置

所有设置都存在 `config/settings.json`，界面「设置」里可改。重点项：

- `outputRoot`：hanime 媒体库根目录，按月建子目录。
- `hgSaveRoot`：短剧默认保存路径，默认 `media/AI短剧`，Emby 剧集目录建在其下；
  相对路径（如 `./media/AI短剧`）一律按项目根目录解析，不受启动时工作目录影响。
- `proxyEnabled` / `proxyUrl`：黄果与野果直连不可用，需要代理。
- `flaresolverrEnabled` / `flaresolverrUrl` / `flaresolverrSession`：站点出现
  Cloudflare 挑战页时使用；启用后页面 UA 由 FlareSolverr 决定。
- `userAgent`：普通请求统一使用；留空用内置默认值。
- `categories`：NFO 保留的分类与标签，未勾选的不写入。

命令行的 `--state-dir` 可以把运行时数据指到别处，测试实例用它可以不动正式数据。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -q      # 202 个用例
cd web && pnpm typecheck && pnpm build                 # 前端类型检查与构建
```

## 与旧版差异

- 后端从 9 个平铺模块合并为 `media_helper` 包，短剧源走注册表（`SOURCES` /
  `CLIENTS`），新增站点只需实现同名 Client 并登记。
- 去掉 Playwright 抓取路径，hanime 只走 requests + FlareSolverr，安装体积更小。
- 前端重写：语义化颜色令牌与深浅主题、表格/抽屉/弹窗键盘可达、状态不只靠颜色区分。
- 端口默认 8766，可与仍在跑的旧版 8765 并存。
