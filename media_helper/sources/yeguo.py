"""yeguodj.com client: encrypted JSON API, AES covers and signed HLS.

The site is a Nuxt SPA whose real API lives at /api.php/{path}. Every response
is `{"errcode":0,"data":"<base64 AES-CBC ciphertext>"}` — the key/IV/sign keys
are hard-coded in the front-end bundle (nuxt_BIgYouz_.js), so they are pinned
here. Covers use a second key pair and HLS playlists carry short-lived
`auth_key` signatures on rotating CDN domains, so addresses are resolved right
before each download.

The CDN answers `https://op.udhhzr.cn` with an occasional TLS reset through
some proxies; falling back to plain `http://` on the same host works, and a
"warning" HTML page (HTTP 200) is treated as a soft failure so the caller can
re-resolve a fresh signed URL.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from urllib.parse import urlparse

import requests
import urllib3

from .huangguo import Client as BaseClient
from .huangguo import HuangguoError, _image_cache_key, _image_put

BASE = "https://www.yeguodj.com"
API = BASE + "/api.php"
SITE_REFERER = "https://yeguodj.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

API_KEY = b"2acf7e91e9864673"
API_IV = b"1c29882d3ddfcfd6"
MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

COMMON_PARAMS = {
    "bundleId": "com.pwa.mater", "version": "1.3.2", "oauth_type": "web",
    "language": "zh", "via": "pwa",
    "oauth_id": "7d05538c4b8a5e74e82f93c0dab0163c",
    "trace_id": "7d05538c4b8a5e74e82f93c0dab0163c",
}

# 站点/CDN 域名会轮换，只放行这里登记过的后缀；接口返回的新域名会在首次
# 使用时登记进实例白名单（见 `_check`），避免 CDN 换域名即整体失效。
ALLOWED_HOSTS = ("yeguodj.com", "www.yeguodj.com")
ALLOWED_CDN_SUFFIXES = (".hdhwqx.cn", ".udhhzr.cn", ".oolrvd.cn", ".yeguodj.com")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class YeguoError(HuangguoError):
    pass


def _aes_decrypt(blob, key, iv):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    if not blob or len(blob) % 16:
        raise YeguoError("密文长度非法")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = cipher.update(blob) + cipher.finalize()
    pad = plain[-1] if plain else 0
    if 0 < pad <= 16 and plain[-pad:] == bytes([pad]) * pad:
        plain = plain[:-pad]
    return plain


def _b64decode(text):
    raw = str(text or "").strip().replace(" ", "+").replace("\n", "")
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.b64decode(raw)
    except (binascii.Error, ValueError) as exc:
        raise YeguoError(f"响应编码异常：{exc}") from exc


class Client(BaseClient):
    """Blocking client bound to the current proxy settings."""

    source = "yeguo"
    source_label = "野果短剧"

    def __init__(self, proxy_url=None, timeout=30):
        super().__init__(proxy_url=proxy_url, timeout=timeout)
        self.session.headers.update({"Accept": "application/json",
                                     "Origin": BASE,
                                     "Referer": SITE_REFERER})
        self._detail_cache = {}
        self._extra_hosts = set()

    # ---------------- transport ----------------
    def _check(self, url, allow_cdn=False):
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            raise YeguoError(f"非法地址：{url}")
        if host in ALLOWED_HOSTS or host in self._extra_hosts:
            return url
        if allow_cdn and any(host.endswith(suffix) for suffix in ALLOWED_CDN_SUFFIXES):
            return url
        raise YeguoError(f"非法地址：{url}")

    def _remember_host(self, url):
        host = (urlparse(url).hostname or "").lower()
        if host:
            self._extra_hosts.add(host)

    def _api(self, path, params=None, retries=3):
        """POST one API call and return the decrypted `data` object."""
        payload = dict(COMMON_PARAMS)
        payload.update({k: str(v) for k, v in (params or {}).items()})
        last = None
        for attempt in range(retries):
            try:
                response = self.session.post(API + path, data=payload, timeout=self.timeout)
                if response.status_code != 200:
                    last = YeguoError(f"HTTP {response.status_code}：{path}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                body = response.json()
            except (requests.RequestException, ValueError) as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if body.get("errcode") not in (0, "0", None):
                raise YeguoError(str(body.get("errmsg") or body.get("msg") or f"接口错误 {body.get('errcode')}"))
            raw = body.get("data")
            if not raw:
                raise YeguoError("接口未返回数据")
            plain = _aes_decrypt(_b64decode(raw), API_KEY, API_IV)
            try:
                data = json.loads(plain.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise YeguoError(f"响应解析失败：{exc}") from exc
            for url in _walk_urls(data):
                self._remember_host(url)
            return data.get("data", data) if isinstance(data, dict) else data
        raise YeguoError(f"访问失败：{last}")

    def _cdn_fetch(self, url, referer, attempts=4):
        """CDN GET; the CDN resets TLS intermittently and may serve a hijack page.

        Both answers are transient, so they are retried rather than surfaced:
        the connection-level reset usually clears within a couple of seconds,
        and the plain-`http` variant of the same URL is tried as a last resort.
        """
        self._check(url, allow_cdn=True)
        headers = {"Referer": referer or SITE_REFERER, "Accept": "*/*"}
        targets = [url]
        if url.startswith("https://"):
            targets.append("http://" + url[len("https://"):])
        last = None
        for target in targets:
            for attempt in range(attempts):
                try:
                    response = self.session.get(target, headers=headers, timeout=60)
                    if response.status_code in (200, 206):
                        body = _Guarded(response)
                        if not _looks_like_warning(body.content):
                            return body
                        last = YeguoError("CDN 返回了拦截页")
                    else:
                        last = YeguoError(f"HTTP {response.status_code}：{target}")
                except requests.RequestException as exc:
                    last = exc
                time.sleep(0.7 * (attempt + 1))
        raise YeguoError(f"CDN 访问失败：{last}")

    def _playlist_text(self, url, referer, refresh=None, attempts=3):
        """Playlist body; the CDN occasionally answers with a hijack/warning page."""
        last = None
        for attempt in range(attempts):
            try:
                response = self._cdn_fetch(url, referer)
            except YeguoError as exc:
                last = exc
                time.sleep(1 + attempt)
                continue
            text = response.content.decode("utf-8", errors="replace").lstrip("\ufeff \r\n")
            if text.startswith("#EXTM3U"):
                return text
            if not _looks_like_warning(response.content):
                return text  # 例如 JSON 错误页，交给上层判断
            last = YeguoError("播放地址已失效或返回了拦截页，请重新解析后再试")
            if refresh:
                # auth_key 只有几分钟有效期：续签后换新地址重试
                try:
                    fresh = refresh()
                    if fresh and fresh != url:
                        self._remember_host(fresh)
                        url = fresh
                        continue
                except HuangguoError:
                    pass
            time.sleep(1 + attempt)
        raise last

    # ---------------- API surface ----------------
    def search(self, keyword, page=1, limit=20):
        data = self._api("/api/search/result", {"keyword": keyword.strip(), "page": page, "limit": limit})
        rows = []
        for item in data.get("list") or []:
            video_id = str(item.get("video_id") or item.get("id") or "")
            if not video_id:
                continue
            episodes = int(item.get("episodes") or 0)
            rows.append({
                "id": video_id,
                "videoId": video_id,
                "source": self.source,
                "sourceLabel": self.source_label,
                "title": str(item.get("title") or "").strip(),
                "url": f"{BASE}/drama/detail/{video_id}/",
                "cover": str(item.get("cover") or ""),
                "description": str(item.get("description") or ""),
                "episodeLabel": f"更新至{episodes}集" if episodes else "",
                "score": str(item.get("play_count_text") or ""),
                "tags": [str(t) for t in (item.get("tags") or [])][:10],
                "episodeId": item.get("episode_id"),
            })
        return rows

    def detail(self, video_id):
        data = self._api("/api/playlet/detail", {"video_id": str(video_id)})
        episodes = data.get("episodes") or []
        ids, numbers = {}, []
        for index, ep in enumerate(episodes, start=1):
            number = int(ep.get("sort") or index)
            numbers.append(number)
            if ep.get("id") is not None:
                ids[number] = ep["id"]
        numbers.sort()
        info = {
            "id": str(video_id),
            "videoId": str(video_id),
            "source": self.source,
            "sourceLabel": self.source_label,
            "title": str(data.get("title") or "").strip(),
            "url": str(data.get("share_url") or f"{BASE}/drama/detail/{video_id}/"),
            "cover": str(data.get("cover") or ""),
            "description": str(data.get("description") or ""),
            "tags": [str(t) for t in (data.get("tags") or [])][:10],
            "premiered": "",
            "actors": "、".join(str(a.get("name") if isinstance(a, dict) else a)
                               for a in (data.get("actor_list") or [])),
            "total": int(data.get("episode_count") or len(numbers)),
            "episodes": numbers,
            "episodeMap": ids,
            "status": str(data.get("serialize_status_text") or ""),
        }
        self._detail_cache[str(video_id)] = (time.time(), info)
        return info

    def _episode_id(self, video_id, episode):
        cached = self._detail_cache.get(str(video_id))
        info = cached[1] if cached and time.time() - cached[0] < 300 else self.detail(video_id)
        ep_id = (info.get("episodeMap") or {}).get(int(episode))
        if ep_id is None:
            raise YeguoError(f"第 {episode} 集不存在（该剧共 {info.get('total')} 集）")
        return ep_id

    def episode_stream(self, video_id, episode, title=""):
        ep_id = self._episode_id(video_id, episode)
        data = self._api("/api/playlet/play", {"video_id": str(video_id), "episode_id": str(ep_id)})
        url = str(data.get("video_url") or "").replace("\\/", "/")
        if not url:
            raise YeguoError("未解析到播放地址")
        self._remember_host(url)
        return url

    def episode_page_url(self, video_id, episode=None):
        return f"{BASE}/drama/detail/{video_id}/"

    def fetch_image(self, url, referer=None):
        """Download a cover; the image host serves AES-CBC encrypted PNG/JPEG."""
        if not url:
            return None
        key = _image_cache_key(url)
        if key is not None:
            from .huangguo import _IMAGE_CACHE, IMAGE_TTL_SECONDS, _now_ts
            hit = _IMAGE_CACHE.get(key)
            if hit and _now_ts() - hit[0] < IMAGE_TTL_SECONDS:
                return hit[1]
        self._check(url, allow_cdn=True)
        response = self._cdn_fetch(url, referer)
        data = response.content
        if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
            _image_put(key, data)
            return data
        try:
            plain = _aes_decrypt(data, MEDIA_KEY, MEDIA_IV)
        except Exception:  # noqa: BLE001
            return None
        if plain[:3] == b"\xff\xd8\xff" or plain[:8] == b"\x89PNG\r\n\x1a\n":
            _image_put(key, plain)
            return plain
        return None


class _Guarded:
    """Response shim: the CDN sometimes answers with an HTTP-200 warning page."""

    def __init__(self, response):
        self.status_code = response.status_code
        self.content = response.content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise YeguoError(f"HTTP {self.status_code}")

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")


def _looks_like_warning(data):
    """True for the 反诈 warning page the CDN serves with HTTP 200."""
    head = (data or b"")[:512].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def _walk_urls(value):
    """Collect absolute http(s) URLs from an API payload (host allow-listing)."""
    found = []
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            if node.startswith("http://") or node.startswith("https://"):
                found.append(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def clean_description(text):
    """野果简介已经是纯正文，仅做空白规整。"""
    return re.sub(r"\s+", " ", str(text or "")).strip()


strip_ad = clean_description  # 与黄果模块保持同一接口名
