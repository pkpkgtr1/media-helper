"""Local library/configuration storage, independent of crawler dependencies."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

from flaresolverr_client import DEFAULT_URL as DEFAULT_FLARESOLVERR_URL
from flaresolverr_client import normalize_url as normalize_flaresolverr_url

APP_ROOT = Path(__file__).resolve().parent

# Playwright 目录内的浏览器布局，按平台排列，用于检测与错误提示。
BROWSER_PATTERNS = (
    "chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell",
    "chromium-*/chrome-linux*/chrome",
    "chromium_headless_shell-*/chrome-headless-shell-win*/chrome-headless-shell.exe",
    "chromium-*/chrome-win*/chrome.exe",
    "chromium-*/Chromium.app/Contents/MacOS/Chromium",
    "chromium-*/chrome-mac*/Chromium Framework.framework/Versions/Current/Chromium",
)


def browser_roots():
    """Directories that may hold Playwright browsers, project bundle first."""
    roots = [APP_ROOT / "ms-playwright"]
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured and configured != "0":
        candidate = Path(configured).expanduser()
        if candidate not in roots:
            roots.append(candidate)
    home_values = [os.environ.get("HOME", ""), os.environ.get("USERPROFILE", "")]
    try:
        home_values.append(str(Path.home()))
    except RuntimeError:
        pass
    for value in home_values:
        if not value:
            continue
        candidate = Path(value).expanduser() / ".cache" / "ms-playwright"
        if candidate not in roots:
            roots.append(candidate)
    # Windows 默认缓存在 %LOCALAPPDATA%\ms-playwright，与 Linux 的 ~/.cache 不同；
    # 漏掉它会让 `playwright install` 默认安装的浏览器不被发现，重复下载。
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        candidate = Path(local_appdata).expanduser() / "ms-playwright"
        if candidate not in roots:
            roots.append(candidate)
    return roots


def find_browser_executable(roots=None):
    """First Playwright browser binary found, or None. Project bundle wins."""
    for root in roots if roots is not None else browser_roots():
        if not root.is_dir():
            continue
        for pattern in BROWSER_PATTERNS:
            for match in sorted(root.glob(pattern)):
                if match.is_file() and match.stat().st_size > 0:
                    return match
    return None


def browser_install_hint():
    """One copy-paste command that installs chromium into the project bundle."""
    if os.name == "nt":
        return ('PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="$PWD\\ms-playwright"; '
                '.\\.venv\\Scripts\\python.exe -m playwright install chromium '
                '（CMD: set "PLAYWRIGHT_BROWSERS_PATH=%CD%\\ms-playwright" && '
                '.venv\\Scripts\\python.exe -m playwright install chromium）')
    return 'PLAYWRIGHT_BROWSERS_PATH="$PWD/ms-playwright" ./.venv/bin/python -m playwright install chromium'


def configure_browser_env():
    """Point Playwright at a bundle that really contains a browser, if possible."""
    bundled = APP_ROOT / "ms-playwright"
    if bundled.is_dir() and find_browser_executable([bundled]):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)
        return bundled
    return None


PROXY_SCHEMES = ("http", "https", "socks4", "socks5")


def proxy_from_settings(settings):
    """Normalized proxy URL from settings; returns None when disabled or empty."""
    if not isinstance(settings, dict) or not settings.get("proxyEnabled"):
        return None
    value = str(settings.get("proxyUrl") or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        parsed = urlparse(value)
    except ValueError:
        raise ValueError("代理地址无效")
    if parsed.scheme.lower() not in PROXY_SCHEMES or not parsed.hostname:
        raise ValueError(f"代理地址需形如 http://用户:密码@主机:端口 或 socks5://主机:端口（{value}）")
    if not parsed.port:
        raise ValueError("代理地址必须包含端口，例如 http://192.168.11.2:7893")
    return value


def proxy_bypass_hosts(settings=None):
    """Hosts that must stay direct even with a proxy on (the app's own loopback API)."""
    hosts = ["127.0.0.1", "localhost", "::1"]
    for value in str((settings or {}).get("proxyBypass") or "").replace(",", ";").split(";"):
        value = value.strip().lower().lstrip(".")
        if value and value not in hosts:
            hosts.append(value)
    return hosts


def mask_proxy(value):
    """Hide credentials in a proxy URL for logs and UI: scheme://***@host:port."""
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return "***"
    if not parsed.username:
        return value
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    return f"{parsed.scheme}://***@{netloc}"


def playwright_proxy(value):
    """Convert a proxy URL into Playwright's context `proxy` option (auth-safe split)."""
    parsed = urlparse(value)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    option = {"server": server, "bypass": ",".join(proxy_bypass_hosts())}
    if parsed.username:
        option["username"] = unquote(parsed.username)
    if parsed.password:
        option["password"] = unquote(parsed.password)
    return option


def configure_proxy_env(settings):
    """Publish the effective proxy to child tools via env; returns URL or None.

    requests/yt-dlp read standard proxy env automatically; Chromium launched by
    Playwright does not, so the crawler uses MEDIA_PROXY through
    playwright_proxy() instead. The original process env is left untouched when
    the switch is off so direct-mode jobs never inherit stale values.
    """
    url = proxy_from_settings(settings)
    names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "MEDIA_PROXY", "MEDIA_PROXY_BYPASS")
    lower = tuple(name.lower() for name in names)
    if not url:
        for name in names + lower:
            os.environ.pop(name, None)
        return None
    no_proxy = ",".join(proxy_bypass_hosts(settings))
    values = {"HTTP_PROXY": url, "HTTPS_PROXY": url, "ALL_PROXY": url, "NO_PROXY": no_proxy,
              "MEDIA_PROXY": url, "MEDIA_PROXY_BYPASS": no_proxy}
    for name in names + lower:
        os.environ.pop(name, None)
    for name, value in values.items():
        os.environ[name] = value
        os.environ[name.lower()] = value
    return url


