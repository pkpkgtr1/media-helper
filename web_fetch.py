"""Fetch HTML with plain requests, escalating to FlareSolverr only when blocked.

The caller keeps ownership of the requests.Session, so cookies obtained while
solving a challenge stay available for the following image/video requests.
"""
from __future__ import annotations

import requests

import flaresolverr_client

BLOCK_STATUS = (401, 403, 407, 429, 503)
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
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


def make_session():
    """Plain requests session with the headers the hanime pages expect."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    session.verify = False
    return session


def looks_blocked(status, html):
    if status in BLOCK_STATUS:
        return True
    head = (html or "")[:6000].lower()
    return any(marker in head for marker in BLOCK_MARKERS)


def apply_solution(session, solution):
    """Carry the solver's cookies and UA into the caller's session."""
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
    """Return (html, status); a challenge response is retried through FlareSolverr."""
    def note(message, level="warn"):
        if log:
            try:
                log(message, level)
            except TypeError:
                log(message)

    headers = {"Referer": referer} if referer else {}
    status, html = 0, ""
    try:
        response = session.get(url, headers=headers, timeout=(min(10, timeout), timeout),
                               verify=False)
        status, html = response.status_code, response.text or ""
    except requests.RequestException as exc:
        note(f"请求失败，将尝试 FlareSolverr：{url}（{exc}）")
    if not (allow_flaresolverr and flaresolverr_client.enabled()):
        return html, status
    if html and not looks_blocked(status, html):
        return html, status
    try:
        solution = flaresolverr_client.solve(url, max_timeout=max(15000, int(timeout * 1000)))
        apply_solution(session, solution)
        note(f"FlareSolverr 已解析：{url}（HTTP {solution.status}）", "info")
        return solution.html, solution.status
    except flaresolverr_client.FlareSolverrError as exc:
        note(f"FlareSolverr 未能解析 {url}：{exc}")
        return html, status
