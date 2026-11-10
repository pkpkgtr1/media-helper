"""本地服务：静态界面 + JSON API（默认只听回环，局域网需显式放行）。

路由表集中在 `Application.get` / `Application.post`，子任务交给 `TaskManager`
以独立进程执行；本文件不含任何抓取逻辑，方便单独测试访问控制与任务编排。
"""
from __future__ import annotations

import argparse
from collections import deque
import copy
import importlib.util
import ipaddress
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import net
from .auth import COOKIE_NAME, SESSION_TTL, AuthError, AuthStore
from .config import (PROJECT_ROOT, PACKAGE_ROOT, Storage, atomic_write, cleanup_staging_dirs,
                     default_settings, exists, library_entries, mask_proxy, month_directory,
                     proxy_from_settings, read_month, safe_base)
from . import ltx
from .sources import SOURCES, HuangguoManager, source_label

DIST = PROJECT_ROOT / "web" / "dist"
WORKER = PACKAGE_ROOT / "worker.py"
WORKER_MODULE = "media_helper.worker"

ACTIVE = ("waiting", "downloading")
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")
DEFAULT_LAN_CIDRS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
DEFAULT_DEV_ORIGINS = ("http://127.0.0.1:8443", "http://localhost:8443")
PROBE_URL = "https://www.google.com/generate_204"


def split_host(value):
    """Split a Host/Origin host part into (name, port) and tolerate IPv6 brackets."""
    value = (value or "").strip()
    if value.startswith("["):
        end = value.find("]")
        if end > 0:
            return value[1:end].lower(), value[end + 1:].lstrip(":")
    if value.count(":") == 1:
        name, port = value.split(":", 1)
        return name.lower(), port
    return value.lower(), ""


