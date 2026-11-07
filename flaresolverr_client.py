"""Optional FlareSolverr bridge for Cloudflare-protected pages.

The hanime path no longer drives a local browser. When a plain HTTP request is
rejected by a challenge page, the same URL can be handed to FlareSolverr, which
returns the rendered HTML plus the cookies/User-Agent that solved the challenge.
The switch and endpoint live in Settings → Advanced and reach the worker
through the environment, mirroring how the proxy is published.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

DEFAULT_URL = "http://192.168.11.253:8191/v1"
ENV_ENABLED = "MEDIA_FLARESOLVERR"
ENV_URL = "MEDIA_FLARESOLVERR_URL"
DEFAULT_MAX_TIMEOUT_MS = 60000


class FlareSolverrError(RuntimeError):
    """Raised when FlareSolverr is unreachable or refuses the request."""


@dataclass
class Solution:
    html: str = ""
    status: int = 0
    url: str = ""
    user_agent: str = ""
    cookies: list = field(default_factory=list)


def normalize_url(value):
    """Accept `host:8191`, `http://host:8191` or the full `.../v1` endpoint."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("FlareSolverr 地址需形如 http://192.168.11.253:8191/v1")
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/v1"):
        path = "/v1"
    else:
        raise ValueError("FlareSolverr 地址路径应为 /v1")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname}{port}{path}"


def configure_from_settings(settings):
    """Publish the switch for the current job; returns the endpoint or None."""
    settings = settings or {}
    enabled = bool(settings.get("flaresolverrEnabled"))
    url = normalize_url(settings.get("flaresolverrUrl") or DEFAULT_URL) if enabled else ""
    if enabled and url:
        os.environ[ENV_ENABLED] = "1"
        os.environ[ENV_URL] = url
        return url
    os.environ.pop(ENV_ENABLED, None)
    os.environ.pop(ENV_URL, None)
    return None


def enabled():
    return os.environ.get(ENV_ENABLED, "").strip().lower() in ("1", "true", "yes", "on")


def endpoint():
    return normalize_url(os.environ.get(ENV_URL) or DEFAULT_URL)


def solve(url, max_timeout=DEFAULT_MAX_TIMEOUT_MS, timeout=None, session=None):
    """Run one `request.get` through FlareSolverr and return the rendered page.

    `session` is accepted for symmetry with requests calls so callers can pass a
    proxy-configured session; FlareSolverr does its own fetching, so only the
    request to the solver itself is affected by it.
    """
    if not str(url or "").strip():
        raise FlareSolverrError("缺少需要 FlareSolverr 解析的地址")
    payload = {"cmd": "request.get", "url": str(url), "maxTimeout": int(max_timeout)}
    http = session or requests
    wait = timeout if timeout is not None else max_timeout / 1000 + 20
    try:
        response = http.post(endpoint(), json=payload,
                             headers={"Content-Type": "application/json"},
                             timeout=(10, wait))
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise FlareSolverrError(f"FlareSolverr 连接失败：{exc}") from exc
    except ValueError as exc:
        raise FlareSolverrError("FlareSolverr 返回内容不是 JSON") from exc
    if str(data.get("status", "")).lower() != "ok":
        raise FlareSolverrError(f"FlareSolverr 解析失败：{data.get('message') or data.get('status') or '未知错误'}")
    solution = data.get("solution") or {}
    try:
        status = int(solution.get("status") or 0)
    except (TypeError, ValueError):
        status = 0
    return Solution(html=solution.get("response") or "", status=status,
                    url=solution.get("url") or str(url),
                    user_agent=solution.get("userAgent") or "",
                    cookies=solution.get("cookies") or [])
