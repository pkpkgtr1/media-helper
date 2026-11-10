"""huangguoai.com client: search, detail, episodes, HLS video and encrypted covers.

The site serves SSR HTML only (no public JSON API). Covers are AES-128-CBC
encrypted at rest with key/IV published in the site's own
crypto-image-protocol.js; video streams are AES-128-CBC HLS with short-lived
auth_key URLs (~78s), so playlists are resolved lazily and retried once.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import urllib3

from .. import net

BASE = "https://huangguoai.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
PROTOCOL_JS = "/static/web/js/plugins/crypto-image-protocol.js"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HuangguoError(RuntimeError):
    pass


ALLOWED_HOSTS = ("huangguoai.com",)
ALLOWED_CDN_SUFFIXES = (".drleao.cn", ".eisees.com", ".hzjvlo.cn", ".aluxvl.cn")


def _safe(url, allow_cdn=False):
    """Reject anything outside the site and its known CDN domains (anti-SSRF)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        raise HuangguoError(f"非法地址：{url}")
    if host in ALLOWED_HOSTS:
        return url
    if allow_cdn and any(host.endswith(suffix) for suffix in ALLOWED_CDN_SUFFIXES):
        return url
    raise HuangguoError(f"非法地址：{url}")


_IMAGE_CACHE = {}
_IMAGE_CACHE_ORDER = []
IMAGE_TTL_SECONDS = 6 * 3600
IMAGE_CACHE_LIMIT = 48


