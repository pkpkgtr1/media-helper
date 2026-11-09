"""HTTP 层：自定义 UA、FlareSolverr 桥接与「先直连、遇盾再解析」的抓取入口。

三个原模块（user_agent / flaresolverr_client / web_fetch）说的是同一件事——
「这次请求用哪个 UA、走不走代理、被盾拦了怎么办」——所以合并成一处，
调用方只需要 `net.make_session()` 和 `net.fetch_html()`。

开关、地址与会话 ID 来自「设置 → 高级」，由 `configure()` 发布到环境变量，
worker 子进程与主进程读同一份配置，做法与代理一致。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

# ---------------- User-Agent ----------------

UA_ENV = "MEDIA_USER_AGENT"
UA_MAX_LENGTH = 512
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def normalize_ua(value):
    """折叠空白（头部不允许换行），保留原值。"""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def ua_from_settings(settings):
    """当前生效的自定义 UA；留空或启用 FlareSolverr 时返回空串（用默认值）。"""
    if (settings or {}).get("flaresolverrEnabled"):
        return ""
    return normalize_ua((settings or {}).get("userAgent"))


def current_ua(default=DEFAULT_UA):
    """任务内的取值入口：环境变量优先，否则用模块内置的默认 UA。"""
    return os.environ.get(UA_ENV, "").strip() or default


# ---------------- FlareSolverr ----------------

DEFAULT_FLARESOLVERR_URL = "http://192.168.11.253:8191/v1"
ENV_ENABLED = "MEDIA_FLARESOLVERR"
ENV_URL = "MEDIA_FLARESOLVERR_URL"
ENV_SESSION = "MEDIA_FLARESOLVERR_SESSION"
DEFAULT_MAX_TIMEOUT_MS = 60000
MAX_SESSION_LENGTH = 128
BLOCK_STATUS = (401, 403, 407, 429, 503)
BLOCK_MARKERS = (
    "just a moment",
    "cf-challenge",
    "cf_chl_opt",
    "cf_chl_",
    "checking your browser",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "ddos-guard",
    "enable javascript and cookies to continue",
)


class FlareSolverrError(RuntimeError):
    """FlareSolverr 不可达或拒绝了请求。"""


@dataclass
class Solution:
    html: str = ""
    status: int = 0
    url: str = ""
    user_agent: str = ""
    cookies: list = field(default_factory=list)


def normalize_flaresolverr_url(value):
    """接受 `host:8191`、`http://host:8191` 或完整的 `.../v1`。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("FlareSolverr 地址需形如 http://192.168.11.253:8191/v1")
    path = (parsed.path or "").rstrip("/")
    if path not in ("", "/v1"):
        raise ValueError("FlareSolverr 地址路径应为 /v1")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname}{port}/v1"


def normalize_session(value):
    """会话名会进入 JSON 载荷，保持单行且限长。"""
    if not isinstance(value, str):
        return ""
    text = "".join(value.split())
    if len(text) > MAX_SESSION_LENGTH:
        raise ValueError(f"FlareSolverr 会话 ID 不能超过 {MAX_SESSION_LENGTH} 个字符")
    return text


def configure(settings):
    """把当前任务需要的开关发布到环境变量；返回生效的 FlareSolverr 地址或 None。"""
    settings = settings or {}
    enabled = bool(settings.get("flaresolverrEnabled"))
    url = normalize_flaresolverr_url(settings.get("flaresolverrUrl") or DEFAULT_FLARESOLVERR_URL) if enabled else ""
    if enabled and url:
        os.environ[ENV_ENABLED] = "1"
        os.environ[ENV_URL] = url
        name = normalize_session(settings.get("flaresolverrSession") or "")
        if name:
            os.environ[ENV_SESSION] = name
        else:
            os.environ.pop(ENV_SESSION, None)
    else:
        os.environ.pop(ENV_ENABLED, None)
        os.environ.pop(ENV_URL, None)
        os.environ.pop(ENV_SESSION, None)
    # 启用 FlareSolverr 后页面由它的浏览器请求，自定义 UA 反而会被校验拒绝。
    agent = ua_from_settings(settings)
    if agent:
        os.environ[UA_ENV] = agent
    else:
        os.environ.pop(UA_ENV, None)
    return url or None


def flaresolverr_enabled():
    return os.environ.get(ENV_ENABLED, "").strip().lower() in ("1", "true", "yes", "on")


def flaresolverr_endpoint():
    return normalize_flaresolverr_url(os.environ.get(ENV_URL) or DEFAULT_FLARESOLVERR_URL)


def session_name():
    return os.environ.get(ENV_SESSION, "").strip()


