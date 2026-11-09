"""下载页画质：只按页面实际列出的分辨率判定，绝不从 id 或标签推测。"""
from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlparse

from . import net

QUALITY = r"(240|360|480|540|576|720|1080|1440|2160|4320)p"


def resolution_from_url(url):
    path = unquote(urlparse(str(url or "")).path)
    matches = re.findall(rf"(?<![a-zA-Z0-9]){QUALITY}(?=$|[^a-zA-Z0-9])", path, re.I)
    return max(map(int, matches), default=0)


def download_resolutions(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    values = set()
    for row in soup.select("tr"):
        # 只看真正的下载行，避免把正文里的标签当成画质。
        if not row.select("a[href], button[data-url], button[data-href]"):
            continue
        for cell in row.select("td"):
            values.update(int(x) for x in re.findall(rf"\b{QUALITY}\b", cell.get_text(" ", strip=True), re.I))
    for node in soup.select("a[href], source[src], video[src], [data-url], [data-href]"):
        for attr in ("href", "src", "data-url", "data-href"):
            value = node.get(attr, "")
            if re.search(r"\.(mp4|m3u8)(?:\?|$)", value, re.I):
                quality = resolution_from_url(value)
                if quality:
                    values.add(quality)
    return sorted(values, reverse=True)


def read_download_resolutions(video_id, timeout=30000, fetch=None, session=None):
    """读取下载页列出的画质，不需要浏览器。

    `fetch(url) -> (html, status)` 与 `session` 可注入，方便测试；默认走
    requests，遇到挑战页时交给 FlareSolverr 解析。
    """
    if not str(video_id).isdigit():
        return []
    url = f"https://hanime1.me/download?v={video_id}"
    if fetch is None:
        sess = session if session is not None else net.make_session(retries=False)
        max_timeout = max(5.0, float(timeout) / 1000.0)

        def fetch(target):
            return net.fetch_html(sess, target, referer="https://hanime1.me/", timeout=max_timeout)

    errors = []
    for attempt in range(2):
        try:
            html, status = fetch(url)
            if status >= 400:
                raise RuntimeError(f"下载页 HTTP {status}")
            values = download_resolutions(html or "")
            if values:
                return values
            if attempt == 0:
                # 表格有时比首屏稍晚出现。
                time.sleep(1.0)
                continue
            raise RuntimeError("下载页未返回可用画质")
        except Exception as exc:
            errors.append(str(exc))
            if attempt == 0:
                time.sleep(1.0)
    raise RuntimeError("画质查询两次失败：" + (errors[-1] if errors else "未知错误"))


def entry_resolution(item):
    values = [v for v in (item.get("available_resolutions") or []) if type(v) is int and 100 <= v <= 4320]
    if values:
        return f"{max(values)}p", "下载页最高可用画质"
    return "", "尚未确认下载页最高画质，请刷新分辨率"