def parse_cidrs(values):
    networks = []
    for value in values or ():
        try:
            networks.append(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError as exc:
            raise ValueError(f"网段无效：{value}（{exc}）") from exc
    if not networks:
        networks = [ipaddress.ip_network(value) for value in DEFAULT_LAN_CIDRS]
    return networks


def local_addresses(bind_host):
    """Best-effort list of this machine's addresses, used only for printing URLs."""
    if bind_host not in ("0.0.0.0", "::", ""):
        return [bind_host]
    found = []
    probes = [("8.8.8.8", socket.AF_INET), ("2001:4860:4860::8888", socket.AF_INET6)]
    for target, family in probes:
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as probe:
                probe.settimeout(0.3)
                probe.connect((target, 80))
                address = probe.getsockname()[0]
        except OSError:
            continue
        if not ipaddress.ip_address(address).is_loopback and address not in found:
            found.append(address)
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        infos = []
    for info in infos:
        address = info[4][0]
        if not ipaddress.ip_address(address).is_loopback and address not in found:
            found.append(address)
    return found


class AccessPolicy:
    """Decide which Host headers, source addresses and Origins may reach the UI."""

    def __init__(self, lan=False, cidrs=(), local_names=()):
        self.lan = bool(lan)
        self.networks = parse_cidrs(cidrs) if self.lan else []
        names = {str(value).strip().lower() for value in local_names if str(value).strip()}
        names.add(socket.gethostname().split(".")[0].lower())
        self.local_names = {name for name in names if name}

    def _address_in_networks(self, address):
        return any(address.version == network.version and address in network for network in self.networks)

    def host_ok(self, header_value):
        name, _port = split_host(header_value)
        if not name:
            return False
        if name in LOOPBACK_NAMES:
            return True
        if not self.lan:
            return False
        try:
            address = ipaddress.ip_address(name)
        except ValueError:
            # 只放行本机主机名这类无点名；带点的外部域名一律拒绝，防 DNS rebinding。
            return "." not in name and name in self.local_names
        return self._address_in_networks(address)

    def peer_ok(self, peer_ip):
        try:
            address = ipaddress.ip_address(peer_ip)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        return self.lan and self._address_in_networks(address)

    def origin_ok(self, header_value):
        value = (header_value or "").strip()
        if not value:
            return True
        if value.lower() == "null":
            return False
        scheme, _, remainder = value.partition("://")
        if scheme.lower() not in ("http", "https"):
            return False
        return self.host_ok(remainder.split("/", 1)[0])


def size_text(value):
    if isinstance(value, str):
        return value
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def open_local(path):
    path = Path(path)
    if not path.exists():
        raise ValueError("路径不存在，请先生成或下载文件")
    if os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def explain(message):
    """把子进程的原始失败信息补上一句可执行的建议。"""
    text = str(message or "")
    if "yt-dlp" in text and "未找到" not in text:
        text += "；可把 yt-dlp 放到项目的 bin/ 目录后重试"
    if "ffmpeg" in text.lower() and "not found" in text.lower():
        text += "；可把 ffmpeg 放到项目的 bin/ 目录后重试"
    return text


def worker_entry(path):
    """How to launch the worker: `-m` for the package module, file path for custom scripts.

    Running the module file directly makes every `from . import ...` fail with
    "attempted relative import with no known parent package", so the packaged
    worker must go through `python -m media_helper.worker`.
    """
    path = Path(path)
    if path.resolve() == WORKER.resolve():
        return ["-m", WORKER_MODULE]
    return [str(path)]


class TaskManager:
    def __init__(self, storage, worker_path=None):
        self.storage = storage
        self.worker_path = Path(worker_path or WORKER)
        self.worker_command = worker_entry(self.worker_path)
        self.lock = threading.RLock()
        self.tasks = []
        self.logs = []
        self.next_log = 0
        log_file = storage.state_dir / "operations.log"
        if log_file.exists():
            try:
                with log_file.open(encoding="utf-8") as stream:
                    for line in deque(stream, maxlen=1000):
                        try:
                            record = json.loads(line)
                            self.logs.append(record)
                            self.next_log = max(self.next_log, record["id"])
                        except (ValueError, KeyError, TypeError):
                            continue
            except OSError:
                pass
        self.revision = 0
        self.process = None
        self.active_id = None
        self.closed = threading.Event()
        self.wake = threading.Event()
        state = storage.state_dir / "tasks.json"
        if state.exists():
            try:
                self.tasks = json.loads(state.read_text(encoding="utf-8"))
                for task in self.tasks:
                    if task["state"] in ACTIVE:
                        task.update(state="cancelled", error="上次运行已中断，可点击重试")
            except (OSError, ValueError, KeyError, TypeError):
                self.tasks = []
        self.log("本地服务已启动")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _save(self):
        atomic_write(self.storage.state_dir / "tasks.json", json.dumps(self.tasks, ensure_ascii=False, indent=2).encode())

    def log(self, message, level="info", task_id=None):
        with self.lock:
            self.next_log += 1
            line = dict(id=self.next_log, t=datetime.now().strftime("%H:%M:%S"), level=level if level in ("info", "warn", "error") else "info", msg=str(message), taskId=task_id)
            self.logs.append(line)
            self.logs = self.logs[-1000:]
            self.storage.state_dir.mkdir(parents=True, exist_ok=True)
            with (self.storage.state_dir / "operations.log").open("a", encoding="utf-8") as file:
                file.write(json.dumps(line, ensure_ascii=False) + "\n")

    def snapshot(self):
        with self.lock:
            return dict(tasks=[{k: v for k, v in t.items() if not k.startswith("_")} for t in self.tasks], logs=copy.deepcopy(self.logs), revision=self.revision)

    def enqueue(self, request):
        kind = request.get("kind")
        if kind not in ("metadata", "covers", "video", "repair", "resolutions"):
            raise ValueError("不支持的任务类型")
        year, month, root = request["year"], request["month"], request["outputRoot"]
        directory = month_directory(root, year, month)
        items, _ = read_month(root, year, month)
        ids = request.get("ids")
        if ids is not None:
            if not isinstance(ids, list) or not ids:
                raise ValueError("请选择至少一个条目")
            selected = [item for item in items if item["_entry_id"] in ids]
            if len(selected) != len(set(ids)):
                raise ValueError("部分条目已改变，请刷新列表")
            items = selected
        if kind != "metadata" and not items:
            raise ValueError("当前月份没有记录，请先获取图片与 NFO")
        settings = copy.deepcopy(self.storage.settings)
        settings["outputRoot"] = str(directory.parent)
        groups = [[item] for item in items] if kind in ("video", "repair") else [items]
        queued, skipped = 0, 0
        with self.lock:
            for group in groups:
                item = group[0] if len(group) == 1 and kind in ("video", "repair") else None
                if kind == "video" and settings["existingVideo"] == "skip" and exists(Path(str(safe_base(directory, item["title_fs"])) + ".mp4")):
                    skipped += 1
                    continue
                key = (kind, str(directory), tuple(sorted(i["_entry_id"] for i in group)))
                if any(t["state"] in ACTIVE and tuple(t["_key"][:2]) == key[:2] and tuple(t["_key"][2]) == key[2] for t in self.tasks):
                    skipped += 1
                    continue
                task_id = uuid.uuid4().hex
                job = dict(id=task_id, kind=kind, year=year, month=month, outputRoot=str(directory.parent), items=group, settings=settings)
                task = dict(id=task_id, title=item["title"] if item else f"{year}-{month:02d} " + ("画质更新" if kind == "resolutions" else "封面更新" if kind == "covers" else "图片与 NFO"),
                            code=str(item.get("id") or "本地记录") if item else f"{year}-{month:02d}", type="画质" if kind == "resolutions" else "视频" if kind == "video" else "图片" if kind == "covers" else "NFO",
                            state="waiting", progress=0, indeterminate=True, outputDir=str(directory), entryId=item["_entry_id"] if item else None,
                            _job=job, _key=key)
                self.tasks.append(task)
                self.log("任务已加入队列", task_id=task_id)
                queued += 1
            self.revision += 1
            self._save()
            self.wake.set()
        return dict(queued=queued, skipped=skipped)

    def action(self, request):
        action, task_id = request.get("action"), request.get("id")
        with self.lock:
            if action == "clear-completed":
                self.tasks = [t for t in self.tasks if t["state"] != "completed"]
            elif action == "retry-failed":
                for task in self.tasks:
                    if task["state"] == "failed":
                        self._retry(task)
            elif action in ("cancel", "retry"):
                task = next((t for t in self.tasks if t["id"] == task_id), None)
                if not task:
                    raise ValueError("任务不存在")
                if action == "retry":
                    if task["state"] not in ("failed", "cancelled"):
                        raise ValueError("只能重试失败或已取消的任务")
                    self._retry(task)
                elif task["state"] in ACTIVE:
                    task["state"] = "cancelled"
                    task["error"] = "任务已取消"
                    # The monitor owns process cleanup. Do not wait on it holding this lock.
                    if self.active_id == task_id and self.process is not None:
                        self._terminate(self.process)
                    self.log("任务已取消", "warn", task_id)
            else:
                raise ValueError("不支持的任务操作")
            self.revision += 1
            self._save()
            self.wake.set()
        return {"ok": True}

    def _retry(self, task):
        if self.active_id == task["id"]:
            raise ValueError("任务仍在结束处理中，请稍后重试")
        task.update(state="waiting", progress=0, indeterminate=True)
        for key in ("error", "downloaded", "total", "speed", "eta", "currentCode", "currentTitle", "currentIndex", "itemTotal", "processed", "phase"):
            task.pop(key, None)
        self.log("已重新加入队列（从头重试）", task_id=task["id"])

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=HIDDEN, timeout=15)
        else:
            import signal
            os.killpg(process.pid, signal.SIGTERM)

    def close(self):
        self.closed.set()
        self.wake.set()
        with self.lock:
            if self.process:
                self._terminate(self.process)

    def _loop(self):
        while not self.closed.is_set():
            self.wake.wait(1)
            self.wake.clear()
            with self.lock:
                task = next((t for t in self.tasks if t["state"] == "waiting"), None)
                if task:
                    task["state"] = "downloading"
                    self.active_id = task["id"]
                    self.revision += 1
                    self._save()
            if not task:
                continue
            self._run(task)
            # Interval applies between jobs and can be interrupted during shutdown.
            self.closed.wait(task["_job"]["settings"].get("downloadInterval", 0) / 1000)
            self.wake.set()

    @staticmethod
    def _clean_staging(task):
        """Remove leftovers a killed worker or earlier crash left in the month dir."""
        directory = task.get("outputDir") if task else None
        if not directory:
            return []
        try:
            return cleanup_staging_dirs(directory)
        except OSError:
            return []

    def _run(self, task):
        job_file = self.storage.state_dir / "jobs" / (task["id"] + ".json")
        stderr_file = self.storage.state_dir / "jobs" / (task["id"] + ".stderr.log")
        completed, error = False, ""
        process = None
        try:
            atomic_write(job_file, json.dumps(task["_job"], ensure_ascii=False).encode())
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            with stderr_file.open("w", encoding="utf-8") as stderr:
                with self.lock:
                    if task["state"] == "cancelled" or self.closed.is_set():
                        return
                    for stale in self._clean_staging(task):
                        self.log(f"已清理上次中断遗留的临时文件：{Path(stale).name}", "warn", task["id"])
                    process = subprocess.Popen([sys.executable, "-u", *self.worker_command, str(job_file)], cwd=PROJECT_ROOT, env=env,
                                               stdout=subprocess.PIPE, stderr=stderr, text=True, encoding="utf-8", errors="replace",
                                               creationflags=HIDDEN, start_new_session=os.name != "nt")
                    self.process = process
                self.log("开始执行任务", task_id=task["id"])
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        if line.strip():
                            self.log(line.strip(), task_id=task["id"])
                        continue
                    with self.lock:
                        if task["state"] == "cancelled":
                            continue
                        if event.get("type") == "log":
                            self.log(event.get("msg", ""), event.get("level", "info"), task["id"])
                        elif event.get("type") == "progress":
                            task["progress"] = max(0, min(100, round(float(event.get("progress", 0)))))
                            task["indeterminate"] = bool(event.get("indeterminate", False))
                            for key in ("currentCode", "currentTitle", "currentIndex", "itemTotal", "processed", "phase"):
                                if key in event:
                                    task[key] = event[key]
                            for key in ("downloaded", "total"):
                                if event.get(key) is not None:
                                    task[key] = size_text(event[key])
                            if event.get("speed") is not None:
                                task["speed"] = size_text(event["speed"]) + "/s"
                            if event.get("eta") is not None:
                                task["eta"] = f"约 {round(float(event['eta']))} 秒"
                            self.revision += 1
                        elif event.get("type") == "done":
                            completed = True
                        elif event.get("type") == "error":
                            error = event.get("msg", "任务失败")
                returncode = process.wait()
                if returncode != 0 and not error:
                    tail = stderr_file.read_text(encoding="utf-8", errors="replace")[-1600:].strip()
                    error = f"任务进程退出（{returncode}）" + (f"：{tail}" if tail else "")
        except Exception as exc:
            error = str(exc)
        finally:
            if process and process.poll() is None:
                self._terminate(process)
            # A cancelled worker is killed before it can remove its staging dir.
            for stale in self._clean_staging(task):
                self.log(f"已清理中断任务遗留的临时文件：{Path(stale).name}", "warn", task["id"])
            with self.lock:
                if task["state"] != "cancelled":
                    if completed and not error:
                        task.update(state="completed", progress=100, indeterminate=False)
                        if task.get("entryId"):
                            for older in self.tasks:
                                if older is not task and older.get("entryId") == task["entryId"] and older["type"] == task["type"] and older["state"] in ("failed", "cancelled"):
                                    older["superseded"] = True
                        self.log("任务完成", task_id=task["id"])
                        if task["_job"]["settings"].get("openAfter"):
                            try: open_local(task["outputDir"])
                            except OSError as exc: self.log(str(exc), "warn", task["id"])
                    else:
                        task.update(state="failed", error=explain(error or "任务没有返回完成结果，请查看日志"))
                        self.log(task["error"], "error", task["id"])
                self.process = None
                self.active_id = None
                self.revision += 1
                self._save()
            if process and process.stdout:
                process.stdout.close()