def normalize_category(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).split())


def default_settings():
    categories = [{**row, "checked": False} for row in official_categories()]
    return dict(outputRoot=str(APP_ROOT / "media"), openAfter=False, posterMode="download",
                coverSite="dmm", redownloadCover=False, existingVideo="skip", retries=3,
                downloadInterval=5000, requestTimeout=30, writeTags=True, writeGenres=True,
                unseenDefault="exclude", proxyEnabled=False, proxyUrl="",
                flaresolverrEnabled=False, flaresolverrUrl=DEFAULT_FLARESOLVERR_URL,
                hgSaveRoot=str(APP_ROOT / "media" / "黄果短剧"), hgIntervalValue=6, hgIntervalUnit="hour",
                hgConcurrent=4, hgRetries=2, hgRetryInterval=30,
                categories=categories)


def official_categories():
    """Only the site's content-tag modal is a source of selectable metadata."""
    return json.loads((APP_ROOT / "hanime_content_tags.json").read_text(encoding="utf-8"))["categories"]


def catalog_aliases():
    return {normalize_category(alias).casefold(): row["name"]
            for row in official_categories() for alias in [row["name"], *row.get("aliases", [])]}


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("设置必须是对象")
    result = default_settings()
    result.update({k: v for k, v in value.items() if k in result})
    if not isinstance(result["outputRoot"], str) or not result["outputRoot"].strip():
        raise ValueError("输出目录不能为空")
    result["outputRoot"] = str(Path(result["outputRoot"].strip()).expanduser().resolve())
    for key, allowed in {"posterMode": ("download", "screenshot", "both"), "coverSite": ("dmm", "animap", "auto"),
                         "existingVideo": ("skip", "redownload"), "unseenDefault": ("keep", "exclude")}.items():
        if result[key] not in allowed:
            raise ValueError(f"无效设置：{key}")
    for key in ("openAfter", "redownloadCover", "writeTags", "writeGenres", "proxyEnabled", "flaresolverrEnabled"):
        if not isinstance(result[key], bool):
            raise ValueError(f"无效开关：{key}")
    result["posterMode"] = "download"  # 浏览器截图已移除，旧设置统一降级为图片下载
    if not isinstance(result["proxyUrl"], str):
        raise ValueError("代理地址必须是文本")
    result["proxyUrl"] = result["proxyUrl"].strip()
    if result["proxyEnabled"] and not result["proxyUrl"]:
        raise ValueError("开启代理时必须填写代理地址")
    if result["proxyUrl"]:
        proxy_from_settings(dict(proxyEnabled=True, proxyUrl=result["proxyUrl"]))
    if not isinstance(result["flaresolverrUrl"], str):
        raise ValueError("FlareSolverr 地址必须是文本")
    result["flaresolverrUrl"] = result["flaresolverrUrl"].strip() or DEFAULT_FLARESOLVERR_URL
    try:
        result["flaresolverrUrl"] = normalize_flaresolverr_url(result["flaresolverrUrl"])
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if result["flaresolverrEnabled"] and not result["flaresolverrUrl"]:
        raise ValueError("开启 FlareSolverr 时必须填写地址")
    if result["hgIntervalUnit"] not in ("minute", "hour", "day"):
        raise ValueError("无效设置：hgIntervalUnit")
    if not isinstance(result["hgSaveRoot"], str):
        raise ValueError("黄果默认保存路径必须是文本")
    result["hgSaveRoot"] = result["hgSaveRoot"].strip()
    for key, lo, hi in (("retries", 0, 20), ("downloadInterval", 0, 600000), ("requestTimeout", 1, 3600),
                        ("hgIntervalValue", 1, 9999), ("hgConcurrent", 1, 8),
                        ("hgRetries", 0, 5), ("hgRetryInterval", 0, 3600)):
        if type(result[key]) is not int or not lo <= result[key] <= hi:
            raise ValueError(f"{key} 必须是 {lo}–{hi} 之间的整数")
    if not isinstance(result["categories"], list):
        raise ValueError("分类规则必须是列表")
    categories, seen = [], set()
    for rule in result["categories"]:
        if not isinstance(rule, dict) or not isinstance(rule.get("name"), str) or type(rule.get("checked")) is not bool:
            raise ValueError("分类规则需要名称和勾选状态")
        name = normalize_category(rule["name"])
        if not name or len(name) > 200 or name.casefold() in seen:
            raise ValueError("分类名称为空、重复或过长")
        seen.add(name.casefold())
        categories.append(dict(name=name, checked=rule["checked"]))
    aliases = catalog_aliases()
    selected = {}
    for rule in categories:
        canonical = aliases.get(rule["name"].casefold())
        if canonical:
            # If old settings contain both spellings, an explicit exclusion wins.
            selected[canonical] = selected.get(canonical, True) and rule["checked"]
    result["categories"] = [{**row, "checked": selected.get(row["name"], False)} for row in official_categories()]
    result.update(writeTags=True, writeGenres=True, unseenDefault="exclude")
    return result


