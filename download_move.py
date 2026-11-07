# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from lxml import html
import requests
import time
import re
import os
from webdriver_manager.chrome import ChromeDriverManager
import warnings, urllib3
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

# ====== 公共工具 ======
def safe_filename_for_windows(name: str) -> str:
    char_map = {
        '!': '！', '?': '？', '<': '＜', '>': '＞', ':': '：', '"': '＂',
        '|': '｜', '\\': '＼', '/': '／', '*': '＊'
    }
    for half, full in char_map.items():
        name = name.replace(half, full)
    safe = []
    for ch in name:
        safe.append('_' if 0 <= ord(ch) <= 31 else ch)
    return ''.join(safe).strip()[:180]

# ====== 解析下载页（稳健） ======
def download_move_info(page: str):
    """
    返回 (titles, urls)：
      titles: list[str]  —— 页内标题（可能为空）
      urls:   list[str]  —— 解析出的 .mp4/.m3u8 直链（可能为空）
    """
    titles, urls = [], []
    try:
        tree = html.fromstring(page)

        # 标题（保留你们原 XPath）
        titles = tree.xpath('//*[@id="content-div"]/div[1]/div[4]/div/div/h3/text()') or []

        # a / button / script 统扫
        cand = set()
        for sel in ["//a[@data-url]", "//a[@data-href]", "//a[@href]"]:
            for a in tree.xpath(sel) or []:
                for attr in ("data-url", "data-href", "href"):
                    v = a.get(attr)
                    if v:
                        cand.add(v)
        for b in tree.xpath("//button") or []:
            for attr in ("data-url", "data-href", "onclick"):
                v = b.get(attr)
                if v:
                    cand.add(v)
        for s in (tree.xpath("//script/text()") or []):
            cand.add(s)

        # 正则抽直链
        seen = set()
        urls = []
        for blob in cand:
            for m in re.findall(r'https?://[^\s\'"]+\.(?:mp4|m3u8)(?:[^\s\'"]*)', str(blob), flags=re.I):
                if m not in seen:
                    seen.add(m); urls.append(m)
    except Exception:
        pass
    return titles, urls

# ====== 全局单例浏览器（避免每次重启） ======
import atexit
from typing import Optional

_BROWSER = None
_SERVICE = None

def _build_chrome_options(headless: bool = True):
    opt = Options()
    if headless:
        # 先用新的 headless 模式；如果不稳定后面会在 _get_browser 里回退
        opt.add_argument("--headless=new")
        # 你也可以改成旧的：
        # opt.add_argument("--headless")
    opt.add_argument("--disable-gpu")
    opt.add_argument("--window-size=800,600")
    opt.add_argument("log-level=3")

    # 这些先保持关闭，后面如果需要再一点点加回去
    # opt.add_argument("--disable-blink-features=AutomationControlled")
    # opt.add_experimental_option("excludeSwitches", ["enable-automation"])
    # opt.add_experimental_option("useAutomationExtension", False)
    # opt.page_load_strategy = "eager"

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    opt.add_argument(f"--user-agent={UA}")
    return opt

def _get_browser():
    global _BROWSER, _SERVICE
    if _BROWSER is not None:
        return _BROWSER

    _SERVICE = Service(ChromeDriverManager().install())

    # 先尝试“无头”模式
    try:
        _BROWSER = webdriver.Chrome(service=_SERVICE, options=_build_chrome_options(headless=True))
    except Exception as e:
        print(f"[download_move] headless 模式启动失败，改用有窗口模式：{e}")
        # 回退到有窗口（保证功能可用）
        _BROWSER = webdriver.Chrome(service=_SERVICE, options=_build_chrome_options(headless=False))

    if os.environ.get("MEDIA_REQUEST_TIMEOUT"):
        _BROWSER.set_page_load_timeout(float(os.environ["MEDIA_REQUEST_TIMEOUT"]))

    def _cleanup():
        try:
            if _BROWSER:
                _BROWSER.quit()
        except Exception:
            pass

    atexit.register(_cleanup)
    return _BROWSER


# ====== 快速直抓（无需浏览器） ======
def _extract_urls_via_requests(download_page_url: str, referer: Optional[str] = None):
    try:
        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        hs = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        if referer:
            hs["Referer"] = referer
        r = requests.get(download_page_url, headers=hs, timeout=8, verify=False)
        if r.status_code != 200 or not r.text:
            return [], []
        page = r.text
        titles, urls = download_move_info(page)
        if urls:
            return titles, urls
        # 再正则兜底
        seen = set()
        urls = [u for u in re.findall(r'https?://[^\s\'"]+\.(?:mp4|m3u8)(?:[^\s\'"]*)', page, flags=re.I)
                if not (u in seen or seen.add(u))]
        return titles, urls
    except Exception:
        return [], []

