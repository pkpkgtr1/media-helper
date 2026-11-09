"""媒体下载助手（新版）：按年月整理 hanime1.me 与短剧订阅，输出 Emby/Jellyfin 目录结构。

模块边界：
- `config`     设置、媒体库索引、NFO 读写（本地状态，不联网）
- `net`        HTTP 会话、User-Agent、FlareSolverr 桥接
- `resolution` 下载页画质
- `crawler`    hanime1.me 抓取与下载
- `worker`     单个后台任务子进程（JSONL 事件流）
- `server`     HTTP 服务、访问控制与任务编排
- `sources`    短剧站点客户端与订阅管理器
"""
from __future__ import annotations

__all__ = ["__version__", "__app_name__"]

__version__ = "2.0.0"
__app_name__ = "媒体下载助手"