def filter_categories(tags, settings):
    aliases = catalog_aliases()
    rules = {}
    for rule in settings.get("categories", []):
        name = aliases.get(normalize_category(rule["name"]).casefold())
        if name:
            rules[name] = rules.get(name, True) and rule["checked"]
    seen, result = set(), []
    for value in tags or []:
        name = aliases.get(normalize_category(value).casefold())
        key = name
        if name and key not in seen and rules.get(key, False):
            result.append(name)
            seen.add(key)
    return sorted(result, key=lambda s: (s.casefold(), s))


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def publish_month_item(output_root, year, month, item):
    """Publish one finished record without losing other records on interruption."""
    directory = month_directory(output_root, year, month)
    safe_base(directory, item["title_fs"])
    path = contained_file(directory, directory / f"{year}-{month:02d}.json")
    previous = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else []
    if not isinstance(previous, list) or any(not isinstance(row, dict) for row in previous):
        raise ValueError("月份索引格式错误，未覆盖原文件")
    rows = [row for row in previous if str(row.get("id")) != str(item.get("id"))]
    rows.append(item)
    rows.sort(key=lambda row: str(row.get("title_fs", "")).casefold())
    atomic_write(path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))


def publish_month_resolution(output_root, year, month, item, values):
    directory = month_directory(output_root, year, month)
    path = contained_file(directory, directory / f"{year}-{month:02d}.json")
    rows = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("月份索引格式错误，未覆盖原文件")
    found = next((row for row in rows if str(row.get("id")) == str(item.get("id"))), None)
    if found is None:
        found = {k: v for k, v in item.items() if not k.startswith("_")}
        safe_base(directory, found["title_fs"])
        rows.append(found)
    found["available_resolutions"] = values
    atomic_write(path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))


def month_directory(output_root, year, month):
    if type(year) is not int or not 1900 <= year <= 2200 or type(month) is not int or not 1 <= month <= 12:
        raise ValueError("年份或月份无效")
    if not isinstance(output_root, str) or not output_root.strip():
        raise ValueError("输出目录不能为空")
    root = Path(output_root).expanduser().resolve()
    directory = root / f"{year}-{month:02d}"
    if not directory.resolve().is_relative_to(root):
        raise ValueError("月份目录指向媒体根目录之外")
    return directory


def contained_file(directory, path):
    path = Path(path)
    if not path.resolve().is_relative_to(Path(directory).resolve()):
        raise ValueError("文件指向月份目录之外")
    return path


def safe_base(directory, name):
    if not name or name in (".", "..") or re.search(r'[\\/:*?"<>|\r\n\x00]', name):
        raise ValueError("记录中的文件名无效")
    base = directory / name
    if not base.resolve().is_relative_to(directory.resolve()):
        raise ValueError("文件超出月份目录")
    return base


def exists(path):
    return path.is_file() and path.stat().st_size > 0