# ====== 带回调的统一下载器（支持 Referer） ======
def download_file(lf_id, NY, url, filename=None, progress_callback=None, referer=None):
    """
    下载单个文件；progress_callback(downloaded_bytes, total_bytes, filename)
    """
    import traceback
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    try:
        base_dir = os.path.dirname(__file__)
        if filename is None:
            filename = url.split("/")[-1]
        if not os.path.isabs(filename):
            target_dir = os.path.join(base_dir, str(NY))
            os.makedirs(target_dir, exist_ok=True)
            filename = os.path.join(target_dir, safe_filename_for_windows(filename))

        UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

        sess = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5,
                      status_forcelist=(500, 502, 503, 504),
                      allowed_methods=["GET"])
        sess.mount("http://", HTTPAdapter(max_retries=retry))
        sess.mount("https://", HTTPAdapter(max_retries=retry))

        headers = {"User-Agent": UA, "Accept": "*/*"}
        headers["Referer"] = referer or "https://hanime1.me/"
        resp = sess.get(url, stream=True, timeout=(10, 60), verify=False, headers=headers)
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", 0)) if resp.headers.get("Content-Length") else 0
        downloaded = 0
        last_pct = -1

        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    try:
                        progress_callback(downloaded, total, filename)
                    except Exception:
                        pass

                if total > 0:
                    pct = int(downloaded * 100 / total)
                    if pct != last_pct:
                        last_pct = pct
                        mb_d = downloaded / (1024 * 1024)
                        mb_t = total / (1024 * 1024)
                        print("\r[%.1f / %.1f MB] (%3d%%) %s" %
                              (mb_d, mb_t, pct, os.path.basename(filename)), end="", flush=True)
        if total > 0:
            print()
        if downloaded == 0 or (total and downloaded != total):
            raise IOError("下载文件为空或长度不完整")

        return True

    except Exception as e:
        print(f"下载失败：{e}")
        traceback.print_exc()
        return False

# ====== 解析下载页 → 选择最高清直链 → 下载 ======
def download_html(LF_id, NY, progress_callback=None, out_dir=None):
    """
    打开下载页，解析直链并下载到 ./tmp/<YYYYMM>/ 下。
    优先 requests 快速解析；不行再复用全局 Selenium（避免每条重启导致 5–10s 延迟）。
    """
    def _emit(cb, percent, text):
        if cb:
            try:
                cb(percent, text)
            except Exception:
                pass

    base_dir = os.path.dirname(__file__)
    tmp_dir = os.path.abspath(out_dir) if out_dir else os.path.join(base_dir, "tmp", str(NY))
    os.makedirs(tmp_dir, exist_ok=True)

    download_page_url = f"https://hanime1.me/download?v={LF_id}"
    _emit(progress_callback, 0, f"准备下载 {LF_id}-{NY} …")

    # 0) 快速路径：不用浏览器，直接 requests 抓下载页 HTML 再解析
    titles, urls = _extract_urls_via_requests(download_page_url, referer="https://hanime1.me/")

    if not urls:
        # 1) 兜底：用 Selenium 打开下载页再解析
        br = _get_browser()
        br.get(download_page_url)

        # 等页面加载 & 脚本跑完——这里时间不要太短，否则某些资源还没挂上去
        time.sleep(2.0)
        try:
            br.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        time.sleep(1.0)

        page = br.page_source
        _emit(progress_callback, 5, "已打开下载页（Selenium）")

        # 先用 lxml/正则综合解析
        titles, urls = download_move_info(page)
        if not urls:
            # 再从 a/button/script 的 JS 里兜底提取一次
            blobs = []
            try:
                blobs = br.execute_script("""
                    const out = [];
                    const pick = el => [el.getAttribute('href'), el.getAttribute('data-url'),
                                        el.getAttribute('data-href'), el.getAttribute('onclick')];
                    document.querySelectorAll('a,button').forEach(el => { pick(el).forEach(v => v && out.push(v)); });
                    document.querySelectorAll('script').forEach(s => s.textContent && out.push(s.textContent));
                    return out;
                """) or []
            except Exception:
                pass
            if blobs:
                seen = set()
                urls_js = re.findall(
                    r'https?://[^\s\'"]+\.(?:mp4|m3u8)(?:[^\s\'"]*)',
                    "\n".join(map(str, blobs)),
                    flags=re.I
                )
                urls = [u for u in urls_js if not (u in seen or seen.add(u))]

    if not urls:
        print("未解析到可用下载链接。")
        return

    # 选择最高清：优先 2160/1440/1080…；同清晰度优先 mp4（更稳）
    def _quality(u: str) -> int:
        m = re.search(r'(\d{3,4})p', u, re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        for q in (2160, 1440, 1080, 720, 480, 360):
            if str(q) in u:
                return q
        return 0

    def _sort_key(u: str):
        # -质量（越大越前） + mp4 优先
        return (-_quality(u), 0 if u.lower().endswith(".mp4") else 1)

    urls_sorted = sorted(set(urls), key=_sort_key)
    file_url = urls_sorted[0]

    # 目标绝对文件名（保存在 tmp/NY 下）
    title_text = (titles[0].strip() if titles else str(LF_id)) or str(LF_id)
    name_safe = safe_filename_for_windows(title_text) or str(LF_id)
    out_abs = os.path.join(tmp_dir, f"{name_safe}.mp4")

    _emit(progress_callback, 10, "开始下载…")
    success = download_file(
        LF_id,
        NY,
        file_url,
        filename=out_abs,
        progress_callback=progress_callback,
        referer=download_page_url,
    )
    if not success:
        return None
    _emit(progress_callback, 100, f"已保存：{out_abs}")
    return out_abs