def _post(payload, http=None, timeout=None):
    """发送一条命令并返回解码后的 JSON。"""
    try:
        response = (http or requests).post(flaresolverr_endpoint(), json=payload,
                                           headers={"Content-Type": "application/json"},
                                           timeout=timeout or (10, 90))
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise FlareSolverrError(f"FlareSolverr 连接失败：{exc}") from exc
    except ValueError as exc:
        raise FlareSolverrError("FlareSolverr 返回内容不是 JSON") from exc


def create_session(name, http=None, timeout=None):
    """创建会话（已存在则视为成功），返回会话名。"""
    name = normalize_session(name)
    if not name:
        raise FlareSolverrError("缺少 FlareSolverr 会话 ID")
    data = _post({"cmd": "sessions.create", "session": name}, http=http, timeout=timeout)
    status = str(data.get("status", "")).lower()
    message = str(data.get("message") or "")
    if status != "ok" and "already" not in message.lower():
        raise FlareSolverrError(f"FlareSolverr 会话创建失败：{message or status or '未知错误'}")
    return name


def _solution_of(data, fallback_url):
    solution = data.get("solution") or {}
    try:
        status = int(solution.get("status") or 0)
    except (TypeError, ValueError):
        status = 0
    return Solution(html=solution.get("response") or "", status=status,
                    url=solution.get("url") or fallback_url,
                    user_agent=solution.get("userAgent") or "",
                    cookies=solution.get("cookies") or [])


def solve(url, max_timeout=DEFAULT_MAX_TIMEOUT_MS, timeout=None, session=None):
    """通过 FlareSolverr 执行一次 `request.get` 并返回渲染后的页面。

    `session` 是访问 FlareSolverr 自身用的 requests 会话（因此代理对它生效）；
    FlareSolverr 会话 ID 来自设置，由 `session_name()` 提供。
    """
    if not str(url or "").strip():
        raise FlareSolverrError("缺少需要 FlareSolverr 解析的地址")
    http = session or requests
    wait = timeout if timeout is not None else max_timeout / 1000 + 20
    name = session_name()
    payload = {"cmd": "request.get", "url": str(url), "maxTimeout": int(max_timeout)}
    if name:
        payload["session"] = name
    data = _post(payload, http=http, timeout=(10, wait))
    message = str(data.get("message") or "")
    if str(data.get("status", "")).lower() != "ok" and name and "session" in message.lower():
        # 会话可能被服务端清理过：显式建一次再重试，避免整段任务失败。
        create_session(name, http=http, timeout=(10, 60))
        data = _post(payload, http=http, timeout=(10, wait))
        message = str(data.get("message") or "")
    if str(data.get("status", "")).lower() != "ok":
        raise FlareSolverrError(f"FlareSolverr 解析失败：{message or data.get('status') or '未知错误'}")
    return _solution_of(data, str(url))


# ---------------- 抓取 ----------------

def make_session(retries=True, headers=None):
    """带站点期望头部的 requests 会话；`retries` 为连接池/重试适配器开关。"""
    session = requests.Session()
    if retries:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=Retry(
            total=3, backoff_factor=0.25, status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"), raise_on_status=False))
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": current_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
        "Connection": "keep-alive",
        **(headers or {}),
    })
    session.verify = False
    return session


def looks_blocked(status, html):
    if status in BLOCK_STATUS:
        return True
    head = (html or "")[:6000].lower()
    return any(marker in head for marker in BLOCK_MARKERS)


def apply_solution(session, solution):
    """把解析得到的 Cookie 与 UA 带回调用方的会话。"""
    for cookie in solution.cookies or []:
        try:
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie.get("domain") or None,
                                path=cookie.get("path") or "/")
        except (KeyError, TypeError, ValueError):
            continue
    if solution.user_agent:
        try:
            session.headers["User-Agent"] = solution.user_agent
        except (AttributeError, TypeError):
            pass


def fetch_html(session, url, referer=None, timeout=30, allow_flaresolverr=True, log=None):
    """返回 (html, status)；遇到拦截页时改用 FlareSolverr 重试一次。"""
    def note(message, level="warn"):
        if log:
            try:
                log(message, level)
            except TypeError:
                log(message)

    headers = {"Referer": referer} if referer else {}
    status, html = 0, ""
    try:
        response = session.get(url, headers=headers, timeout=(min(10, timeout), timeout), verify=False)
        status, html = response.status_code, response.text or ""
    except requests.RequestException as exc:
        note(f"请求失败，将尝试 FlareSolverr：{url}（{exc}）")
    if not (allow_flaresolverr and flaresolverr_enabled()):
        return html, status
    if html and not looks_blocked(status, html):
        return html, status
    try:
        solution = solve(url, max_timeout=max(15000, int(timeout * 1000)))
        apply_solution(session, solution)
        note(f"FlareSolverr 已解析：{url}（HTTP {solution.status}）", "info")
        return solution.html, solution.status
    except FlareSolverrError as exc:
        note(f"FlareSolverr 未能解析 {url}：{exc}")
        return html, status