def xml_tree(path):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.fromstring(path.read_bytes(), parser=parser)


def read_month(output_root, year, month):
    directory = month_directory(output_root, year, month)
    records, warnings = {}, []
    file = directory / f"{year}-{month:02d}.json"
    if file.exists():
        try:
            contained_file(directory, file)
            data = json.loads(file.read_text(encoding="utf-8-sig"))
            if not isinstance(data, list):
                raise ValueError("月记录必须是数组")
            for item in data:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                stem = str(item.get("title_fs") or item.get("title") or item.get("id") or "").strip()
                try:
                    safe_base(directory, stem)
                except ValueError:
                    warnings.append("已跳过包含无效文件名的月记录")
                    continue
                item["title_fs"] = stem
                records[stem] = item
        except (ValueError, OSError) as exc:
            warnings.append(f"月记录读取失败，已尝试从 NFO 恢复：{exc}")
    if directory.exists():
        for nfo in directory.glob("*.nfo"):
            try:
                safe_base(directory, nfo.stem)
                contained_file(directory, nfo)
                node = xml_tree(nfo)
                item = records.setdefault(nfo.stem, {"title_fs": nfo.stem})
                item.setdefault("id", node.findtext("id") or node.findtext("uniqueid") or "")
                item.setdefault("title", node.findtext("title") or nfo.stem)
                item.setdefault("url", f"https://hanime1.me/watch?v={item['id']}" if str(item.get("id", "")).isdigit() else "")
                item.setdefault("tags", list(dict.fromkeys(e.text for e in [*node.findall("tag"), *node.findall("genre")] if e.text)))
                item["description"] = node.findtext("plot") or ""
                item["_nfo_categories"] = list(dict.fromkeys(e.text for e in [*node.findall("tag"), *node.findall("genre")] if e.text))
            except (ET.ParseError, OSError, ValueError) as exc:
                warnings.append(f"一个 NFO 无法解析：{exc}")
    for stem, item in records.items():
        item["_entry_id"] = hashlib.sha256(str(directory / stem).encode()).hexdigest()[:20]
        item.setdefault("title", stem)
        item.setdefault("tags", [])
    return sorted(records.values(), key=lambda i: i["title_fs"].casefold()), warnings


def library_entries(output_root, year, month, settings, tasks=()):
    directory = month_directory(output_root, year, month)
    tasks = [task for task in tasks if os.path.normcase(str(task.get("outputDir", ""))) == os.path.normcase(str(directory))]
    items, warnings = read_month(output_root, year, month)
    entries = []
    for item in items:
        base = safe_base(directory, item["title_fs"])
        video, nfo, cover = Path(str(base) + ".mp4"), Path(str(base) + ".nfo"), Path(str(base) + "-poster.jpg")
        for file in (video, nfo, cover):
            contained_file(directory, file)
        states = dict(image="ready" if exists(cover) else "missing", nfo="ready" if exists(nfo) else "missing", video="ready" if exists(video) else "missing")
        status = "completed" if all(v == "ready" for v in states.values()) else "no-image" if states["image"] == "missing" else "no-nfo" if states["nfo"] == "missing" else "pending"
        task = next((t for t in reversed(list(tasks)) if t.get("entryId") == item["_entry_id"] and not t.get("superseded")), None)
        if task and task.get("state") not in ("waiting", "downloading", "failed"):
            task = None
        if task:
            status = "failed" if task["state"] == "failed" else "downloading"
            if task["type"] == "视频":
                states["video"] = "failed" if task["state"] == "failed" else "downloading"
        original = item.get("original_tags", item.get("tags", []))
        from media_resolution import entry_resolution
        resolution, resolution_source = entry_resolution(item)
        entry = dict(id=item["_entry_id"], code=str(item.get("id") or "本地记录"), title=item["title"],
                     resolution=resolution, resolutionSource=resolution_source,
                     cover="/api/asset?path=" + __import__("urllib.parse", fromlist=["quote"]).quote(str(cover), safe="") if exists(cover) else "",
                     **states, status=status, description=item.get("description", ""), originalCategories=original,
                     exportedCategories=item.get("_nfo_categories", []), originalCategoriesAvailable="original_tags" in item,
                     paths=dict(video=str(video), nfo=str(nfo), cover=str(cover)))
        if task:
            entry.update(videoProgress=task.get("progress", 0), error=task.get("error"))
        current = next((t for t in reversed(tasks) if t.get("currentCode") == str(item.get("id"))
                        and t.get("state") == "downloading" and t.get("type") in ("NFO", "图片")), None)
        if current:
            entry["status"] = "downloading"
            for field in ("image", "nfo"):
                if entry[field] == "missing":
                    entry[field] = "downloading"
        entries.append(entry)
    for task in tasks:
        code = task.get("currentCode")
        if task.get("state") != "downloading" or not code or any(e["code"] == code for e in entries):
            continue
        entries.append(dict(id=f"processing-{task['id']}-{code}", code=code,
                            title=task.get("currentTitle") or f"正在读取条目 {code}", cover="",
                            image="downloading", nfo="downloading", video="missing", status="downloading",
                            description="", originalCategories=[], exportedCategories=[],
                            paths=dict(video="", nfo="", cover=""), isProcessingPlaceholder=True))
    return dict(entries=entries, monthDir=str(directory), warnings=warnings,
                categories=sorted(set(str(t) for i in items for t in i.get("original_tags", i.get("tags", []))), key=str.casefold))


