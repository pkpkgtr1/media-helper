"""hanime1.me 抓取：按月列表 → 详情页 → NFO + 封面 + 画质记录。

只做三件事：解析站点页面、写出 NFO/图片、把视频交给 yt-dlp 或 ffmpeg。
浏览器截图、Selenium 兜底与离线翻译都已移除；挑战页统一交给 `net.fetch_html`
（直连失败才启用 FlareSolverr），因此本模块只依赖 requests + bs4。
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from . import net
from .config import PROJECT_ROOT, atomic_write, contained_file, filter_categories, publish_month_item
from .resolution import read_download_resolutions
from xml.sax.saxutils import escape as xml_escape

# ---------------- 站点与选择器 ----------------
BASE_SEARCH = ("https://hanime1.me/search?query=&type=&genre=%E8%A3%8F%E7%95%AA"
               "&sort=&date={year}+%E5%B9%B4+{month}+%E6%9C%88&duration=")

LIST_WRAPPER = "div.home-rows-videos-wrapper"
LIST_ITEMS   = "div.home-rows-videos-wrapper a[href*='watch?v=']"

DETAIL_TITLE      = "#shareBtn-title"
DETAIL_DESC       = "div.video-caption-text"
DETAIL_TAG_ITEM   = "div.video-details-wrapper.video-tags-wrapper div.single-video-tag a"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ---------------- NFO 清洗配置 ----------------
# 说明：这里维护“需要从 <tag>/<genre> 里屏蔽”的词。
# 使用 NFKC 归一化后匹配（兼容全角/半角、部分波浪/符号差异）。
TAG_BLACKLIST = {
    # 历史屏蔽
    "魔物娘", "阿嘿颜", "阿嘿顏", "异种族", "巨乳", "比基尼", "1080p", "放尿", "口爆", "腋交",
    "着衣", "潮吹", "尖耳朵", "兽交", "remove", "add", "马尾", "贫乳", "背后位", "处女", "妖精",
    "中文字幕", "办公室", "图书馆", "夜店", "手交", "浴室", "淫纹", "游泳池", "火车便当", "爱情宾馆", "男乳首责", "车震",
    "逆强制", "黑皮肤", "傲娇", "十指紧扣", "双马尾", "外射", "女仆", "强制", "女王样", "水手服", "深喉咙", "迷你裙",
    "高跟鞋", "公众场合", "乳牛", "兔女郎", "寻欢洞", "胃凸", "修女", "户外野战", "素股", "女战士", "怪兽",
    "魔法少女", "丁字裤", "性暴力", "性玩具", "摄影", "教室", "阴毛", "项圈", "女医生", "情侣", "榨精", "短发",
    "群交", "自慰", "捆绑", "吞精", "同事", "肉便器", "断面图", "# 武田弘光", "眼罩", "性奴隶", "毒龙钻", "紧身衣",
    "丑男", "内射", "內射", "# 雷火劍", "# 雷火剑",

    # 今日追加（用户新增）
    "凌虐", "美人痣", "魅魔", "男教师", "磨豆腐", "女忍", "偶像", "拳交", "旗袍", "热裤", "兽耳", "肉棒打脸", "兽娘", "睡眠奸",
    "舔腋下", "妄想専科", "无表情", "巫女", "新東宝", "眼镜娘", "眼神死", "藥物", "鷹の爪", "株式会社虎の穴", "醉酒",
    "BREAKBOTTLE", "Celeb", "chippai", "COSMOS", "Discovery", "erozuki", "GOLD BEAR", "Hills", "Honnybit", "HOT BEAR", "Lovely", "MOON ROCK",
    "nur", "Princess Sugar", "Stringendo", "Studio DEEN", "Studio Fantasia", "TOHO", "ANIMAC", "AniMan", "Animan", "BDSM", "bdsm", "BOMB!CUTE!BOMB!",
    "BibleBlack", "JVD", "PoRO", "Queen Bee", "PIXY", "ZIZ", "WHITE BEAR", "Collaboration Works", "BOOTLEG", "PashminaA", "GREEN BUNNY", "EDGE",
    "schoolzone", "Schoolzone", "Vanilla", "VANILLA", "Milky", "3D卡通", "OL",

    # 日文社团/片商及别名
    "あんてきぬすっ", "エッジ", "エンゼルフィッシュ", "オブテイン·フューチャー", "オブテイン・フューチャー", "ガールズトーク", "キスハグ",
    "グリーンパニー", "グリーンバニー", "クリエイティブアクザ", "さくらぶりんアニメーション", "さくらぷりんアニメーション", "サークルトリビュート",
    "じゅうしいまんご~", "じゅうしぃまんご～", "ショーテン", "せるふいつしゅ", "せるふぃっしゅ", "セフレ学园", "ツクルノモリ",
    "トッフ?マーシャル", "ばにいうお~か~", "ばにぃうぉ～か～", "パシュミナ", "バ二ラ", "バニラ", "ひまじん", "ピンクパイナップル",
    "ファイブウェイズ", "メディアバンク", "メリー?ジェーン", "ルネ", "ルネピクチャーズ",

    # 近期新增
    "白虎", "爆精", "百合", "病娇", "雌小鬼", "大屌", "巨屌", "飞机杯", "扶他", "高潮", "黑魔术学园", "角色扮演", "和服", "婚纱", "精神崩潰",
    "异物插入", "AI解码", "膝袜", "伪娘", "同人", "女阴摩擦", "女巫", "女儿",
}

def _norm_tag(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip())

TAG_BLACKLIST_NORM = {_norm_tag(x) for x in TAG_BLACKLIST}
TAG_BLACKLIST_NORM_LOWER = {x.lower() for x in TAG_BLACKLIST_NORM}

# 剔除标题末尾一个或多个 [xxx] 后缀，例如：
# ハニーブロンド2 第3話[フクダーダ] [中文字幕] -> ハニーブロンド2 第3話
TITLE_SUFFIX_PATTERN = re.compile(r"(?:\s*\[[^\]]+\]\s*)+$")

def clean_title_suffix(title: str) -> str:
    s = (title or "").strip()
    # 连续剔除末尾方括号块（可预测/不可预测内容统一处理）
    return TITLE_SUFFIX_PATTERN.sub("", s).strip()

def filter_and_sort_tags(tags: list) -> list:
    cleaned=[]
    seen=set()
    for x in (tags or []):
        s=(x or "").strip()
        if not s:
            continue
        s_norm = _norm_tag(s)
        if (s_norm in TAG_BLACKLIST_NORM) or (s_norm.lower() in TAG_BLACKLIST_NORM_LOWER):
            continue
        if s_norm in seen:
            continue
        seen.add(s_norm)
        cleaned.append(s)
    # 排序稳定：按不区分大小写 + 原文
    cleaned.sort(key=lambda v: (v.casefold(), v))
    return cleaned

def rating_to_10(rating_percent):
    if rating_percent is None:
        return None
    try:
        return round(float(rating_percent) / 10.0, 1)
    except Exception:
        return None


# ---------------- 工具与兼容 ----------------
def ensure_dir(p): os.makedirs(p, exist_ok=True); return p

def request_timeout_ms(fallback: int) -> int:
    """设置里的请求超时（秒）→ 毫秒；未设置时用调用方给的默认值。"""
    try:
        return int(float(os.environ["MEDIA_REQUEST_TIMEOUT"]) * 1000)
    except (KeyError, ValueError):
        return fallback

def _proxy_url() -> Optional[str]:
    """Effective proxy URL published by the worker; None means direct."""
    return (os.environ.get("MEDIA_PROXY") or "").strip() or None

def _proxy_cli_args(tool: str, referer: Optional[str] = None) -> list:
    """Proxy CLI arguments for yt-dlp / ffmpeg download commands."""
    proxy = _proxy_url()
    if not proxy:
        return []
    if tool == "yt-dlp":
        args = ["--proxy", proxy]
        if referer:
            args += ["--referer", referer]
        return args
    if tool == "ffmpeg":
        return ["-http_proxy", proxy]
    return []

def _fetch_html(session, url, referer: Optional[str] = None, allow_flaresolverr: bool = True,
                progress: Optional[Callable[[Dict], None]] = None):
    """Plain HTTP first; FlareSolverr only when the page is a challenge/empty."""
    logger = None
    if progress is not None:
        def logger(msg, level="info"):
            progress({"type": "log", "msg": msg, "level": level})
    return net.fetch_html(session, url, referer=referer,
                          timeout=max(5, request_timeout_ms(30000) / 1000),
                          allow_flaresolverr=allow_flaresolverr, log=logger)


def safe_name(s): return re.sub(r'[\\/:*?"<>|\r\n]+', "_", (s or "")).strip()[:180]

def find_stream_url(html: str) -> str:
    m = re.search(r'https?://[^\s\'\"]+?\.m3u8[^\s\'\"]*', html)
    if m: return m.group(0)
    m2 = re.search(r'<source[^>]+src=["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', html, re.I)
    if m2: return m2.group(1)
    m3 = re.search(r'<video[^>]+src=["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', html, re.I)
    return m3.group(1) if m3 else ""

# ---------------- NFO 写入（按你的新要求） ----------------
def write_movie_nfo(basepath: str, *,
                    title_raw: str,
                    title_zh: str,
                    plot_raw: str,
                    plot_zh: str,
                    premiered: str = "",
                    tags: list = None,
                    thumb: str = "",
                    mid: str = "",
                    rating: int | None = None,
                    votes: int | None = None,
                    runtime_min: int | None = None,
                    series_name: str = "",
                    episodes_count: int | None = None,
                    maker: str = "",
                    label: str = "",
                    num: str = "",
                    release: str = "",
                    tagline: str = "",
                    fanart: str = "",
                    nfo_settings: Optional[Dict] = None):
    """
    生成 NFO（按需求）：
      - <title> 去掉末尾 [xxx] 后缀
      - <tag>/<genre> 过滤黑名单并排序
      - <rating> 0-100 转 0-10（如 98 -> 9.8）
    """

    def _norm(s): return (s or "").strip()
    def _end_with_cn_period(s):
        s = _norm(s)
        if not s: return s
        return s if s.endswith(("。","！","？",".","!","?")) else s + "。"

    title_raw   = clean_title_suffix(_norm(title_raw))
    title_zh    = _norm(title_zh)
    plot_raw    = _norm(plot_raw)
    plot_zh     = _norm(plot_zh)
    premiered   = _norm(premiered)
    tagline     = _norm(tagline) or title_zh
    maker       = _norm(maker)
    label       = _norm(label)
    num         = _norm(num)
    release     = _norm(release) or premiered

    # <plot> 组装：按 Emby 友好的 CDATA + <br> 换行格式
    def _fmt_plot(s: str) -> str:
        s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
        return s.replace("\n", "<br>\n")

    plot_out = ""
    if plot_zh:
        plot_out += _fmt_plot(_end_with_cn_period(plot_zh))
    if plot_raw:
        raw_fmt = _fmt_plot(plot_raw)
        plot_out += ("<br>\n<br>\n" if plot_out else "") + raw_fmt

    # 计算 year
    year = ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", premiered) if premiered else None
    if m: year = m.group(1)
    elif re.match(r"^\d{4}$", premiered):
        year, premiered = premiered, ""

    lines = ["<movie>"]
    if title_raw: lines.append(f"  <title>{xml_escape(title_raw)}</title>")
    if title_raw: lines.append(f"  <originaltitle>{xml_escape(title_raw)}</originaltitle>")
    if title_raw: lines.append(f"  <sorttitle>{xml_escape(title_raw)}</sorttitle>")
    if tagline:   lines.append(f"  <tagline>{xml_escape(tagline)}</tagline>")
    if year:      lines.append(f"  <year>{xml_escape(year)}</year>")
    if premiered: lines.append(f"  <premiered>{xml_escape(premiered)}</premiered>")
    if plot_out:
        lines.append("  <plot><![CDATA[" + plot_out.replace("]]>", "]]]]><![CDATA[>") + "]]></plot>")
    if title_zh:  lines.append("  <outline><![CDATA[" + title_zh.replace("]]>", "]]]]><![CDATA[>") + "]]></outline>")
    if mid:       lines.append(f"  <id>{xml_escape(str(mid))}</id>")

    # 扩展字段
    if maker:     lines.append(f"  <maker>{xml_escape(maker)}</maker>")
    if label:     lines.append(f"  <label>{xml_escape(label)}</label>")
    if num:       lines.append(f"  <num>{xml_escape(str(num))}</num>")
    if release:   lines.append(f"  <release>{xml_escape(release)}</release>")
    if maker:     lines.append(f"  <studio>{xml_escape(maker)}</studio>")

    # rating 转 10 分制
    r10 = rating_to_10(rating)
    if r10 is not None:         lines.append(f"  <rating>{r10}</rating>")
    if votes is not None:       lines.append(f"  <votes>{int(votes)}</votes>")
    if runtime_min is not None: lines.append(f"  <runtime>{int(runtime_min)}</runtime>")
    if series_name:             lines.append(f"  <series>{xml_escape(series_name)}</series>")
    if episodes_count is not None:
                                lines.append(f"  <episodes>{int(episodes_count)}</episodes>")
    if series_name:
        lines.append(f"  <set><name>{xml_escape(series_name)}</name></set>")

    lines.append("  <watched>false</watched>")
    lines.append("  <playcount>0</playcount>")

    # 标签/类型（过滤 + 排序）
    if nfo_settings is None:
        _tg_sorted = filter_and_sort_tags(tags)
    else:
            _tg_sorted = filter_categories(tags or [], nfo_settings)
    # 先连续写 tag，再连续写 genre（分开且各自有序）
    for tg in _tg_sorted:
        lines.append(f"  <tag>{xml_escape(tg)}</tag>")
    for tg in _tg_sorted:
        lines.append(f"  <genre>{xml_escape(tg)}</genre>")

    if thumb:
        lines.append(f"  <thumb>{xml_escape(thumb)}</thumb>")
        lines.append(f"  <thumb aspect=\"poster\">{xml_escape(thumb)}</thumb>")
    if fanart:
        lines.append(f"  <fanart>{xml_escape(fanart)}</fanart>")
    if thumb or fanart:
        lines.append("  <art>")
        if thumb:
            lines.append(f"    <poster>{xml_escape(thumb)}</poster>")
        if fanart:
            lines.append(f"    <fanart>{xml_escape(fanart)}</fanart>")
        lines.append("  </art>")

    lines.append(f"  <dateadded>{time.strftime('%Y-%m-%d %H:%M:%S')}</dateadded>")
    lines.append("  <fileinfo>")
    lines.append("    <streamdetails>")
    lines.append("      <video><codec/><aspect/><width/><height/><durationinseconds/><stereomode/></video>")
    lines.append("      <audio><codec/><language>jpn</language><channels/></audio>")
    lines.append("    </streamdetails>")
    lines.append("  </fileinfo>")
    lines.append(f"  <original_filename>{xml_escape(os.path.basename(basepath))}.mp4</original_filename>")

    lines.append("</movie>")
    contained_file(os.path.dirname(os.path.abspath(basepath)), basepath + ".nfo")
    atomic_write(basepath + ".nfo", "\n".join(lines).encode("utf-8"))

# ---------------- 翻译（可选；未安装则保留原文） ----------------
def translate_text_ja2zh(text: str) -> str:
    """站点未提供中文时最多做一次本地翻译；没装翻译库就直接放弃。"""
    try:
        from .translator import translate_text_ja2zh as _translate
    except ImportError:
        return text or ""
    try:
        return _translate(text) or (text or "")
    except Exception:
        return text or ""

# ---------------- 命令查找 ----------------
def which(cmd: str) -> Optional[str]:
    bin_dir = PROJECT_ROOT / "bin"
    for candidate in (bin_dir / cmd, bin_dir / f"{cmd}.exe"):
        if candidate.exists():
            return str(candidate)
    return shutil.which(cmd) or shutil.which(f"{cmd}.exe")

# ---------------- HTTP 会话（核心优化） ----------------
def _make_session() -> requests.Session:
    """带重试与会话级的站点 Cookie 的 requests 会话（代理/UA 由 net 统一处理）。"""
    sess = net.make_session(headers={"Accept-Language": "ja,en;q=0.9,zh-CN;q=0.8"})
    # DMM/FANZA 年龄确认：只是省一次跳转，不保证一定生效。
    for domain in (".dmm.co.jp", ".video.dmm.co.jp"):
        try:
            sess.cookies.set("age_check_done", "1", domain=domain, path="/")
            sess.cookies.set("cklg", "ja", domain=domain, path="/")
        except (ValueError, TypeError):
            pass
    return sess


def _dmm_log(debug_dir: str, msg: str):
    try:
        if not debug_dir:
            return
        ensure_dir(debug_dir)
        fp = os.path.join(debug_dir, "dmm_fanart.log")
        with open(fp, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def _dmm_dump_html(debug_dir: str, html: str):
    try:
        if not debug_dir:
            return
        ensure_dir(debug_dir)
        fp = os.path.join(debug_dir, "dmm_last_page_snippet.html")
        txt = (html or "")[:120000]
        with open(fp, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass


def _remote_image_size(sess: requests.Session, url: str) -> int:
    """探测远程图片字节数，失败返回 0"""
    if not url:
        return 0
    try:
        r = sess.get(url, timeout=(4, 12), stream=False, verify=False)
        if r.status_code != 200:
            return 0
        clen = int(r.headers.get("Content-Length") or 0)
        bsz = len(r.content or b"")
        return max(clen, bsz)
    except Exception:
        return 0


def pick_fanart_url(title: str, sess: requests.Session, cover_site: str = "dmm",
                    min_dmm_bytes: int = 50000, progress: Optional[Callable[[Dict], None]] = None,
                    debug_dir: str = "") -> Tuple[str, str]:
    """
    返回 (fanart_url, source)
    规则：
    - dmm: 先 DMM；若 DMM 图 <50KB 或取不到，再回退 ani-map
    - auto: 同 dmm（即优先 DMM 高清无水印）
    - ani-map: 仅 ani-map
    """
    if progress is None:
        progress = lambda e: None

    cs = (cover_site or "dmm").strip().lower()

    progress({"type": "log", "msg": f"fanart.select site={cs} title={title}"})

    if cs in ("dmm", "auto"):
        dmm_url = fetch_dmm_fanart_url(title, sess, progress=progress, debug_dir=debug_dir)

        # 主链路（requests + DMM 搜索）未命中时直接判定无可用 id；
        # 不再回退到浏览器渲染，那条路径会误抓页面上的 GTM 脚本。

        if dmm_url:
            sz = _remote_image_size(sess, dmm_url)
            progress({"type": "log", "msg": f"fanart[dmm] size={sz} url={dmm_url}"})
            # size=0 视为探测失败（网络/反爬），不直接判死，仍优先走 DMM
            if sz == 0:
                progress({"type": "log", "msg": "fanart[dmm] size=0(未知)，先按DMM下载"})
                return dmm_url, "dmm"
            if sz >= int(min_dmm_bytes):
                return dmm_url, "dmm"
            progress({"type": "log", "msg": f"fanart[dmm] <{min_dmm_bytes} bytes，回退 ani-map"})

        ani_url = fetch_animap_fanart_url(title, sess, progress=progress)
        if ani_url:
            progress({"type": "log", "msg": f"fanart[ani-map] url={ani_url}"})
            return ani_url, "ani-map"
        return "", ""

    # cs == ani-map
    ani_url = fetch_animap_fanart_url(title, sess, progress=progress)
    if ani_url:
        progress({"type": "log", "msg": f"fanart[ani-map] url={ani_url}"})
        return ani_url, "ani-map"
    return "", ""


def fetch_dmm_fanart_url(title: str, sess: Optional[requests.Session] = None,
                         progress: Optional[Callable[[Dict], None]] = None,
                         debug_dir: str = "") -> str:
    """
    规则：
    1) 访问 https://video.dmm.co.jp/anime/list/?key=<title>
    2) 从搜索结果里提取 content id（如 h_1379jdxa57704）
    3) 拼接 https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/<id>/<id>pl.jpg?f=webp
    """
    def _log(msg: str):
        try:
            if progress:
                progress({"type": "log", "msg": msg})
        except Exception:
            pass
        _dmm_log(debug_dir, msg)

    def _normalize_queries(src_title: str) -> list[str]:
        s = clean_title_suffix(src_title)
        cands = [s]
        cands.append(re.sub(r"\s*第\s*\d+\s*[巻话話集]\s*$", "", s, flags=re.I))
        cands.append(re.sub(r"THE\s+ANIMATION", "", s, flags=re.I).strip())
        cands.append(re.sub(r"\s*第\s*\d+\s*[巻话話集]\s*$", "", cands[-1], flags=re.I).strip())
        cands.append(s[:24].strip())
        out = []
        seen = set()
        for x in cands:
            x = (x or "").strip()
            if not x or x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    def _valid_cid(cid: str) -> bool:
        c = (cid or "").strip().lower()
        if not c:
            return False
        if c in {"gtm", "true", "false", "null", "none"}:
            return False
        if len(c) < 6:
            return False
        # DMM 常见：h_1379jdxa57704 / 196glod00408
        if not re.fullmatch(r"[a-z0-9_]+", c):
            return False
        if not re.search(r"[a-z]", c):
            return False
        if not re.search(r"\d", c):
            return False
        return True

    def _extract_cid(html: str) -> str:
        # 只在 DMM 内容页链接上下文里取 id，避免误抓页面哈希/GTM
        pats = [
            r"/anime/content/\?id=([a-zA-Z0-9_]{6,})",
            r"video\.dmm\.co\.jp/anime/content/\?id=([a-zA-Z0-9_]{6,})",
            r"anime/content/\?id=([a-zA-Z0-9_]{6,})&i3_ref=search",
        ]
        for pat in pats:
            for m in re.finditer(pat, html or ""):
                c = m.group(1)
                if _valid_cid(c):
                    return c
        return ""

    title = clean_title_suffix(title)
    if not title:
        _log("[dmm] empty title")
        return ""

    own_sess = False
    if sess is None:
        sess = _make_session()
        own_sess = True

    cid = ""
    try:
        queries = _normalize_queries(title)
        _log(f"[dmm] origin title={title}")
        _log(f"[dmm] queries={queries}")

        # 1) requests 快速路径
        for qword in queries:
            q = requests.utils.quote(qword, safe="")
            search_url = f"https://video.dmm.co.jp/anime/list/?key={q}"
            _log(f"[dmm] search url={search_url}")
            try:
                r = sess.get(search_url, timeout=(5, 15), verify=False)
                _log(f"[dmm] status={r.status_code}")
                if r.status_code != 200:
                    continue
                html = r.text
                if ("年齢認証" in html) or ("18歳以上" in html) or ("age_check" in html):
                    _log("[dmm] requests got age-check page")
                cid = _extract_cid(html)
                if cid:
                    _log(f"[dmm] requests cid={cid}")
                    break
            except Exception as e:
                _log(f"[dmm] requests err={e}")

        # 2) FlareSolverr 回退（DMM 可能 JS 渲染）
        if not cid and net.flaresolverr_enabled():
            _log("[dmm] requests no cid, fallback flaresolverr")
            for qword in queries:
                q = requests.utils.quote(qword, safe="")
                search_url = f"https://video.dmm.co.jp/anime/list/?key={q}"
                try:
                    solution = net.solve(search_url, max_timeout=60000)
                    net.apply_solution(sess, solution)
                    cid = _extract_cid(solution.html)
                    if not cid:
                        for href in re.findall(r'href="([^"]+)"', solution.html or ""):
                            match = re.search(r"id=([a-zA-Z0-9_]{6,})", href)
                            if match and _valid_cid(match.group(1)):
                                cid = match.group(1)
                                _log(f"[dmm] flaresolverr href={href}")
                                break
                    if cid:
                        _log(f"[dmm] flaresolverr cid={cid}")
                        break
                except Exception as e:
                    _log(f"[dmm] flaresolverr err={e}")

        if not cid:
            _log("[dmm] no content id found")
            try:
                if debug_dir:
                    _dmm_dump_html(debug_dir, html if 'html' in locals() else '')
                    _log("[dmm] dumped snippet -> dmm_last_page_snippet.html")
            except Exception as e:
                _log(f"[dmm] dump err={e}")
            return ""

        fanart_url = f"https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/{cid}/{cid}pl.jpg?f=webp"
        _log(f"[dmm] fanart url={fanart_url}")

        try:
            hd = sess.head(fanart_url, timeout=(4, 8), allow_redirects=True, verify=False)
            final_u = (getattr(hd, 'url', '') or '').lower()
            _log(f"[dmm] head status={hd.status_code} final={final_u}")
            if 'nowprinting' in final_u:
                _log("[dmm] head detected nowprinting placeholder")
                return ""
            if hd.status_code == 200:
                return fanart_url
        except Exception as e:
            _log(f"[dmm] head err={e}")

        try:
            gd = sess.get(fanart_url, timeout=(4, 10), stream=False, verify=False)
            final_u = (getattr(gd, 'url', '') or '').lower()
            ctype = (gd.headers.get('Content-Type') or '').lower()
            clen = int(gd.headers.get('Content-Length') or 0)
            body = gd.content or b''
            bsz = len(body)
            _log(f"[dmm] get status={gd.status_code} final={final_u} ctype={ctype} clen={clen} bsz={bsz}")
            if 'nowprinting' in final_u:
                _log("[dmm] get detected nowprinting placeholder")
                return ""
            if gd.status_code == 200 and (max(clen, bsz) > 0) and max(clen, bsz) < 50000:
                _log("[dmm] get detected tiny image, treat as placeholder")
                return ""
            if gd.status_code == 200:
                return fanart_url
        except Exception as e:
            _log(f"[dmm] get err={e}")

        return ""
    except Exception as e:
        _log(f"[dmm] fatal err={e}")
        return ""
    finally:
        if own_sess:
            try:
                sess.close()
            except Exception:
                pass


def fetch_animap_fanart_url(title: str, sess: Optional[requests.Session] = None,
                            progress: Optional[Callable[[Dict], None]] = None) -> str:
    """
    Ani-map 封面图抓取：
    1) GET https://ani-map.net/products/list?category_id=&tag_id=&name=<title>
    2) 解析页面中的 <img src="/html/upload/save_image/...jpg">
    3) 返回完整 URL: https://ani-map.net/html/upload/save_image/...
    """
    title = clean_title_suffix(title)
    if not title:
        return ""
    own=False
    if sess is None:
        sess=_make_session(); own=True
    try:
        q=requests.utils.quote(title, safe='')
        url=f"https://ani-map.net/products/list?category_id=&tag_id=&name={q}"
        r=sess.get(url, timeout=(5, 12), verify=False)
        r.raise_for_status()
        html=r.text

        # 优先匹配上传目录图片
        m = re.search(r"<img[^>]+src=['\"](/html/upload/save_image/[^'\"]+)['\"]", html, re.I)
        if not m:
            # 回退：任意save_image
            m = re.search(r"(/html/upload/save_image/[^'\"\\s>]+)", html, re.I)
        if not m:
            return ""
        src=m.group(1)
        if src.startswith('//'):
            return 'https:' + src
        if src.startswith('http'):
            return src
        return 'https://ani-map.net' + src
    except Exception as e:
        try:
            progress({"type": "log", "msg": f"[ani-map] err={e}"})
        except Exception:
            pass
        return ""
    finally:
        if own:
            try: sess.close()
            except Exception: pass

def download_video_for_item(item: Dict, out_dir: str, logger=print, progress_callback=None) -> Optional[str]:
    """
    下载一个条目的视频：
      1. 尽量拿到 watch 页里的直链 / m3u8（必要时重新抓一遍页面）
      2. 若能拿到 hembed 的 >=1080p mp4，直接用 requests 流式下载
      3. 若是其它直链 / m3u8，用 yt-dlp / ffmpeg 下
    """
    url = (item.get("url") or "").strip()
    title_fs = item.get("title_fs") or safe_name(item.get("title") or item.get("id") or "video")
    out_dir = os.path.abspath(out_dir)
    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"{title_fs}.mp4")

    def looks_like_direct(u: str) -> bool:
        return bool(re.search(r'\.(mp4|m3u8)(?:\?|$)', u or "", flags=re.I))

    def quality_from_url(u: str) -> int:
        m = re.search(r'(\d{3,4})p', u or "", re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        for q in (2160, 1440, 1080, 720, 480, 360):
            if u and str(q) in u:
                return q
        return 0

    def get_best_download_url_from_page(page_html: str) -> str:
        """
        从下载页 HTML 里抓出所有 mp4 链接，返回分辨率最高的那个。
        """
        urls = set()

        # 直接正则扫一遍 .mp4 链接
        for m in re.finditer(r'https?://[^\s"\']+?\.mp4[^\s"\']*', page_html):
            urls.add(m.group(0))

        # 再扫一遍 <a href="...mp4">
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+\.mp4[^"\']*)["\']', page_html, re.I):
            urls.add(m.group(1))

        best = ""
        best_q = 0
        for u in urls:
            q = quality_from_url(u)
            if q > best_q:
                best_q = q
                best = u

        return best

    def get_best_download_url_via_fetch(video_id: str) -> str:
        """取下载页最高画质直链：requests 优先，被拦截时由 FlareSolverr 解析。"""
        if not video_id:
            return ""

        download_url = f"https://hanime1.me/download?v={video_id}"
        logger(f"打开下载页获取直链：{download_url}")

        try:
            sess = _make_session()
            html2, status = _fetch_html(sess, download_url, referer="https://hanime1.me/")
            if status >= 400:
                logger(f"下载页访问失败（HTTP {status}）")
                return ""
            if not html2:
                logger("下载页 HTML 为空。")
                return ""

            best = get_best_download_url_from_page(html2)
            if best:
                logger(f"下载页解析到最高画质直链：{best} （{quality_from_url(best)}p）")
            else:
                logger("下载页未找到任何 mp4 直链。")
            return best
        except Exception as e:
            logger(f"打开下载页失败：{e}")
            return ""


    def ensure_stream_url() -> str:
        """
        优先用 item 里现成的 stream_url；
        没有的话先尝试 requests 抓 watch 页；
        再不行就重新请求一次，被 403 / 防爬拦截时由 FlareSolverr 拿渲染后的页面。
        """
        s = (item.get("stream_url") or "").strip()
        if looks_like_direct(s):
            return s

        page_url = url
        if not page_url:
            return ""

        # 1) 先试 requests（能成功就最快）
        try:
            sess = _make_session()
            r = sess.get(page_url, timeout=(5, 15), verify=False)
            r.raise_for_status()
            html = r.text
            s2 = find_stream_url(html) or ""
            if looks_like_direct(s2):
                item["stream_url"] = s2
                logger(f"重新解析到 stream_url（requests）：{s2[:80]}...")
                return s2
        except Exception as e:
            logger(f"重新获取 stream_url 失败（requests）：{e}")

        # 2) requests 被 403 / 防爬时，由 FlareSolverr 拿渲染后的页面
        try:
            sess2 = _make_session()
            logger(f"重新打开 watch 页获取 stream_url：{page_url}")
            html2, status = _fetch_html(sess2, page_url, referer="https://hanime1.me/")
            if status >= 400:
                logger(f"watch 页访问失败（HTTP {status}）")
            s3 = find_stream_url(html2) or ""
            if looks_like_direct(s3):
                item["stream_url"] = s3
                logger(f"重新解析到 stream_url：{s3[:80]}...")
                return s3
            logger("重新打开页面后仍未找到 stream_url。")

        except Exception as e:
            logger(f"获取 stream_url 失败：{e}")

        # 实在没拿到，就返回原值（大概率是空）
        return s


    # —— 先尽量拿到直链 / m3u8 ——
    direct = ""
    stream = ensure_stream_url()
    if looks_like_direct(stream):
        direct = stream
    elif looks_like_direct(url):
        direct = url
        
        # 如果当前只有 720 等较低分辨率，尝试从下载页再拿一次更高清的直链
    cur_q = quality_from_url(direct)
    if cur_q < 1080:
        # 优先用 item["id"]，没有的话从 url 的 ?v=xxx 里抠
        vid = (item.get("id") or "").strip()
        if not vid:
            m_vid = re.search(r"[?&]v=(\d+)", url)
            if m_vid:
                vid = m_vid.group(1)

        best_dl = get_best_download_url_via_fetch(vid) if vid else ""
        if best_dl:
            best_q = quality_from_url(best_dl)
            if best_q > cur_q:
                logger(f"使用下载页直链替换：{cur_q}p -> {best_q}p")
                direct = best_dl


    # ① 有 hembed >=1080p 的 mp4：自己用 requests 下（带进度回调）
    use_direct = bool(direct) and ".mp4" in direct.lower() and quality_from_url(direct) >= 1080 and "hembed.com" in direct
    if use_direct:
        filename_abs = os.path.join(out_dir, f"{title_fs}.mp4")
        logger(f"使用直链下载（{quality_from_url(direct)}p）：{direct}")

        for attempt in range(1, 4):
            try:
                sess = _make_session()
                headers = {}
                if url:
                    headers["Referer"] = url

                with sess.get(direct, headers=headers, stream=True,
                              timeout=(4, 60), verify=False) as r:
                    r.raise_for_status()

                    # 总大小（如果服务器有 Content-Length，就能算百分比）
                    total_bytes = int(r.headers.get("Content-Length") or 0)
                    done_bytes = 0
                    last_report = 0

                    ensure_dir(os.path.dirname(filename_abs) or ".")
                    with open(filename_abs, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 256):
                            if not chunk:
                                continue
                            f.write(chunk)
                            done_bytes += len(chunk)

                            # ★ 这里通知 GUI 更新进度条
                            if progress_callback:
                                # 每下载 ≥1MB 或刚好完成时汇报一次，避免太频繁
                                if (total_bytes and done_bytes - last_report >= 1 * 1024 * 1024) or (total_bytes and done_bytes == total_bytes):
                                    last_report = done_bytes
                                    try:
                                        progress_callback(done_bytes, total_bytes, filename_abs)
                                    except Exception:
                                        pass

                    if total_bytes and done_bytes != total_bytes:
                        raise IOError("下载长度与 Content-Length 不符")
                    # 下载结束再补一次 100%，防止刚好没触发
                    if progress_callback and total_bytes:
                        try:
                            progress_callback(total_bytes, total_bytes, filename_abs)
                        except Exception:
                            pass

                # 大小检查：小于 1MB 基本是错误页，重试
                if os.path.getsize(filename_abs) < 1 * 1024 * 1024:
                    logger(f"直链下载完成但文件太小，疑似异常（第 {attempt} 次），重试…")
                    os.remove(filename_abs)
                    time.sleep(2)
                    continue

                # 一切正常，返回文件路径
                return filename_abs

            except Exception as e:
                logger(f"直链下载异常（第 {attempt} 次）：{e}")
                try:
                    if os.path.exists(filename_abs):
                        os.remove(filename_abs)
                except Exception:
                    pass
                time.sleep(2)

        logger("直链连续多次失败，准备尝试其它方式…")


    # ② 还有直链（mp4/m3u8）：优先用 yt-dlp
    ytdlp = which("yt-dlp")
    if ytdlp and direct:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            part_path = out_path + ".part"
            if os.path.exists(part_path):
                os.remove(part_path)
        except Exception as e:
            logger(f"清理旧文件失败：{e}")

        cmd = [
            ytdlp, "-o", out_path,
            "--no-part", "--no-mtime",
            "--no-continue", "--force-overwrites",
            "--add-header", f"User-Agent:{net.current_ua(UA)}",
        ] + _proxy_cli_args("yt-dlp", referer=url)
        if url:
            cmd += ["--add-header", f"Referer:{url}"]
        cmd += [direct]
        logger(" ".join(cmd))
        try:
            subprocess.run(cmd, check=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
        except Exception as e:
            logger(f"yt-dlp(直链) 失败：{e}")

    # ③ yt-dlp 不行就试 ffmpeg
    ffm = which("ffmpeg")
    if ffm and direct:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        headers = f"User-Agent: {net.current_ua(UA)}\r\n"
        if url:
            headers += f"Referer: {url}\r\n"
        cmd = [ffm, "-y"] + _proxy_cli_args("ffmpeg") + ["-headers", headers, "-i", direct, "-c", "copy", out_path]
        logger(" ".join(cmd))
        try:
            subprocess.run(cmd, check=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
        except Exception as e:
            logger(f"ffmpeg(直链) 失败：{e}")

    logger("未找到可用的下载方式：下载页没有给出直链，yt-dlp 与 ffmpeg 均失败。")
    return None


# ---------------- 内部：图片下载（并发 + 复用会话） ----------------
def _download_image(sess: requests.Session, url: str, path: str, referer: str = "", force: bool = False) -> Tuple[str, bool, str]:
    contained_file(os.path.dirname(os.path.abspath(path)), path)
    if not url:
        return path, False, "download"
    if not force and os.path.exists(path) and os.path.getsize(path) > 0:
        return path, True, "skip"
    try:
        hs = {"Referer": referer} if referer else {}
        with sess.get(url, headers=hs, timeout=(4, 12), stream=False, verify=False) as r:
            r.raise_for_status()
            ensure_dir(os.path.dirname(path) or ".")
            data = r.content
            if not (data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")) or
                    (data.startswith(b"RIFF") and data[8:12] == b"WEBP")):
                raise ValueError("响应不是有效图片")
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(path) or ".", suffix=".tmp", delete=False) as f:
                temporary = f.name
                f.write(data)
            try:
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        return path, True, "download"
    except Exception:
        return path, False, "download"


def redownload_covers_only(year: int, month: int, out_root: str,
                           cover_site: str = "dmm",
                           progress: Optional[Callable[[Dict], None]] = None,
                           img_workers: int = 8,
                           items: Optional[List[Dict]] = None, force: bool = True) -> List[Dict]:
    """
    仅复下载 poster/fanart，不重写 NFO，不碰视频。
    依赖当月 JSON 条目（title/title_fs/cover_url/id）。
    """
    if progress is None:
        progress = lambda e: None

    out_root_abs = os.path.abspath(out_root)
    out_dir = ensure_dir(os.path.join(out_root_abs, f"{year}-{month:02d}"))

    json_path = os.path.join(out_dir, f"{year}-{month:02d}.json")
    if items is None and not os.path.exists(json_path):
        progress({"type": "log", "msg": f"未找到当月JSON：{json_path}"})
        return []

    try:
        if items is None:
            with open(json_path, "r", encoding="utf-8") as f:
                items = json.load(f)
    except Exception as e:
        progress({"type": "log", "msg": f"读取JSON失败：{e}"})
        return []

    session = _make_session()
    pool = ThreadPoolExecutor(max_workers=max(2, int(img_workers)))
    futures = []

    total = len(items)
    progress({"type": "start", "total": total})

    for i, it in enumerate(items, 1):
        title_raw = clean_title_suffix((it.get("title") or "").strip())
        title_fs = (it.get("title_fs") or safe_name(title_raw) or str(it.get("id") or i)).strip()
        cover_url = (it.get("cover_url") or "").strip()

        base = os.path.join(out_dir, title_fs)
        poster_path = base + "-poster.jpg"
        fanart_path = base + "-fanart.jpg"

        progress({"type": "item", "index": i, "total": total, "title": title_raw})

        # poster 直接用列表封面
        if cover_url:
            futures.append(pool.submit(_download_image, session, cover_url, poster_path, "https://hanime1.me/", force))
        else:
            progress({"type": "asset_error", "msg": "条目缺少封面地址", "path": poster_path})

        # fanart 按站点选择（dmm 优先；dmm 小图<50KB时回退 ani-map）
        fanart_url, fanart_source = pick_fanart_url(
            title_raw, session, cover_site=cover_site, min_dmm_bytes=50000, progress=progress,
            debug_dir=out_dir,
        )

        if not fanart_url:
            fanart_url = cover_url  # 兜底
            fanart_source = "cover"

        if fanart_url:
            progress({"type": "log", "msg": f"fanart站点[{fanart_source}] -> {fanart_url}"})
            futures.append(pool.submit(_download_image, session, fanart_url, fanart_path, "https://hanime1.me/", force))
        else:
            progress({"type": "asset_error", "msg": "条目缺少背景图地址", "path": fanart_path})

    for fut in as_completed(futures):
        try:
            path, ok, mode = fut.result()
            if ok:
                progress({"type": "save_poster", "path": path, "mode": mode})
            else:
                progress({"type": "asset_error", "msg": "图片下载失败", "path": path})
        except Exception as e:
            progress({"type": "asset_error", "msg": str(e)})

    pool.shutdown(wait=True)
    progress({"type": "done", "total": total, "out": out_dir})
    return items

# ---------------- 核心抓取（列表封面先并发 + 详情海报再并发） ----------------
def crawl_month(year: int, month: int, out_root: str,
                progress: Optional[Callable[[Dict], None]] = None,
                img_workers: int = 8,
                cover_site: str = "dmm",
                redownload_cover: bool = False,
                nfo_settings: Optional[Dict] = None) -> List[Dict]:

    if progress is None:
        progress = lambda e: None

    out_root_abs = os.path.abspath(out_root)
    out_dir = ensure_dir(os.path.join(out_root_abs, f"{year}-{month:02d}"))
    img_dir = ensure_dir(os.path.join(out_dir, "images"))

    session = _make_session()
    results: List[Dict] = []

    # 1) 列表页收集：requests 优先，Cloudflare 拦截时由 FlareSolverr 接管
    search_url = BASE_SEARCH.format(year=year, month=month)
    progress({"type": "log", "msg": f"打开月份页：{search_url}"})
    html, status = _fetch_html(session, search_url, referer="https://hanime1.me/", progress=progress)
    if status >= 400:
        raise RuntimeError(f"月份页访问失败（HTTP {status}），未获取任何作品")
    soup = BeautifulSoup(html, "html.parser")
    if not soup.select_one(LIST_WRAPPER):
        raise RuntimeError("月份页未正常加载，可能需要网站验证；请检查 FlareSolverr 设置或稍后重试")

    cards = soup.select(LIST_ITEMS)
    ids: List[str] = []
    list_info: Dict[str, Dict[str, str]] = {}
    for a in cards:
        href = a.get("href") or ""
        m = re.search(r'watch\?v=(\d+)', href)
        if not m:
            continue
        vid = m.group(1)
        ids.append(vid)
        tdiv = a.select_one("div.home-rows-videos-title")
        title_txt = tdiv.get_text(strip=True) if tdiv else ""
        im = a.select_one("img")
        img_url = ""
        if im:
            img_url = (im.get("src") or im.get("data-src") or "").strip()
            if (not img_url) and im.get("srcset"):
                parts = [s.strip().split()[0] for s in im.get("srcset").split(",") if s.strip()]
                if parts:
                    img_url = parts[-1]
        list_info[vid] = {"title": title_txt, "img": img_url, "href": href}
    ids = list(dict.fromkeys(ids))
    total = len(ids)
    progress({"type": "start", "total": total})
    if total == 0:
        raise RuntimeError(f"{year}-{month:02d} 网站月份页未返回作品，未生成图片和 NFO；请查看网站筛选结果。已有文件已保留")

    # 2) 先把 “列表封面 images/vid.jpg” 全部并发起来
    cover_futures = []
    pool = ThreadPoolExecutor(max_workers=max(2, int(img_workers)))
    for vid in ids:
        cover_url = (list_info.get(vid, {}) or {}).get("img") or ""
        if not cover_url:
            continue
        fp = os.path.join(img_dir, f"{vid}.jpg")
        if os.path.exists(fp) and os.path.getsize(fp) > 0 and not redownload_cover:
            continue
        cover_futures.append(pool.submit(_download_image, session, cover_url, fp, "https://hanime1.me/", redownload_cover))

    # 3) 逐条读取详情，同时把 “海报/背景 <title>-poster.jpg / -fanart.jpg” 丢进线程池
    for i, vid in enumerate(ids, 1):
        url = f"https://hanime1.me/watch?v={vid}"
        title_guess = (list_info.get(vid, {}) or {}).get("title") or ""
        progress({"type": "item", "index": i, "total": total, "id": vid, "title": title_guess})

        dhtml, dstatus = _fetch_html(session, url, referer="https://hanime1.me/", progress=progress)
        if dstatus >= 400 or not dhtml:
            progress({"type": "log", "msg": f"打开失败：{url}（HTTP {dstatus}）"})
            continue
        sp = BeautifulSoup(dhtml, "html.parser")
        title_node = sp.select_one(DETAIL_TITLE)
        if not title_node:
            progress({"type": "asset_error", "msg": f"条目 {vid} 未返回有效详情，未生成 NFO"})
            continue
        title_raw = clean_title_suffix(title_node.get_text(strip=True) or title_guess)

        # 发布者/制造商（用于文件名前缀）
        artist_name = ""
        artist_el = sp.select_one("#video-artist-name")
        if artist_el:
            artist_name = (artist_el.get_text(" ", strip=True) or "").strip()

        # 品牌/厂牌（页面若有独立字段优先；否则回退为 artist）
        label_name = ""
        for sel in ["#video-brand-name", "#video-label-name", "a[href*='search?query='][id*='brand']"]:
            _el = sp.select_one(sel)
            if _el:
                label_name = (_el.get_text(" ", strip=True) or "").strip()
                if label_name:
                    break
        if not label_name:
            label_name = artist_name

        file_title = title_raw
        if artist_name:
            file_title = f"[{artist_name}] {title_raw}"
        title_fs = safe_name(file_title) or vid

        # --- 剧情 + 中文标题（tagline 优先取页面自带中文） ---
        desc_el = sp.select_one(DETAIL_DESC)
        plot_raw = desc_el.get_text("\n", strip=True) if desc_el else ""

        # 页面内置的中文标题：video-description-panel 里第二行 div
        title_cn_panel = ""
        panel = sp.select_one(".video-description-panel")
        if panel:
            try:
                children = panel.select("> div")
            except Exception:
                children = [c for c in panel.children if getattr(c, "name", None) == "div"]
            for div in children:
                txt = div.get_text(" ", strip=True)
                if not txt:
                    continue
                if "观看次数" in txt:
                    continue
                if re.search(r"\d{4}-\d{2}-\d{2}", txt):
                    continue
                title_cn_panel = txt.strip()
                break

        # 翻译回退
        title_zh = title_cn_panel if title_cn_panel else translate_text_ja2zh(title_raw)
        plot_zh = translate_text_ja2zh(plot_raw)

        # --- 标签 ---
        tags = []
        for a in sp.select(DETAIL_TAG_ITEM):
            txt = a.get_text(" ", strip=True)
            txt = re.sub(r"\(\d+\)$", "", txt).strip()
            if txt:
                tags.append(txt)
        original_tags = list(tags)
        if nfo_settings is None:
            tags = filter_and_sort_tags(tags)
        else:
                    tags = filter_categories(original_tags, nfo_settings)

        cover_url = (list_info.get(vid, {}) or {}).get("img") or ""
        dmm_fanart_url, fanart_source = pick_fanart_url(
            title_raw, session, cover_site=cover_site, min_dmm_bytes=50000, progress=progress,
            debug_dir=out_dir,
        )
        stream = find_stream_url(dhtml)

        # --- rating / votes：优先隐藏域 likes/unlikes，回退按钮“99%(4112)” ---
        rating_percent = None
        votes = None
        like_form = sp.select_one("#video-like-form")
        if like_form:
            try:
                likes = int((like_form.select_one("input[name='likes-count']") or {}).get("value", "0"))
                unlikes = int((like_form.select_one("input[name='unlikes-count']") or {}).get("value", "0"))
                vote_total = likes + unlikes
                if vote_total > 0:
                    rating_percent = round(likes * 100 / vote_total)
                votes = vote_total
            except Exception:
                pass
        if rating_percent is None or votes is None:
            btn = sp.select_one("#video-like-btn .single-icon")
            if btn:
                txt = btn.get_text(" ", strip=True)
                m1 = re.search(r"(\d{1,3})\s*%", txt)
                m2 = re.search(r"\((\d{1,9})\)", txt)
                if rating_percent is None and m1:
                    rating_percent = int(m1.group(1))
                if votes is None and m2:
                    votes = int(m2.group(1))

        # --- 系列名 / 集数 ---
        series_name = ""
        episodes_count = None
        series_box = sp.select_one("#video-playlist-wrapper")
        if series_box:
            h4s = series_box.select("h4")
            if h4s:
                series_name = h4s[0].get_text(strip=True)
            if len(h4s) >= 2:
                m = re.search(r"(\d+)\s*个视频", h4s[1].get_text(" ", strip=True))
                if m:
                    episodes_count = int(m.group(1))

        # 用标题再做一次规范化，避免某些页面 h4 不带 OVA 前缀导致分组不一致
        series_from_title = re.sub(r"\s*[#＃]\s*\d+.*$", "", title_raw).strip()
        series_from_title = re.sub(r"\s*第\s*\d+\s*[話话巻卷].*$", "", series_from_title).strip()
        if series_from_title:
            series_name = series_from_title

        # --- 片长（分钟）：“現正播放/正在播放”卡片的 mm:ss ---
        runtime_min = None
        try:
            cur = None
            for card in sp.select("#playlist-scroll .related-watch-wrap"):
                txt = card.get_text(" ", strip=True)
                if "現正播放" in txt or "正在播放" in txt:
                    cur = card
                    break
            if cur:
                dur_el = cur.select_one(".card-mobile-duration.card-playlist-small")
                if dur_el:
                    dur_txt = dur_el.get_text(strip=True)
                    if re.match(r"^\d{1,2}:\d{2}$", dur_txt):
                        mm, ss = dur_txt.split(":")
                        runtime_min = int(mm) + (1 if int(ss) >= 30 else 0)
        except Exception:
            pass

        # --- premiered / year：从页面文本中找 YYYY-MM-DD ---
        premiered = ""
        try:
            candidate = sp.select_one(".video-description-panel") or sp.select_one(".video-details-wrapper")
            txt_all = candidate.get_text(" ", strip=True) if candidate else dhtml
            m = re.search(r"(\d{4}-\d{2}-\d{2})", txt_all)
            if m:
                premiered = m.group(1)
        except Exception:
            pass

        # --- 路径先定义，避免未赋值 ---
        base = os.path.join(out_dir, title_fs)
        poster_path = base + "-poster.jpg"
        fanart_path = base + "-fanart.jpg"

        # --- 选择用于 NFO 的 thumb/fanart 引用（优先本地文件名，其次 URL） ---
        thumb_ref = os.path.basename(poster_path) if (os.path.exists(poster_path) and os.path.getsize(poster_path) > 0) else (cover_url or "")
        fanart_src_url = dmm_fanart_url or cover_url
        fanart_ref = os.path.basename(fanart_path) if (os.path.exists(fanart_path) and os.path.getsize(fanart_path) > 0) else (fanart_src_url or "")

        # --- 写 NFO（标题原文-><title>；中文-><tagline>；plot 先中后日） ---
        write_movie_nfo(
            basepath=base,
            title_raw=title_raw,
            title_zh=title_zh,
            plot_raw=plot_raw,
            plot_zh=plot_zh,
            premiered=premiered,
            tags=tags,
            thumb=thumb_ref,
            mid=vid,
            rating=rating_percent,
            votes=votes,
            runtime_min=runtime_min,
            series_name=series_name,
            episodes_count=episodes_count,
            maker=artist_name,
            label=label_name,
            num=vid,
            release=premiered,
            tagline=title_zh,
            fanart=fanart_ref,
            nfo_settings=nfo_settings,
        )
        progress({"type": "save_nfo", "path": base + ".nfo"})

        item_futures = []
        # --- 并发下载 poster / fanart（都可用 cover_url） ---
        if cover_url and (redownload_cover or not (os.path.exists(poster_path) and os.path.getsize(poster_path) > 0)):
            item_futures.append(pool.submit(_download_image, session, cover_url, poster_path, url, redownload_cover))
        if fanart_src_url and (redownload_cover or not (os.path.exists(fanart_path) and os.path.getsize(fanart_path) > 0)):
            progress({"type": "log", "msg": f"fanart站点[{fanart_source or cover_site}] -> {fanart_src_url}"})
            item_futures.append(pool.submit(_download_image, session, fanart_src_url, fanart_path, url, redownload_cover))
        if not cover_url:
            progress({"type": "asset_error", "msg": "条目缺少封面地址", "path": poster_path})

        try:
            available_resolutions = read_download_resolutions(vid, request_timeout_ms(30000), session=session)
            if not available_resolutions:
                raise RuntimeError("下载页未返回可用画质")
        except Exception as exc:
            available_resolutions = []
            progress({"type": "log", "level": "warn", "msg": f"条目 {vid} 画质读取失败：{exc}"})
        record = {
            "id": vid,
            "url": url,
            "title": title_raw,
            "title_fs": title_fs,
            "artist": artist_name,
            "cover_url": cover_url,
            "tags": tags,
            "original_tags": original_tags,
            "available_resolutions": available_resolutions,
            "stream_url": stream,
        }
        results.append(record)
        publish_month_item(out_root_abs, year, month, record)
        # Finish this title's images before moving on to the next title.
        for future in as_completed(item_futures):
            try:
                path, ok, mode = future.result()
                progress({"type": "save_poster" if ok else "asset_error", "path": path,
                          "mode": mode, "msg": "图片下载失败" if not ok else "图片已保存"})
            except Exception as exc:
                progress({"type": "asset_error", "msg": str(exc)})
        progress({"type": "item_done", "index": i, "total": total, "id": vid, "title": title_raw})
        time.sleep(0.06)

    # 4) 等待所有图片任务完成（列表封面 + 海报/背景）
    for fut in as_completed(cover_futures):
        try:
            path, ok, mode = fut.result()
            if ok and mode != "skip":
                progress({"type": "save_poster", "path": path, "mode": "download"})
            elif not ok:
                progress({"type": "asset_error", "msg": "图片下载失败", "path": path})
        except Exception as e:
            progress({"type": "asset_error", "msg": str(e)})
    pool.shutdown(wait=True)

    # 结果排序（按 title_fs）
    results.sort(key=lambda x: ((x.get("title_fs") or "").casefold(), x.get("id") or ""))

    # CSV/JSON 汇总
    csv_path = os.path.join(out_dir, f"{year}-{month:02d}.csv")
    json_path = os.path.join(out_dir, f"{year}-{month:02d}.json")
    if not results:
        raise RuntimeError("没有成功读取任何条目，已保留现有月份索引")
    if len(results) < total:
        progress({"type": "asset_error", "msg": f"{total - len(results)} 个条目的详情读取失败，保留这些条目的旧索引"})
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                previous = json.load(f)
            finished_ids = {str(x.get("id")) for x in results}
            results.extend(x for x in previous if str(x.get("id")) not in finished_ids)
            results.sort(key=lambda x: ((x.get("title_fs") or "").casefold(), x.get("id") or ""))
        except (OSError, ValueError, TypeError):
            pass
    import io
    contained_file(out_dir, csv_path)
    contained_file(out_dir, json_path)
    with io.StringIO(newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "url", "title", "artist", "cover_url", "stream_url", "tags"])
        for x in results:
            w.writerow([x.get("id", ""), x.get("url", ""), x.get("title", ""), x.get("artist", ""),
                        x.get("cover_url", ""), x.get("stream_url", ""), " | ".join(x.get("tags", []))])
        csv_data = f.getvalue()
    atomic_write(csv_path, csv_data.encode("utf-8-sig"))
    atomic_write(json_path, json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8"))

    progress({"type": "done", "total": total, "csv": csv_path, "json": json_path, "out": out_dir})
    return results