def environment_info():
    """界面上「运行环境」卡片的真实数据来源：只报告检测结果，不安装任何东西。"""
    items = [dict(name="Python", status="ready", detail=f"{sys.version.split()[0]} · {sys.executable}")]
    for executable, label in (("ffmpeg", "FFmpeg"), ("yt-dlp", "视频下载器")):
        bundled = PROJECT_ROOT / "bin" / (executable + (".exe" if os.name == "nt" else ""))
        found = str(bundled) if bundled.exists() else shutil.which(executable)
        items.append(dict(name=label, status="ready" if found else "missing", detail=found or "未安装"))
    for module, label in (("requests", "HTTP 请求"), ("bs4", "页面解析"), ("PIL", "图片处理")):
        available = importlib.util.find_spec(module) is not None
        items.append(dict(name=label, status="ready" if available else "missing",
                          detail="已安装" if available else "缺少 Python 依赖，请重新安装 requirements.txt"))
    proxy = net.flaresolverr_enabled()
    items.append(dict(name="FlareSolverr",
                      status="ready" if proxy else "optional",
                      detail=net.flaresolverr_endpoint() if proxy else "未启用；仅在站点启用挑战页时需要"))
    return {"items": items}


def _count_by_source(results):
    counts = {}
    for row in results:
        key = str(row.get("source") or "huangguo")
        counts[key] = counts.get(key, 0) + 1
    return counts