def _image_cache_key(url):
    """host + path, ignoring rotating query signatures."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.netloc or not parsed.path:
        return None
    return parsed.netloc.lower() + parsed.path


def _image_put(key, data):
    if key is None or not data:
        return
    if len(data) > 4 * 1024 * 1024:
        return
    _IMAGE_CACHE[key] = (_now_ts(), data)
    _IMAGE_CACHE_ORDER.append(key)
    # 淘汰：超量或过期条目，防止长时间运行内存增长
    while len(_IMAGE_CACHE_ORDER) > IMAGE_CACHE_LIMIT:
        stale = _IMAGE_CACHE_ORDER.pop(0)
        if stale != key:
            _IMAGE_CACHE.pop(stale, None)


def _now_ts():
    return time.time()


class Client:
    """Blocking client bound to the current proxy settings."""

    def __init__(self, proxy_url=None, timeout=25):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": net.current_ua(UA), "Referer": BASE + "/"})
        self.session.verify = False
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    # ---------------- HTML helpers ----------------
    def _get(self, url, referer=None, retries=3, wait=2.0, allow_cdn=False):
        _safe(url, allow_cdn=allow_cdn)
        last = None
        headers = {"Referer": referer or BASE + "/"}
        for attempt in range(retries):
            try:
                response = self.session.get(url, headers=headers, timeout=self.timeout)
                if response.status_code == 200:
                    return response
                if response.status_code in (403, 404, 429, 500, 502, 503):
                    last = HuangguoError(f"HTTP {response.status_code}：{url}")
                    time.sleep(wait * (attempt + 1))
                    continue
                raise HuangguoError(f"HTTP {response.status_code}：{url}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
                time.sleep(wait * (attempt + 1))
        raise HuangguoError(f"访问失败：{last}")

    def _cdn_fetch(self, url, referer):
        """GET one CDN resource (playlist/key/segment); sites may override."""
        return self.session.get(_safe(url, allow_cdn=True),
                                headers={"Referer": referer}, timeout=60)

    def _playlist_text(self, url, referer, refresh=None):
        """Playlist body; sites with flaky TLS or signed URLs may override."""
        return self._cdn_fetch(url, referer).text

    # ---------------- image crypto ----------------
    def image_keys(self):
        if getattr(self, "_image_keys", None):
            return self._image_keys
        script = self._get(BASE + PROTOCOL_JS).text
        match = re.search(r'Object\.freeze\((\{.*?\})\)', script)
        if not match:
            raise HuangguoError("图片解密配置解析失败")
        config = json.loads(match.group(1))
        if not config.get("decryptEnabled"):
            self._image_keys = None
            return None
        self._image_keys = (config["decryptKey"].encode(), config["decryptIV"].encode())
        return self._image_keys

    def decrypt_image(self, data):
        keys = self.image_keys()
        if not keys or len(data) < 16 or len(data) % 16:
            return data
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.AES(keys[0]), modes.CBC(keys[1])).decryptor()
        return cipher.update(data) + cipher.finalize()

    def fetch_image(self, url, referer=None):
        """Download a site image and return decoded JPEG bytes (best effort).

        Results are cached across Client instances keyed by host+path: the site
        rotates `auth_key` on every page load, so the same poster keeps asking
        for a fresh ~1.7s proxied fetch otherwise (search card → detail dialog).
        """
        unescaped = htmllib.unescape(url)
        key = _image_cache_key(unescaped)
        if key is not None:
            hit = _IMAGE_CACHE.get(key)
            if hit and _now_ts() - hit[0] < IMAGE_TTL_SECONDS:
                return hit[1]
        response = self._get(unescaped, referer=referer, allow_cdn=True)
        data = response.content
        if data[:3] == b"\xff\xd8\xff":
            _image_put(key, data)
            return data
        try:
            plain = self.decrypt_image(data)
            if plain[:3] == b"\xff\xd8\xff" or plain[:8] == b"\x89PNG\r\n\x1a\n":
                _image_put(key, plain)
                return plain
        except Exception:
            pass
        return None

    # ---------------- search ----------------
    def search(self, keyword):
        page = self._get(f"{BASE}/search/video/{quote(keyword.strip())}/")
        text = page.text
        # 只解析真实结果区：页面上"猜你喜欢"推荐位与热搜位同样是 hg-drama-card，
        # 混在一起会把推荐剧当成搜索结果（如“海贼王”1 个结果被解析成 5 个）。
        start = text.find('class="hg-search-results"')
        if start >= 0:
            body = text[start:]
            for marker in ("hg-search-suggest", "hg-search-hot", "<footer"):
                cut = body.find(marker)
                if cut > 0:
                    body = body[:cut]
            text = body
        results, seen = [], set()
        chunks = text.split('<div class="hg-drama-card"')[1:]
        for block in chunks:
            link = re.search(r'href="/video/(\d+)/"', block)
            if not link:
                continue
            vid = link.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            title = _first(r'class="hg-drama-card__title"[^>]*>\s*<a[^>]*>([^<]+)', block) \
                or _first(r'data-track-item-name="([^"]*)"', "<div class=\"hg-drama-card\"" + block) or ""
            cover = _first(r'class="hg-drama-card__cover-link"[^>]*>.*?data-src="([^"]+)"', block) \
                or _first(r'data-src="(https?://[^"]+)"', block)
            desc = _first(r'<p class="hg-drama-card__desc">([^<]*)', block) or ""
            episode = _first(r'class="hg-drama-card__episode"[^>]*data-ep-base="([^"]+)"', block) \
                or _first(r'class="hg-drama-card__episode"[^>]*>\s*([^<]+?)<', block) or ""
            score = _first(r'hg-drama-card__score">([^<]+)<', block) or ""
            tag_block = _first(r'<div class="hg-drama-card__tags">(.*?)</div>', block)
            tags = re.findall(r'<a class="hg-tag"[^>]*>([^<]+)', tag_block) if tag_block else []
            results.append({"id": vid, "title": htmllib.unescape(title.strip()),
                            "url": f"{BASE}/video/{vid}/",
                            "cover": htmllib.unescape(cover) if cover else "",
                            "description": strip_ad(htmllib.unescape(desc.strip()))[:200],
                            "episodeLabel": htmllib.unescape(episode.strip()),
                            "score": htmllib.unescape(score.strip()),
                            "tags": [htmllib.unescape(t) for t in tags[:6]]})
        return results

    # ---------------- detail ----------------
    def detail(self, video_id):
        url = f"{BASE}/video/{int(video_id)}/"
        page = self._get(url)
        text = page.text
        title = _first(r'<meta property="og:title" content="([^"]+?)(?: - 黄果短剧|\s*-\s*黄果短剧)', text) \
            or _first(r'<title>([^<]+?)(?: -|·)', text) or ""
        description = _first(r'<meta property="og:description" content="([^"]*)"', text) or ""
        # 封面：详情页正文里第一个图常是推荐位（曾导致 poster.jpg 存成别的剧）。
        # 以 og:image 的文件名为准，在页面里找同名图片（优先带新鲜 auth_key 的 pic 域名）。
        og_image = htmllib.unescape(_first(r'<meta property="og:image" content="([^"]+)"', text) or "")
        cover = self._match_cover(og_image, text)
        total = _first(r'全\s*(\d+)\s*集', text)
        episodes = sorted({int(m) for m in re.findall(rf'/video/{video_id}/ep-(\d+)/', text)})
        tags = self._main_tags(text)
        premiered = _first(r'<span class="hg-detail[^>]*>(\d{4})年', text) or ""
        actors = _first(r'主演[：:]\s*</[^>]+>([^<]{2,120})', text) or ""
        total_count = int(total) if total else (max(episodes) if episodes else 1)
        # 站点编号从 1 开始且"全N集"权威；页面偶有推荐位外链，取 <= total 的链接与完整区间
        full_range = list(range(1, total_count + 1)) if total_count > 0 else sorted(set(episodes))
        return {"id": str(int(video_id)), "title": htmllib.unescape(title.strip()), "url": url,
                "description": strip_ad(htmllib.unescape(description.strip())),
                "cover": htmllib.unescape(cover) if cover else "",
                "total": total_count,
                "episodes": full_range or [1],
                "tags": [htmllib.unescape(t) for t in dict.fromkeys(tags)][:10],
                "premiered": premiered, "actors": actors.strip()}

    def _main_tags(self, text):
        """Tags of the show itself, never of the recommendation cards.

        A detail page embeds many `hg-drama-card` blocks (猜你喜欢), each carrying
        its own `hg-tag` links. Scanning the whole page therefore mixed every
        recommendation's tags into the subscription. The show's own tags live in
        `.hg-web-play__tags` inside the intro card.
        """
        block = re.search(r'<div class="hg-web-play__tags[^"]*">(.*?)</div>', text, re.S)
        segment = block.group(1) if block else ""
        if not segment:
            start = text.find('hg-web-play__introcard')
            if start < 0:
                return []
            end = text.find('hg-web-play__scorebox', start)
            if end < 0:
                end = text.find('<footer', start)
            segment = text[start:end if end > 0 else len(text)]
        values = re.findall(r'<a class="hg-tag"[^>]*>([^<]+)', segment)
        return [htmllib.unescape(value.strip()) for value in values if value.strip()]

    def _match_cover(self, og_image, text):
        """Pick the page URL of the show's own poster, keyed by the og:image name."""
        if not og_image:
            return ""
        name = og_image.split("?")[0].rsplit("/", 1)[-1]
        if not name:
            return og_image
        candidates = [htmllib.unescape(u) for u in re.findall(r'(https?://[^"\'\s]+%s[^"\'\s]*)' % re.escape(name), text)]
        for url in candidates:
            if ".drleao.cn" in url and ".jpg" in name.lower() or ".drleao.cn" in url:
                return url
        return candidates[0] if candidates else og_image

    def episode_page_url(self, video_id, ep):
        return f"{BASE}/video/{int(video_id)}/ep-{int(ep)}/" \
            if int(ep) > 1 else f"{BASE}/video/{int(video_id)}/"

    def _cdn_auth(self, page_text):
        """Playing URL needs the CDN auth header advertised by the page.

        The detail/episode page embeds `#videoInitialData` with the CDN gate
        (authKey/authValue). Missing it is fine for plain GETs but the playback
        endpoint 403s for some episodes, so read it defensively.
        """
        match = re.search(r'<script[^>]*id="videoInitialData"[^>]*>(.*?)</script>', page_text, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(1))
        except (ValueError, TypeError):
            return {}
        key = str(data.get("cdnAuthKey") or "").strip()
        value = str(data.get("cdnAuthValue") or "").strip()
        return {key: value} if key and value else {}

    def _post(self, url, headers, body="{}"):
        """POST helper (playback API); isolated so tests can stub it out."""
        return self.session.post(url, headers=headers, data=body, timeout=self.timeout)

    def _playback_stream(self, video_id, ep, page_url):
        """Resolve via POST /api/videos/{id}/episodes/{ep}/playback.

        站点 2026-11 改版后的唯一取址方式：返回的 data.streams.main 才是带签名
        的 m3u8。旧 GET /api/videos/{id}/play 现在对所有集都回空 video_url，
        这正是「第N集未找到播放地址」的直接原因。空 body 是必需的：带
        {"ep":N} 反而会被判「播放参数无效」。
        """
        api_url = f"{BASE}/api/videos/{video_id}/episodes/{ep}/playback"
        headers = {"Referer": page_url, "Content-Type": "application/json",
                   "X-Requested-With": "XMLHttpRequest"}
        try:
            page = self._get(page_url, referer=page_url)
            headers.update(self._cdn_auth(page.text))
        except HuangguoError:
            pass  # 取不到附属页也不该阻断取链，跳过鉴权头直接试
        try:
            response = self._post(api_url, headers)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise HuangguoError(f"访问失败：{exc}")
        if response.status_code != 200:
            raise HuangguoError(f"HTTP {response.status_code}：{api_url}")
        try:
            payload = response.json()
        except ValueError:
            raise HuangguoError("播放地址接口返回非 JSON")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise HuangguoError(str(payload.get("msg") or "播放地址接口未返回数据"))
        streams = data.get("streams") or {}
        for name in ("main", "hevc", "preview"):
            play = htmllib.unescape(str(streams.get(name) or ""))
            if ".m3u8" in play:
                return play
        return ""

    def episode_stream(self, video_id, ep, title=""):
        """Resolve the m3u8 for one episode. Call right before downloading.

        取址顺序（新→旧，兼容站点多次改版）：
          1. POST /api/videos/{id}/episodes/{ep}/playback 的 data.streams.main（2026-11 起）
          2. GET  /api/videos/{id}/play?ep=N 的 data.video_url（旧版接口，现多为空串）
          3. 分集页 HTML 里的 <source src="...m3u8">（更旧的结构）
        """
        video_id = int(video_id)
        ep = int(ep)
        page_url = self.episode_page_url(video_id, ep)
        try:
            play = self._playback_stream(video_id, ep, page_url)
            if play:
                return play
        except HuangguoError:
            pass
        api_url = f"{BASE}/api/videos/{video_id}/play?ep={ep}&r={int(time.time())}"
        try:
            data = self._get(api_url, referer=page_url).json().get("data") or {}
            play = htmllib.unescape(str(data.get("video_url") or data.get("video_url_hevc") or ""))
            if ".m3u8" in play:
                return play
        except (HuangguoError, ValueError, KeyError):
            pass
        page = self._get(page_url + ("?" if "?" in page_url else "?") + f"r={int(time.time())}", referer=page_url)
        match = re.search(r'<source src="([^"]+\.m3u8[^"]*)"', page.text)
        if not match:
            raise HuangguoError(f"第{ep}集未找到播放地址（站点可能正在更新该集，可稍后重试）")
        return htmllib.unescape(match.group(1))

    def download_hls(self, m3u8_url, referer, out_path, proxy=None, workers=4,
                     progress=None, stop_flag=None, segment_limit=None, refresh=None):
        """Fetch+decrypt HLS to MP4 (temp .ts + ffmpeg remux). Returns file size.

        `segment_limit` truncates on purpose (demo/tests); remux then keeps one
        video frame so the output stays a valid, small MP4. `refresh` re-resolves
        an expired signed playlist URL; clients without signed URLs ignore it.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part_ts = out_path.with_suffix(".part.ts")
        part_mp4 = out_path.with_suffix(".part.mp4")
        playlist = self._playlist_text(m3u8_url, referer, refresh=refresh)
        key_match = re.search(r'#EXT-X-KEY:METHOD=AES-128,URI="([^"]+)"(?:,IV=0x([0-9a-fA-F]+))?', playlist)
        if key_match:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            key_url = key_match.group(1)
            if not key_url.startswith("http"):
                key_url = m3u8_url.rsplit("/", 1)[0] + "/" + key_url
            key = self._cdn_fetch(key_url, referer).content
            iv_bytes = bytes.fromhex(key_match.group(2)) if key_match.group(2) else bytes(16)

            def decrypt(data):
                if len(data) % 16:
                    data = data[:len(data) - len(data) % 16]
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes)).decryptor()
                return cipher.update(data) + cipher.finalize()
        else:
            decrypt = None
        base = m3u8_url.rsplit("/", 1)[0]
        urls = []
        for line in playlist.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line if line.startswith("http") else base + "/" + line)
        if segment_limit:
            urls = urls[:segment_limit]
        total = len(urls)
        buffers = [None] * total
        state = {"done": 0, "failed": None}
        lock = threading.Lock()

        def fetch(index, url):
            if state["failed"] or (stop_flag and stop_flag.is_set()):
                return
            last = None
            for attempt in range(3):
                if state["failed"] or (stop_flag and stop_flag.is_set()):
                    return
                try:
                    response = self._cdn_fetch(url, referer)
                    response.raise_for_status()
                    data = response.content
                    buffers[index] = decrypt(data) if decrypt else data
                    with lock:
                        state["done"] += 1
                        if progress:
                            progress(state["done"], total)
                    return
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    time.sleep(1 + attempt)
            with lock:
                state["failed"] = state["failed"] or f"分片 {index + 1}/{total} 下载失败：{last}"

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda pair: fetch(*pair), enumerate(urls)))
        if stop_flag and stop_flag.is_set():
            part_ts.unlink(missing_ok=True)
            part_mp4.unlink(missing_ok=True)
            raise HuangguoError("任务已取消")
        if state["failed"]:
            raise HuangguoError(state["failed"])
        with part_ts.open("wb") as sink:
            for chunk in buffers:
                if chunk is None:
                    raise HuangguoError("分片缺失")
                sink.write(chunk)
        if segment_limit:
            command = ["ffmpeg", "-i", str(part_ts), "-frames:v", "1", "-c:v", "copy", "-an",
                       "-movflags", "+faststart", str(part_mp4)]
        else:
            command = ["ffmpeg", "-i", str(part_ts), "-c:v", "copy", "-c:a", "aac",
                       "-movflags", "+faststart", str(part_mp4)]
        run_ffmpeg(command, proxy=proxy)
        part_ts.unlink(missing_ok=True)
        if not part_mp4.is_file() or part_mp4.stat().st_size < 1024:
            part_mp4.unlink(missing_ok=True)
            raise HuangguoError("混流输出无效")
        part_mp4.replace(out_path)
        return out_path.stat().st_size

    def first_frame_thumb(self, video_path, out_path, proxy=None, frame=9):
        """Grab frame 10 (index 9) as the episode thumbnail.

        片头常有黑场/LOGO：该帧偏黑时顺延第 30、50 帧；不足 10 帧的极短视频回退
        第 1 帧。输出经 scale 保持宽高比。
        """
        video_path = Path(video_path)
        out_path = Path(out_path)
        last_size = None
        for candidate in (frame, frame + 20, frame + 40, 0):
            result = run_ffmpeg(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                                 "-i", str(video_path),
                                 "-vf", f"select=eq(n\\,{candidate}),scale=1280:-2",
                                 "-frames:v", "1", "-q:v", "3", str(out_path)],
                                proxy=proxy, timeout=120)
            if result and result.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 2000:
                if _not_black(out_path):
                    return out_path.stat().st_size
                last_size = out_path.stat().st_size
        if last_size:
            return last_size
        out_path.unlink(missing_ok=True)
        raise HuangguoError(f"第{frame + 1}帧缩略图生成失败")


def _not_black(jpeg_path):
    try:
        from PIL import Image, ImageStat
        image = Image.open(jpeg_path).convert("L")
        return ImageStat.Stat(image).mean[0] > 12
    except Exception:
        return True


def clean_description(text):
    """清洗站点采集简介：去模板头“…全N集，X月X日更新。”与结尾“免费在线观看”广告。

    模板头以“全\d+集”为标志（正常正文不会以它开头），连同其前面的标题、后面的
    更新日期一并删除；正文标点保持原样。
    """
    if not text:
        return ""
    result = re.sub(r"\s+", " ", str(text)).strip()
    # 头部：任意前缀（标题）+ 全N集 + [，X月X日更新] + [。]，仅在“全N集”出现于前 40 字内认定为模板
    result = re.sub(r"^.{0,40}?全\d+集(?:[，,]?\d{1,2}月\d{1,2}日更新)?[。.，,]?\s*", "", result, count=1)
    result = result.lstrip("，,。.;； ")
    # 广告词前的句号属于正文标点，只删广告本身；分隔逗号由 rstrip 处理
    result = re.sub(r"免费在线观看[。.]?\s*\Z", "", result)
    return result.rstrip("，,、;； ").strip()


strip_ad = clean_description  # 兼容旧名


def _first(pattern, text):
    match = re.search(pattern, text, re.S)
    return match.group(1) if match else None


def run_ffmpeg(command, proxy=None, timeout=1800, remote=False):
    """Run ffmpeg; `-http_proxy` applies only when ffmpeg itself fetches (remote)."""
    import shutil
    binary = shutil.which("ffmpeg") or str(Path(__file__).resolve().parent / "bin" / "ffmpeg")
    command = [binary] + command[1:] if command[0] == "ffmpeg" else command
    def attempt(use_proxy):
        argv = list(command)
        if use_proxy and proxy and remote:
            argv[1:1] = ["-http_proxy", proxy]
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    result = attempt(True)
    if result.returncode and proxy and remote and "4XX" in (result.stderr or ""):
        result = attempt(False)
    if result.returncode:
        raise HuangguoError(f"ffmpeg 失败（{result.returncode}）：{(result.stderr or '').strip()[-200:]}")
    return result