class Storage:
    def __init__(self, state_dir=None):
        self.state_dir = Path(state_dir or APP_ROOT / ".media-helper")
        self.lock = threading.RLock()
        self.settings = default_settings()
        self.error = ""
        path = self.state_dir / "settings.json"
        if path.exists():
            try:
                self.settings = validate_settings(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                self.error = f"配置文件读取失败，当前使用默认设置；原文件已保留：{exc}"

    def save_settings(self, value):
        settings = validate_settings(value)
        with self.lock:
            atomic_write(self.state_dir / "settings.json", json.dumps(settings, ensure_ascii=False, indent=2).encode())
            self.settings = settings
        return copy.deepcopy(settings)

    def _nfo_changes(self, request):
        settings = validate_settings(request.get("settings", self.settings))
        items, _ = read_month(request["outputRoot"], request["year"], request["month"])
        directory = month_directory(request["outputRoot"], request["year"], request["month"])
        ids = request.get("ids")
        if ids is not None:
            if not isinstance(ids, list) or not ids:
                raise ValueError("请先选择需要更新的条目")
            items = [i for i in items if i["_entry_id"] in ids]
        changes, unrecoverable = [], 0
        for item in items:
            path = Path(str(safe_base(directory, item["title_fs"])) + ".nfo")
            contained_file(directory, path)
            if not path.exists():
                continue
            before = path.read_bytes()
            node = xml_tree(path)
            tags = filter_categories(item.get("original_tags", item.get("tags", [])), settings)
            if "original_tags" not in item:
                unrecoverable += 1
            old_fields = "\n".join(ET.tostring(c, encoding="unicode").strip() for c in node if c.tag in ("tag", "genre"))
            for child in list(node):
                if child.tag in ("tag", "genre"):
                    node.remove(child)
            new_nodes = []
            for field, enabled in (("genre", settings["writeGenres"]), ("tag", settings["writeTags"])):
                if enabled:
                    for tag in tags:
                        child = ET.SubElement(node, field)
                        child.text = tag
                        child.tail = "\n"
                        new_nodes.append(child)
            new_fields = "\n".join(ET.tostring(c, encoding="unicode").strip() for c in new_nodes)
            if old_fields == new_fields:
                continue
            after = ET.tostring(node, encoding="utf-8", xml_declaration=True)
            changes.append(dict(path=path, before_bytes=before, after_bytes=after,
                                id=item["_entry_id"], title=item["title"], before=old_fields, after=new_fields))
        digest = hashlib.sha256()
        digest.update(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode())
        for change in changes:
            digest.update(str(change["path"]).encode())
            digest.update(change["before_bytes"])
            digest.update(change["after_bytes"])
        return changes, unrecoverable, digest.hexdigest()

    def preview_nfo(self, request):
        with self.lock:
            changes, missing, token = self._nfo_changes(request)
            return dict(affected=len(changes), unrecoverable=missing, token=token,
                        preview=[{k: c[k] for k in ("id", "title", "before", "after")} for c in changes])

    def apply_nfo(self, request):
        with self.lock:
            changes, _, token = self._nfo_changes(request)
            if token != request.get("token"):
                raise ValueError("文件或规则已改变，请重新预览后再更新")
            backups = 0
            for c in changes:
                if request.get("backup", True):
                    backup = Path(str(c["path"]) + ".bak")
                    while backup.exists():
                        backup = Path(str(c["path"]) + "." + uuid.uuid4().hex + ".bak")
                    # Exclusive creation preserves every older backup, including concurrent ones.
                    with backup.open("xb") as file:
                        file.write(c["before_bytes"])
                    backups += 1
                atomic_write(c["path"], c["after_bytes"])
            return dict(updated=len(changes), backups=backups)