def task_view(task):
    if not task:
        return None
    return {k: v for k, v in task.items() if not k.startswith("_")}


class Application:
    def __init__(self, storage, dist=None, worker_path=None, dev_origins=(), auth=None):
        self.storage = storage
        # 短剧客户端在本进程内直接发请求：启动与保存设置时都要发布 UA/代理/会话。
        net.configure(storage.settings)
        self.tasks = TaskManager(storage, worker_path)
        # 登录：密码存于 config/auth.json，与会话令牌一起决定请求是否放行。
        self.auth = auth if auth is not None else AuthStore(storage.state_dir)
        self.dist = Path(dist or DIST).resolve()
        self.dev_origins = {str(value).rstrip("/") for value in dev_origins if str(value).strip()}
        self.allowed_roots = {Path(storage.settings["outputRoot"]).resolve()}
        for task in self.tasks.tasks:
            self.allowed_roots.add(Path(task["outputDir"]).resolve().parent)
        self.huangguo = None
        if HuangguoManager is not None:
            self.huangguo = HuangguoManager(lambda: self.storage.settings,
                                            logger=lambda msg, level="info": self.tasks.log(f"短剧：{msg}", level),
                                            root=self.storage.state_dir / "huangguo")
            for sub_item in self.huangguo.store.snapshot():
                if sub_item.get("saveRoot"):
                    self.allow(sub_item["saveRoot"])
        # Jasna 资源库：数据落在 config/ltxdb/，与根目录的 ltxdb.py 共用同一份库。
        self.ltx_data_dir = self.storage.state_dir / "ltxdb"
        self.ltx = ltx.Scheduler(lambda: self.storage.settings,
                                 log=lambda msg, level="info": self.tasks.log(f"资源库：{msg}", level),
                                 data_dir=self.ltx_data_dir)

    def allow(self, root):
        self.allowed_roots.add(Path(root).expanduser().resolve())

    def test_proxy(self, body):
        """Probe a fixed endpoint through the given proxy; never an open URL fetch."""
        settings = {"proxyEnabled": True, "proxyUrl": str(body.get("proxyUrl") or self.storage.settings.get("proxyUrl") or "")}
        try:
            url = proxy_from_settings(settings)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "proxy": mask_proxy(settings["proxyUrl"])}
        if not url:
            return {"ok": False, "error": "请先填写代理地址", "proxy": ""}
        import time
        import requests
        started = time.monotonic()
        try:
            response = requests.get(PROBE_URL, proxies={"http": url, "https": url}, timeout=(6, 10), allow_redirects=False)
            elapsed = round(time.monotonic() - started, 2)
            if response.status_code in (204, 200, 301, 302):
                return {"ok": True, "proxy": mask_proxy(url), "detail": f"HTTP {response.status_code}，耗时 {elapsed}s"}
            return {"ok": False, "proxy": mask_proxy(url), "error": f"探测返回 HTTP {response.status_code}，耗时 {elapsed}s"}
        except Exception as exc:
            reason = type(exc).__name__
            if "ProxyError" in reason or "407" in str(exc):
                reason = "代理连接或认证失败，请检查地址、端口与账号密码"
            elif "ConnectTimeout" in reason:
                reason = "无法连接代理，请检查地址与端口是否可达"
            return {"ok": False, "proxy": mask_proxy(url), "error": reason}

    def path(self, value):
        path = Path(value).resolve()
        if not any(path.is_relative_to(root) for root in self.allowed_roots):
            raise ValueError("路径不在已选择的媒体目录中")
        return path

    # ------------------------------------------------------------ 登录相关

    def auth_status(self):
        """登录页与启动流程都靠它判断：要不要设密码、要不要先登录。"""
        return dict(hasPassword=self.auth.has_password, updatedAt=self.auth.updated_at)

    def setup_password(self, body):
        """首次设置密码；已有密码时必须先通过验证才能改。"""
        password = body.get("password")
        if self.auth.has_password:
            if not self.auth.verify(body.get("current")):
                raise ValueError("当前密码不正确")
        try:
            self.auth.set_password(password)
        except AuthError as exc:
            raise ValueError(str(exc)) from exc
        # 改完密码直接登录，省得再输一次。
        return dict(token=self.auth.issue())

    def login(self, body, key=""):
        wait = self.auth.blocked_for(key)
        if wait:
            raise ValueError(f"密码错误次数过多，请 {wait} 秒后再试")
        if not self.auth.has_password:
            raise ValueError("尚未设置密码")
        if not self.auth.verify(body.get("password")):
            self.auth.note_failure(key)
            raise ValueError("密码不正确")
        self.auth.reset_failures(key)
        return dict(token=self.auth.issue())

    def change_password(self, body):
        if not self.auth.verify(body.get("current")):
            raise ValueError("当前密码不正确")
        try:
            self.auth.set_password(body.get("password"))
        except AuthError as exc:
            raise ValueError(str(exc)) from exc
        return dict(token=self.auth.issue())


    def get(self, route, query):
        if route == "/api/bootstrap":
            return dict(settings=self.storage.settings, defaults=default_settings(), error=self.storage.error)
        if route == "/api/state":
            return self.tasks.snapshot()
        if route == "/api/environment":
            return environment_info()
        if route == "/api/library":
            root = query.get("outputRoot", [self.storage.settings["outputRoot"]])[0]
            year, month = int(query["year"][0]), int(query["month"][0])
            month_directory(root, year, month)
            self.allow(root)
            return library_entries(root, year, month, self.storage.settings, self.tasks.snapshot()["tasks"])
        if route.startswith("/api/hg/"):
            return self.huangguo_get(route, query)
        if route.startswith("/api/ltx/"):
            return self.ltx_get(route, query)
        raise FileNotFoundError("接口不存在")

    def ltx_get(self, route, query):
        if route == "/api/ltx/status":
            data = ltx.status(self.ltx_data_dir)
            data["nextSync"] = self.ltx.next_run() or data.get("nextSync")
            data["enabled"] = bool(self.storage.settings.get("ltxSyncEnabled"))
            data["intervalSeconds"] = ltx.interval_seconds(self.storage.settings)
            return data
        if route == "/api/ltx/items":
            def first(key, default=""):
                return (query.get(key) or [default])[0]

            def number(key, default):
                try:
                    return int(first(key, str(default)))
                except ValueError:
                    return default

            return ltx.search(keyword=first("keyword"), maker=first("maker"), genre=first("genre"),
                              sort=first("sort", "date"), page=number("page", 1),
                              limit=number("limit", 48), data_dir=self.ltx_data_dir)
        if route == "/api/ltx/detail":
            code = (query.get("code") or [""])[0].strip()
            if not code:
                raise ValueError("请提供番号")
            return ltx.detail(code, self.ltx_data_dir)
        if route == "/api/ltx/filters":
            return {"makers": ltx.makers(self.ltx_data_dir), "genres": ltx.genres(self.ltx_data_dir)}
        raise FileNotFoundError("接口不存在")

    def hg(self):
        if self.huangguo is None:
            raise ValueError("短剧模块不可用（huangguo_manager 导入失败）")
        return self.huangguo

    def huangguo_image(self, value, source="huangguo"):
        """Fetch + decrypt one site cover for <img> tags (SSRF-guarded)."""
        if not value:
            return None
        manager = self.hg()
        source = source if source in SOURCES else "huangguo"
        return manager._client(source).fetch_image(value)

    def hg_search(self, keyword, source="all"):
        """Search one source or all of them; failures never hide other results."""
        wanted = [source] if source != "all" else list(SOURCES)
        rows, errors = [], []
        for key in wanted:
            try:
                found = self.hg()._client(key).search(keyword)
                for row in found:
                    row["source"] = key
                    row["sourceLabel"] = source_label(key)
                rows.extend(found)
            except Exception as exc:  # noqa: BLE001 - one site down must not break the other
                errors.append(f"{source_label(key)}搜索失败：{exc}")
        return rows, errors

    def huangguo_get(self, route, query):
        manager = self.hg()
        if route == "/api/hg/search":
            keyword = (query.get("keyword") or [""])[0].strip()
            if not keyword:
                raise ValueError("请输入搜索关键词")
            source = (query.get("source") or ["all"])[0].strip() or "all"
            if source != "all" and source not in SOURCES:
                raise ValueError("未知搜索源")
            results, errors = self.hg_search(keyword, source)
            if not results and errors:
                raise ValueError("；".join(errors))
            for message in errors:
                self.tasks.log(message, "warn")
            self.tasks.log(f"短剧：搜索“{keyword}”，{len(results)} 个结果"
                           + (f"（{'、'.join(f'{SOURCES[k]} {v}' for k, v in counts.items())}）"
                              if (counts := _count_by_source(results)) else ""))
            return {"results": results,
                    "sources": [{"key": key, "label": label} for key, label in SOURCES.items()],
                    "errors": errors,
                    "subscribedVideoIds": [s["videoId"] for s in manager.store.snapshot()],
                    "subscribedKeys": [f"{s.get('source', 'huangguo')}:{s['videoId']}"
                                       for s in manager.store.snapshot()]}
        if route == "/api/hg/detail":
            source = (query.get("source") or ["huangguo"])[0].strip() or "huangguo"
            if source not in SOURCES:
                raise ValueError("未知短剧源")
            video_id = int((query.get("videoId") or ["0"])[0])
            info = manager._client(source).detail(video_id)
            info["source"] = source
            info["sourceLabel"] = source_label(source)
            self.tasks.log(f"短剧：查看详情《{info['title']}》（{source_label(source)}，{info['total']} 集）")
            return info
        if route == "/api/hg/subscriptions":
            return manager.subscriptions_view()
        if route == "/api/hg/tasks":
            return manager.snapshot_tasks()
        if route == "/api/hg/records":
            return {"records": manager.records.snapshot()}
        raise FileNotFoundError("接口不存在")

    def post(self, route, body):
        if route == "/api/settings":
            result = self.storage.save_settings(body)
            net.configure(result)
            self.allow(result["outputRoot"])
            self.ltx.reschedule()  # 周期改了要立刻生效，不能等下一轮循环
            self.tasks.log("设置已保存，后续任务使用新设置")
            return result
        if route == "/api/choose-directory":
            script = "import sys,json,tkinter as tk; from tkinter import filedialog; r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True); p=filedialog.askdirectory(parent=r,initialdir=sys.argv[1],title='选择媒体输出根目录'); r.destroy(); print(json.dumps({'path':p or None}))"
            process = subprocess.run([sys.executable, "-c", script, str(body.get("initial") or self.storage.settings["outputRoot"])], capture_output=True, text=True, encoding="utf-8", creationflags=HIDDEN)
            if process.returncode:
                raise ValueError("目录选择器启动失败，可以在设置中直接输入输出目录")
            result = json.loads(process.stdout)
            if result["path"]: self.allow(result["path"])
            return result
        if route == "/api/open-path":
            path = self.path(body["path"])
            open_local(path)
            return {"ok": True}
        if route == "/api/ltx/sync":
            # 手动同步在请求线程里跑完再返回，界面无需轮询；单次约 10–30 秒。
            return self.ltx.run_once(reason="手动")
        if route == "/api/tasks":
            self.allow(body["outputRoot"])
            return self.tasks.enqueue(body)
        if route == "/api/task-action":
            return self.tasks.action(body)
        if route in ("/api/nfo/preview", "/api/nfo/apply"):
            directory = month_directory(body["outputRoot"], body["year"], body["month"])
            with self.tasks.lock:
                if any(t["state"] in ACTIVE and t["outputDir"] == str(directory) for t in self.tasks.tasks):
                    raise ValueError("该月份还有任务运行，请完成或取消后再更新 NFO")
                if route.endswith("preview"):
                    return self.storage.preview_nfo(body)
                result = self.storage.apply_nfo(body)
            self.tasks.revision += 1
            self.tasks.log(f"NFO 更新完成：{result['updated']} 个，备份 {result['backups']} 个")
            return result
        if route == "/api/logs/clear":
            with self.tasks.lock:
                self.tasks.logs.clear()
                atomic_write(self.storage.state_dir / "operations.log", b"")
            return {"ok": True}
        if route == "/api/proxy/test":
            return self.test_proxy(body)
        if route.startswith("/api/hg/"):
            return self.huangguo_post(route, body)
        raise FileNotFoundError("接口不存在")

    def huangguo_post(self, route, body):
        manager = self.hg()
        if route == "/api/hg/subscribe":
            info = dict(body.get("info") or {})
            if not info.get("id"):
                raise ValueError("缺少短剧信息")
            source = info.get("source") if info.get("source") in SOURCES else "huangguo"
            info["source"] = source
            full = manager._client(source).detail(info["id"])
            full["source"] = source
            full["sourceLabel"] = source_label(source)
            full["description"] = full.get("description") or info.get("description") or ""
            sub = manager.store.add(full, self.storage.settings,
                                    **{k: body[k] for k in ("autoCheck", "intervalValue", "intervalUnit",
                                                             "saveRoot", "autoDownload", "scope", "episodeList")
                                       if k in body})
            self.allow(sub["saveRoot"])
            self.tasks.log(f"短剧：已订阅《{sub['title']}》（{source_label(source)}）")
            return sub
        if route == "/api/hg/subscription/update":
            sub = manager.store.update(body["subscriptionId"], body.get("changes") or {})
            if sub.get("saveRoot"):
                self.allow(sub["saveRoot"])
            return sub
        if route == "/api/hg/subscription/remove":
            removed = manager.store.items.get(str(body["subscriptionId"]))
            if removed is None:
                raise KeyError("订阅不存在")
            deleted = None
            if body.get("keepFiles") is False:  # 需前端二次确认才会传 False
                deleted = manager.delete_downloaded(removed)
            manager.store.remove(body["subscriptionId"])
            self.tasks.log("短剧：已删除订阅《" + removed["title"] + "》"
                           + (f"并删除目录 {deleted}" if deleted else "（保留文件）"))
            return {"ok": True, "deletedPath": deleted}
        if route == "/api/hg/subscription/repair":
            return manager.repair_assets(body["subscriptionId"])
        if route == "/api/hg/check":
            task = manager.enqueue_check(body["subscriptionId"], reason=str(body.get("reason") or "手动"))
            return task_view(task)
        if route == "/api/hg/download":
            task = manager.enqueue_download(body["subscriptionId"], body.get("episodes") or None,
                                            reason=str(body.get("reason") or "手动"))
            return task_view(task) if task else {"state": "skipped", "message": "没有需要下载的集数"}
        if route == "/api/hg/thumb":
            return task_view(manager.enqueue_thumb(body["subscriptionId"], body["episode"]))
        if route == "/api/hg/task/clear":
            return manager.clear_tasks()
        if route in ("/api/hg/task/cancel", "/api/hg/task/retry"):
            done = manager.cancel(body["taskId"]) if route.endswith("cancel") else manager.retry(body["taskId"])
            if not done:
                raise ValueError("任务当前状态不支持该操作")
            return {"ok": True}
        raise FileNotFoundError("接口不存在")


def handler_for(app, policy=None, no_auth=False):
    policy = policy or AccessPolicy()
    # 本机 Vite 开发服务器的 Origin 默认放行，可用 MEDIA_DEV_ORIGINS 追加。
    dev_origins = {str(value).strip().rstrip("/") for value in
                   (getattr(app, "dev_origins", ()) or DEFAULT_DEV_ORIGINS) if str(value).strip()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _trusted(self):
            host = self.headers.get("Host", "")
            if not policy.host_ok(host):
                return False
            if not policy.peer_ok(self.client_address[0] if self.client_address else ""):
                return False
            origin = (self.headers.get("Origin") or "").strip().rstrip("/")
            if not origin:
                return True
            if not policy.origin_ok(origin):
                return False
            if origin in dev_origins:
                return True
            # 同源请求：Origin 的主机与端口要和 Host 一致。
            origin_host, origin_port = split_host(origin.split("://", 1)[-1])
            request_host, request_port = split_host(host)
            return origin_host == request_host and (not origin_port or not request_port or origin_port == request_port)

        def _send(self, status, data, content_type="application/json; charset=utf-8", cache=None, headers=None):
            content = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            # 图片内容在服务端按 host+path 缓存，签名轮换不影响字节；
            # 允许浏览器缓存才能做到详情封面直接命中、不再回源。
            self.send_header("Cache-Control", cache or "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            try: self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError): pass

        def _error(self, exc):
            self._send(404 if isinstance(exc, FileNotFoundError) else 400, {"error": str(exc)})

        def _client_key(self):
            return str(self.client_address[0] if self.client_address else "")

        def _token(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == COOKIE_NAME:
                    return value.strip()
            return ""

        def _logged_in(self):
            return app.auth.check(self._token())

        def _cookie_headers(self, token):
            # 本地 HTTP 部署用不上 Secure；SameSite=Strict 挡住跨站带 Cookie。
            value = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}"
            return {"Set-Cookie": value}

        def _clear_cookie(self):
            return {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"}

        def _blocked(self, path):
            """未登录时要拦下的请求返回 True；静态资源与登录接口始终放行。

            只有设置过密码之后才启用，首次运行先让用户进界面设置密码。
            """
            if not app.auth.has_password or no_auth:
                return False
            if path.startswith("/api/auth/"):
                return False
            # 静态资源必须放行，否则登录页自己都加载不出来。
            if not path.startswith("/api/"):
                return False
            return not self._logged_in()

        def do_GET(self):
            if not self._trusted():
                return self._send(403, {"error": "仅允许从本机应用访问"})
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if self._blocked(url.path):
                return self._send(401, {"error": "请先登录"})
            if url.path == "/api/auth/status":
                return self._send(200, {**app.auth_status(), "authenticated": self._logged_in()})
            try:
                if url.path == "/api/asset":
                    path = app.path(query["path"][0])
                    if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        raise ValueError("不支持的图片格式")
                    return self._send(200, path.read_bytes(), mimetypes.guess_type(path)[0] or "image/jpeg")
                if url.path == "/api/hg/image":
                    data = app.huangguo_image(query.get("url", [""])[0],
                                              (query.get("source") or ["huangguo"])[0])
                    if not data:
                        raise ValueError("封面获取失败")
                    kind = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
                    return self._send(200, data, kind, cache="private, max-age=86400")
                if url.path == "/api/hg/cover":
                    data = app.hg().cover_image((query.get("subscriptionId") or [""])[0])
                    kind = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
                    return self._send(200, data, kind, cache="private, max-age=86400")
                if url.path == "/api/ltx/cover":
                    # 只允许站点 CDN；取不到就回 404，让界面走占位图。
                    data = ltx.fetch_cover((query.get("url") or [""])[0])
                    if not data:
                        raise FileNotFoundError("封面获取失败")
                    kind = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                    return self._send(200, data, kind, cache="private, max-age=86400")
                if url.path.startswith("/api/"):
                    return self._send(200, app.get(url.path, query))
                path = (app.dist / url.path.lstrip("/")).resolve()
                if not path.is_relative_to(app.dist):
                    raise ValueError("路径无效")
                if not path.is_file():
                    path = app.dist / "index.html"
                if not path.exists():
                    raise FileNotFoundError("界面尚未构建，请先在 web/ 目录运行 pnpm build")
                content_type = "application/javascript" if path.suffix == ".js" else mimetypes.guess_type(path)[0] or "application/octet-stream"
                self._send(200, path.read_bytes(), content_type)
            except Exception as exc:
                self._error(exc)

        def do_POST(self):
            if not self._trusted():
                return self._send(403, {"error": "仅允许从本机应用访问"})
            if self.headers.get_content_type() != "application/json":
                return self._send(415, {"error": "请求必须使用 JSON"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2_000_000:
                    raise ValueError("请求大小无效")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("请求必须是对象")
                route = urlparse(self.path).path
                if self._blocked(route):
                    return self._send(401, {"error": "请先登录"})
                if route == "/api/auth/login":
                    result = app.login(body, key=self._client_key())
                    return self._send(200, {"ok": True}, headers=self._cookie_headers(result["token"]))
                if route == "/api/auth/setup":
                    result = app.setup_password(body)
                    return self._send(200, {"ok": True}, headers=self._cookie_headers(result["token"]))
                if route == "/api/auth/password":
                    result = app.change_password(body)
                    return self._send(200, {"ok": True}, headers=self._cookie_headers(result["token"]))
                if route == "/api/auth/logout":
                    app.auth.revoke(self._token())
                    return self._send(200, {"ok": True}, headers=self._clear_cookie())
                self._send(200, app.post(route, body))
            except Exception as exc:
                self._error(exc)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="媒体下载助手本地服务（新版界面）")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default=None,
                        help="监听地址；默认 127.0.0.1，局域网访问请用 0.0.0.0 或本机内网 IP，也可设环境变量 MEDIA_HOST")
    parser.add_argument("--lan", "--allow-lan", dest="lan", action="store_true",
                        help="允许同网段设备访问（等价于 MEDIA_ALLOW_LAN=1）")
    parser.add_argument("--lan-cidr", dest="lan_cidrs", action="append", metavar="CIDR",
                        help="放行来源网段，可重复；默认 10/8、172.16/12、192.168/16、fc00::/7")
    parser.add_argument("--state-dir")
    parser.add_argument("--output-root")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-auth", dest="no_auth", action="store_true",
                        help="跳过登录校验（密码仍保留，便于本机脚本调试）")
    args = parser.parse_args()

    bind_host = args.host or os.environ.get("MEDIA_HOST") or "127.0.0.1"
    lan = args.lan or os.environ.get("MEDIA_ALLOW_LAN", "").strip().lower() in ("1", "true", "yes", "on")
    cidrs = list(args.lan_cidrs or ())
    if not cidrs:
        cidrs = [value for value in (os.environ.get("MEDIA_LAN_CIDRS") or "").replace(",", " ").split() if value]
    dev_origins = [value for value in (os.environ.get("MEDIA_DEV_ORIGINS") or "").replace(",", " ").split() if value]
    try:
        policy = AccessPolicy(lan=lan, cidrs=cidrs)
    except ValueError as exc:
        parser.error(str(exc))
    external = bind_host not in ("127.0.0.1", "localhost", "::1", "")
    if external and not lan:
        parser.error(f"监听地址 {bind_host} 会暴露到局域网，请同时指定 --lan（或 MEDIA_ALLOW_LAN=1）确认开放")

    storage = Storage(args.state_dir)
    report = getattr(storage, "migration", None)
    if report and report.get("migrated"):
        print(f"记录与日志已迁移到 {report['to']}（来源 {report['from']}）", flush=True)
    if args.output_root: storage.settings["outputRoot"] = str(Path(args.output_root).resolve())
    app = Application(storage, dev_origins=dev_origins or DEFAULT_DEV_ORIGINS)
    if app.huangguo:
        app.huangguo.start()
    app.ltx.start()
    try:
        server = ThreadingHTTPServer((bind_host, args.port), handler_for(app, policy, no_auth=args.no_auth))
    except OSError:
        app.tasks.close()
        raise
    port = server.server_port
    # 0.0.0.0/:: 也包含回环，本机一律用 127.0.0.1 打开；具体内网 IP 绑定时只能用该 IP。
    machine_host = "127.0.0.1" if bind_host in ("", "127.0.0.1", "localhost", "::1", "0.0.0.0", "::") else bind_host
    if machine_host == "127.0.0.1":
        print(f"媒体下载助手已启动：http://127.0.0.1:{port}", flush=True)
    else:
        print(f"媒体下载助手已启动：http://{bind_host}:{port}（未监听 127.0.0.1，本机请用此地址）", flush=True)
    if lan:
        limits = ", ".join(str(network) for network in policy.networks)
        if bind_host in ("", "127.0.0.1", "localhost", "::1"):
            print(f"提示：已开启局域网放行，但仍只监听 {bind_host or '127.0.0.1'}，其他设备无法访问；"
                  "请改用 --host 0.0.0.0 --lan", flush=True)
        else:
            candidates = [address for address in local_addresses(bind_host) if policy.peer_ok(address)]
            for address in [value for value in candidates if value != machine_host]:
                print(f"局域网地址：http://{address}:{port}", flush=True)
            if candidates:
                print(f"来源限制：{limits}；同网段其他设备请用以上地址访问", flush=True)
            elif bind_host in ("0.0.0.0", "::"):
                print(f"已监听全部网卡，但未探测到命中 {limits} 的本机地址，请用设备实际 IP 访问", flush=True)
            else:
                print(f"警告：监听地址 {bind_host} 不在放行网段 {limits} 内，其他设备会被拒绝；"
                      "请调整 --lan-cidr 或改用 --host 0.0.0.0", flush=True)
    if args.no_auth:
        print("登录校验已关闭（--no-auth），任何能访问该地址的设备都可直接操作", flush=True)
    elif app.auth.has_password:
        print("登录已启用：浏览器首次访问需要输入密码", flush=True)
    else:
        print("尚未设置登录密码：首次打开界面时会要求设置", flush=True)
    if not args.no_browser:
        import webbrowser
        webbrowser.open(f"http://{machine_host}:{port}")
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        if app.huangguo:
            app.huangguo.close()
        app.ltx.close()
        app.tasks.close()
        server.server_close()


if __name__ == "__main__":
    main()
