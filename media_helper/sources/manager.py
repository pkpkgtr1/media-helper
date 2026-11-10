"""Huangguo subscription manager: storage, scheduler and download workers.

One process owns subscriptions, per-subscription schedules and Emby layout
output. State lives under config/huangguo/ (subscriptions.json, downloads.json)
so restarts keep plans and completion records.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from ..config import atomic_write, default_state_dir, proxy_from_settings, resolve_media_path
from . import huangguo
from .huangguo import HuangguoError
from .yeguo import Client as YeguoClient

# 站点源注册表：新增站点只需提供同名 Client（search/detail/episode_stream/
# episode_page_url/fetch_image/download_hls）并在此登记。
SOURCES = {"huangguo": "黄果短剧", "yeguo": "野果短剧"}
DEFAULT_SOURCE = "huangguo"


def source_label(source):
    return SOURCES.get(str(source or DEFAULT_SOURCE), SOURCES[DEFAULT_SOURCE])


CLIENTS = {"huangguo": huangguo.Client, "yeguo": YeguoClient}


def make_client(source, proxy_url=None):
    """Instantiate the client that owns `source` (falls back to 黄果)."""
    return CLIENTS.get(str(source or DEFAULT_SOURCE), huangguo.Client)(proxy_url=proxy_url)

def hg_root():
    """Default store location: `config/huangguo/`, resolved lazily."""
    return default_state_dir() / "huangguo"
UNITS = {"minute": 60, "hour": 3600, "day": 86400}


def _now():
    return time.time()


def iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def safe_title(value, fallback="短剧"):
    text = re.sub(r'[\\/:*?"<>|\r\n]+', " ", str(value or "")).strip()
    text = re.sub(r"\s{2,}", " ", text)
    return (text or fallback)[:120]


def season_dir_label(season=1):
    return f"Season {max(1, int(season)):02d}"


def episode_stem(title, season, episode):
    return f"{safe_title(title)} - S{int(season):02d}E{int(episode):02d}"


def video_dir_name(info, suffix=""):
    """`标题 (年份)`; unknown year is omitted, never invented. `suffix` (source id)
    is passed by the manager only when another show shares the same title."""
    title = safe_title(info.get("title"))
    year = str(info.get("premiered") or "").strip()
    if re.fullmatch(r"(19|20)\d{2}", year):
        title = f"{title} ({year})"
    return f"{title} [{suffix}]" if suffix else title


def clean_plot(description, title=""):
    """NFO 简介清洗：与解析层共用同一套模板剥离规则（标题+全N集+更新日期头、广告尾）。"""
    return huangguo.clean_description(description)


class SubscriptionStore:
    """JSON-backed subscriptions with defaults from system settings."""

    def __init__(self, root=None):
        self.root = Path(root or hg_root())
        self.path = self.root / "subscriptions.json"
        self.lock = threading.RLock()
        self.items = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raw = {}
            for item in raw.get("subscriptions", []):
                if isinstance(item, dict) and item.get("id"):
                    self.items[str(item["id"])] = self._normalize(item)

    def _save(self):
        payload = {"version": 1, "subscriptions": [self.items[k] for k in sorted(self.items)]}
        atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2).encode())

    def _normalize(self, item):
        sub = {
            "id": str(item.get("id") or ""),
            "source": item.get("source") if item.get("source") in SOURCES else DEFAULT_SOURCE,
            "videoId": str(item.get("videoId") or ""),
            "title": safe_title(item.get("title")),
            "url": str(item.get("url") or ""),
            "cover": str(item.get("cover") or ""),
            "description": str(item.get("description") or "")[:500],
            "tags": list(item.get("tags") or [])[:10],
            "premiered": str(item.get("premiered") or ""),
            "actors": str(item.get("actors") or ""),
            "autoCheck": bool(item.get("autoCheck", True)),
            "intervalValue": max(1, min(int(item.get("intervalValue") or 6), 9999)),
            "intervalUnit": item.get("intervalUnit") if item.get("intervalUnit") in UNITS else "hour",
            "saveRoot": resolve_media_path(item.get("saveRoot")),
            "autoDownload": bool(item.get("autoDownload", True)),
            "scope": item.get("scope") if item.get("scope") in ("all", "new", "list") else "new",
            "episodeList": sorted({int(e) for e in item.get("episodeList") or [] if str(e).isdigit()})[:5000],
            "lastChecked": float(item.get("lastChecked") or 0),
            "nextCheck": float(item.get("nextCheck") or 0),
            "knownEpisodes": sorted({int(e) for e in item.get("knownEpisodes") or [] if str(e).isdigit()})[:5000],
            "total": int(item.get("total") or 0),
            "createdAt": float(item.get("createdAt") or _now()),
            "baseline": sorted({int(e) for e in item.get("baseline") or [] if str(e).isdigit()})[:5000],
        }
        return sub

    def interval_seconds(self, sub):
        return sub["intervalValue"] * UNITS[sub["intervalUnit"]]

    def add(self, info, settings_defaults, **overrides):
        with self.lock:
            video_id = str(info["id"])
            source = info.get("source") if info.get("source") in SOURCES else DEFAULT_SOURCE
            for existing in self.items.values():
                # 两个站点可能用相同数字 id，订阅唯一性按「源 + 站点 id」判断
                if existing["videoId"] == video_id and existing["source"] == source:
                    raise ValueError("该短剧已在订阅中")
            sub = self._normalize({
                "id": uuid.uuid4().hex[:12],
                "source": source,
                "videoId": video_id,
                "title": info.get("title"),
                "url": info.get("url"),
                "cover": info.get("cover"),
                "description": info.get("description"),
                "tags": info.get("tags"),
                "premiered": info.get("premiered"),
                "actors": info.get("actors"),
                "total": info.get("total"),
                "knownEpisodes": info.get("episodes"),
                "autoCheck": overrides.get("autoCheck", True),
                "intervalValue": overrides.get("intervalValue", settings_defaults.get("hgIntervalValue", 6)),
                "intervalUnit": overrides.get("intervalUnit", settings_defaults.get("hgIntervalUnit", "hour")),
                "saveRoot": resolve_media_path(overrides.get("saveRoot") or settings_defaults.get("hgSaveRoot", "")),
                "autoDownload": overrides.get("autoDownload", True),
                "scope": overrides.get("scope", "new"),
                "episodeList": overrides.get("episodeList", []),
            })
            if not sub["saveRoot"]:
                raise ValueError("请为该订阅设置保存路径")
            if sub["scope"] == "new":
                # baseline：已存在的集不算"后续新增"
                sub["baseline"] = sorted({int(e) for e in info.get("episodes") or []})
            sub["nextCheck"] = _now() if sub["autoCheck"] else 0
            self.items[sub["id"]] = sub
            self._save()
            return copy.deepcopy(sub)

    def update(self, sub_id, changes):
        with self.lock:
            sub = self.items.get(str(sub_id))
            if not sub:
                raise KeyError("订阅不存在")
            before = (sub["intervalValue"], sub["intervalUnit"], sub["autoCheck"])
            merged = self._normalize({**sub, **{k: v for k, v in changes.items() if k in sub}})
            merged["intervalValue"] = max(1, min(merged["intervalValue"], 9999))
            self.items[sub["id"]] = merged
            reschedule = before != (merged["intervalValue"], merged["intervalUnit"], merged["autoCheck"])
            if not merged["autoCheck"]:
                merged["nextCheck"] = 0
            elif reschedule or not merged["nextCheck"]:
                merged["nextCheck"] = _now()
            self._save()
            return copy.deepcopy(merged)

    def remove(self, sub_id):
        with self.lock:
            if self.items.pop(str(sub_id), None) is None:
                raise KeyError("订阅不存在")
            self._save()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(list(self.items.values()))


class DownloadRecord:
    """Per-episode completion ledger keyed by (videoId, episode)."""

    def __init__(self, root=None):
        self.root = Path(root or hg_root())
        self.path = self.root / "downloads.json"
        self.lock = threading.RLock()
        self.records = {}
        if self.path.exists():
            try:
                self.records = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.records = {}

    def key(self, video_id, episode, source=DEFAULT_SOURCE):
        """`source:videoId:episode`; the 黄果 prefix is omitted to keep old ledgers."""
        head = f"{source}:" if source and source != DEFAULT_SOURCE else ""
        return f"{head}{int(video_id) if str(video_id).isdigit() else video_id}:{int(episode)}"

    def prefix(self, video_id, source=DEFAULT_SOURCE):
        head = f"{source}:" if source and source != DEFAULT_SOURCE else ""
        return f"{head}{int(video_id) if str(video_id).isdigit() else video_id}:"

    def is_done(self, video_id, episode, source=DEFAULT_SOURCE):
        with self.lock:
            record = self.records.get(self.key(video_id, episode, source))
            return bool(record) and record.get("state") == "done" and Path(record.get("path", "")).is_file()

    def mark(self, video_id, episode, path, size, thumb=None, thumb_error=None, state="done",
             source=DEFAULT_SOURCE):
        with self.lock:
            self.records[self.key(video_id, episode, source)] = {
                "state": state, "path": str(path), "size": int(size),
                "thumb": str(thumb) if thumb else None,
                "thumbError": thumb_error,
                "at": iso(_now()),
            }
            self._save()

    def mark_thumb(self, video_id, episode, thumb=None, error=None, source=DEFAULT_SOURCE):
        with self.lock:
            record = self.records.get(self.key(video_id, episode, source))
            if not record:
                raise KeyError("下载记录不存在")
            if thumb:
                record["thumb"] = str(thumb)
                record["thumbError"] = None
            else:
                record["thumbError"] = str(error)[:200]
            self._save()

    def _save(self):
        atomic_write(self.path, json.dumps(self.records, ensure_ascii=False, indent=2).encode())

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.records)


def tvshow_nfo(info):
    def el(tag, value):
        return [] if value in (None, "") else [ET.SubElement(root, tag)]
    root = ET.Element("tvshow")
    for tag, value in (("title", safe_title(info.get("title"))),
                       ("originaltitle", info.get("title") or ""),
                       ("plot", clean_plot(info.get("description"), info.get("title"))),
                       ("premiered", info.get("premiered") or ""),
                       ("studio", source_label(info.get("source")))):
        if value:
            ET.SubElement(root, tag).text = str(value)
    for value in info.get("tags") or []:
        ET.SubElement(root, "genre").text = str(value)
    for value in (info.get("actors") or "").replace("，", ",").split(","):
        if value.strip():
            actor = ET.SubElement(root, "actor")
            ET.SubElement(actor, "name").text = value.strip()
    ET.SubElement(root, "uniqueid", {"type": str(info.get("source") or DEFAULT_SOURCE), "default": "true"}).text = \
        str(info.get("videoId") or info.get("id") or "")
    ET.SubElement(root, "source").text = str(info.get("url") or "")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def episode_nfo(info, title, season, episode):
    """分集 NFO 按需求不含内容简介：站点每集简介同为全剧模板，剧级 plot 足够。"""
    root = ET.Element("episodedetails")
    ET.SubElement(root, "title").text = title or f"第{episode}集"
    ET.SubElement(root, "season").text = str(int(season))
    ET.SubElement(root, "episode").text = str(int(episode))
    ET.SubElement(root, "uniqueid", {"type": str(info.get("source") or DEFAULT_SOURCE), "default": "true"}).text = \
        f"{info.get('videoId') or info.get('id')}-{episode}"
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


class HuangguoManager:
    """Scheduler + task runner; mirrors the hanime TaskManager's event model."""

    def __init__(self, settings_provider, logger=None, root=None):
        self.settings_provider = settings_provider
        self.logger = logger or (lambda msg, level="info": None)
        self.store = SubscriptionStore(root)
        self.records = DownloadRecord(root)
        self._dir_cache = {}
        self._dir_lock = threading.Lock()
        self._cover_cache = {}
        self.tasks = []
        self.lock = threading.RLock()
        self.revision = 0
        self.stop = threading.Event()
        self._threads = {}
        self._scheduler = None

    def delete_downloaded(self, sub):
        """Remove only the show directory, and only inside its own saveRoot."""
        import shutil
        show = Path(sub["saveRoot"]) / self.show_dir_name(sub)
        root = Path(sub["saveRoot"]).resolve()
        resolved = show.resolve()
        if not resolved.is_relative_to(root) or resolved == root:
            raise ValueError("删除范围无效，已中止")
        if not resolved.is_dir():
            return None
        shutil.rmtree(resolved)
        stale = [k for k, rec in self.records.snapshot().items()
                 if str(rec.get("path", "")).startswith(str(resolved))]
        with self.records.lock:
            for key in stale:
                self.records.records.pop(key, None)
            self.records._save()
        return str(resolved)

    # ---------------- helpers ----------------
    def settings(self):
        return self.settings_provider()

    def show_dir_name(self, sub):
        """Stable unique directory name. The earliest subscription of a shared
        title keeps the plain name; later ones get the source-id suffix."""
        base = video_dir_name(sub)
        with self._dir_lock:
            cached = self._dir_cache.get(sub["id"])
            if cached:
                return cached
            rivals = sorted((s for s in self.store.snapshot()
                             if video_dir_name(s) == base and s["id"] != sub["id"]
                             and s.get("source", DEFAULT_SOURCE) == sub.get("source", DEFAULT_SOURCE)),
                            key=lambda s: (s["createdAt"], s["id"]))
            earlier = any(r["createdAt"] < sub["createdAt"] or
                          (r["createdAt"] == sub["createdAt"] and r["id"] < sub["id"])
                          for r in rivals)
            name = video_dir_name(sub, suffix=sub["videoId"]) if rivals and earlier else base
            self._dir_cache[sub["id"]] = name
            return name

    def _client(self, source=None):
        proxy = proxy_from_settings(self.settings())
        return make_client(source, proxy_url=proxy)

    def _client_for(self, sub):
        """Client for one subscription's source; the default source keeps using
        `_client()` so existing tests/overrides that patch `_client` still work."""
        source = str((sub or {}).get("source") or DEFAULT_SOURCE)
        if source == DEFAULT_SOURCE:
            return self._client()
        return self._client(source)

    def log(self, message, level="info", sub_id=None):
        self.logger(message, level)

    # ---------------- task plumbing ----------------
    def _new_task(self, kind, sub_id, detail=None, message=""):
        sub = self.store.items.get(str(sub_id)) or {}
        title = sub.get("title", "")
        task = {"id": uuid.uuid4().hex[:10], "kind": kind, "subscriptionId": sub_id,
                "subscriptionTitle": title,
                "source": sub.get("source", DEFAULT_SOURCE),
                "sourceLabel": source_label(sub.get("source")),
                "state": "waiting", "progress": 0, "indeterminate": True,
                "createdAt": _now(), "startedAt": None, "finishedAt": None,
                "error": "", "detail": detail or "", "attempts": 0,
                "currentEpisode": None, "message": ""}
        with self.lock:
            self.tasks.append(task)
            self.revision += 1
        if message:
            self.log(f"{message}（{title}）" if title else message)
        return task

    def running_for(self, sub_id):
        with self.lock:
            return [t for t in self.tasks if t["subscriptionId"] == sub_id
                    and t["state"] in ("waiting", "downloading", "checking")]

    def _task(self, task_id):
        with self.lock:
            for task in self.tasks:
                if task["id"] == task_id:
                    return task
        return None

    def _update_task(self, task, **changes):
        with self.lock:
            task.update(changes)
            self.revision += 1

    def snapshot_tasks(self):
        with self.lock:
            trimmed = [{k: v for k, v in task.items() if not k.startswith("_")}
                       for task in self.tasks[-200:]]
            revision = self.revision
        return {"tasks": trimmed, "revision": revision}

    #: 这些状态的任务还在跑，一键清空时要保留，避免界面丢掉正在进行的进度。
    ACTIVE_STATES = ("waiting", "downloading", "checking")

    def clear_tasks(self):
        """Drop finished task records; running ones stay so their progress is not lost."""
        with self.lock:
            kept = [t for t in self.tasks if t["state"] in self.ACTIVE_STATES]
            cleared = len(self.tasks) - len(kept)
            self.tasks = kept
            alive = {t["id"] for t in kept}
            for task_id in [k for k in self._threads if k not in alive]:
                self._threads.pop(task_id, None)
            if cleared:
                self.revision += 1
            remaining = len(self.tasks)
        if cleared:
            self.log(f"已清空 {cleared} 条任务记录" + (f"，保留 {remaining} 条进行中任务" if remaining else ""))
        return {"cleared": cleared, "remaining": remaining}

    def cancel(self, task_id):
        task = self._task(task_id)
        if not task or task["state"] not in ("waiting", "downloading", "checking"):
            return False
        stop = task.get("_stop")
        if stop:
            stop.set()
        self._update_task(task, state="cancelled", finishedAt=_now(), error="已取消")
        return True

    def retry(self, task_id):
        task = self._task(task_id)
        if not task or task["state"] not in ("failed", "cancelled"):
            return False
        sub = self.store.items.get(task["subscriptionId"])
        if not sub:
            return False
        if task["kind"] == "download":
            episodes = (task.get("detail") or {}).get("episodes") or []
            self.enqueue_download(sub["id"], episodes, reason="重试")
        else:
            self.enqueue_check(sub["id"], reason="重试")
        return True

    # ---------------- public actions ----------------
    def enqueue_check(self, sub_id, reason="定时"):
        sub = self.store.items.get(str(sub_id))
        if not sub:
            raise KeyError("订阅不存在")
        for task in self.running_for(sub_id):
            if task["kind"] == "check":
                return task
        task = self._new_task("check", sub_id, detail={"reason": reason}, message=f"开始检查更新（{reason}）")
        self._spawn(task, lambda: self._run_check(task, sub))
        return task

    def enqueue_download(self, sub_id, episodes=None, reason="手动"):
        sub = self.store.items.get(str(sub_id))
        if not sub:
            raise KeyError("订阅不存在")
        for task in self.running_for(sub_id):
            if task["kind"] == "download":
                raise ValueError("该订阅已有下载任务进行中")
        chosen = sorted({int(e) for e in episodes or []})
        if not chosen:
            chosen = self.missing_episodes(sub)
        if not chosen:
            return None
        span = f"{chosen[0]}-{chosen[-1]}" if len(chosen) > 1 else str(chosen[0])
        task = self._new_task("download", sub_id, detail={"episodes": chosen, "reason": reason},
                              message=f"加入下载队列（{reason}，共 {len(chosen)} 集：E{span}）")
        self._spawn(task, lambda: self._run_download(task, sub, chosen))
        return task

    def enqueue_thumb(self, sub_id, episode, reason="补截图"):
        sub = self.store.items.get(str(sub_id))
        if not sub:
            raise KeyError("订阅不存在")
        task = self._new_task("thumb", sub_id, detail={"episode": int(episode), "reason": reason},
                              message=f"补做第 {episode} 集截帧图（第10帧）")
        self._spawn(task, lambda: self._run_thumb(task, sub))
        return task

    def wanted_episodes(self, sub):
        known = set(sub["knownEpisodes"])
        if sub["scope"] == "list":
            return sorted(set(sub["episodeList"]))
        if sub["scope"] == "all":
            return sorted(known) if known else list(range(1, max(1, sub["total"] or 1) + 1))
        # "new"：订阅基线之后的集数
        baseline = set(sub.get("baseline") or [])
        return sorted(e for e in known if e not in baseline)

    def missing_episodes(self, sub):
        return [e for e in self.wanted_episodes(sub)
                if not self.records.is_done(sub["videoId"], e, sub.get("source"))]

    # ---------------- scheduler ----------------
    def start(self):
        self.stop.clear()
        self._scheduler = threading.Thread(target=self._scheduler_loop, daemon=True, name="hg-scheduler")
        self._scheduler.start()

    def close(self):
        self.stop.set()
        # 等后台线程退出再返回：调度线程每 2 秒醒来一次，检查线程会写订阅
        # nextCheck/任务记录，不 join 就会和调用方的目录清理竞态
        # （tempfile 报「Directory not empty」）。给的是总预算而不是每个线程
        # 各等一次，否则线程多时关闭会被拖成十几秒。下载线程可能正在传大文件，
        # 只在其已经空闲时才等待，避免关闭被长时间阻塞。
        deadline = time.time() + 1.2
        current = threading.current_thread()
        thread = self._scheduler
        if thread and thread.is_alive() and thread is not current:
            thread.join(timeout=max(0.0, deadline - time.time()))
        with self.lock:
            pending = [t for t in self._threads.values() if t.is_alive() and t is not current]
        for worker in pending:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            worker.join(timeout=remaining)

    def _scheduler_loop(self):
        while not self.stop.wait(2):
            try:
                now = _now()
                for sub in self.store.snapshot():
                    if not sub["autoCheck"]:
                        continue
                    if sub["nextCheck"] and now < sub["nextCheck"]:
                        continue
                    if self.running_for(sub["id"]):
                        continue
                    self.enqueue_check(sub["id"], reason="定时")
            except Exception as exc:  # noqa: BLE001
                self.log(f"订阅调度异常：{exc}", "warn")

    def _spawn(self, task, work):
        def guard():
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                label = {"check": "检查更新", "download": "下载", "thumb": "首帧图"}.get(task["kind"], task["kind"])
                self._update_task(task, state="failed", error=str(exc)[:300],
                                  finishedAt=_now(), indeterminate=False)
                self.log(f"《{task.get('subscriptionTitle') or task['subscriptionId']}》{label}失败：{exc}", "error")
        thread = threading.Thread(target=guard, daemon=True, name=f"hg-{task['id']}")
        task["_stop"] = threading.Event()
        with self.lock:
            self._threads[task["id"]] = thread
        thread.start()

    # ---------------- workers ----------------
    def _run_check(self, task, sub):
        client = self._client_for(sub)
        self._update_task(task, state="checking", startedAt=_now(), message="检查更新")
        self.log(f"《{sub['title']}》正在读取详情页核对集数")
        info = client.detail(sub["videoId"])
        fresh = sorted({int(e) for e in info.get("episodes") or []})
        known = set(sub["knownEpisodes"])
        added = [e for e in fresh if e not in known]
        self.store.update(sub["id"], {"lastChecked": _now(),
                                      "nextCheck": _now() + self.store.interval_seconds(sub) if sub["autoCheck"] else 0,
                                      "knownEpisodes": fresh, "total": info.get("total") or len(fresh),
                                      "cover": info.get("cover") or sub["cover"],
                                      "description": info.get("description") or sub["description"],
                                      "tags": info.get("tags") or sub["tags"],
                                      "title": info.get("title") or sub["title"],
                                      "premiered": info.get("premiered") or sub["premiered"],
                                      "actors": info.get("actors") or sub["actors"]})
        first = not known
        if first:
            baseline = set(sub.get("baseline") or [])
            added = [e for e in fresh if e not in baseline] if sub["scope"] == "new" else list(fresh)
        else:
            added = [e for e in fresh if e not in known]
        current = self.store.items[sub["id"]]
        prev_cover = str(sub.get("cover") or "")
        new_cover = str(info.get("cover") or "")
        current_desc = str(current.get("description") or "")
        cover_changed = bool(new_cover) and Path(prev_cover.split("?")[0]).name != Path(new_cover.split("?")[0]).name
        desc_changed = current_desc != str(sub.get("description") or "")
        show_dir = Path(sub["saveRoot"]) / self.show_dir_name(sub)
        if show_dir.is_dir():
            if cover_changed:
                try:
                    data = client.fetch_image(new_cover, referer=sub["url"])
                    if data:
                        atomic_write(show_dir / "poster.jpg", data)
                        self.log(f"《{sub['title']}》封面源已变化，poster.jpg 已更新（{len(data)} 字节）")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"《{sub['title']}》封面更新失败：{exc}", "warn")
            legacy = self._legacy_episode_nfo(show_dir, sub["videoId"])
            if cover_changed or desc_changed or legacy:
                try:
                    rewritten = self.rewrite_nfos(current, show_dir)
                    reason = "分集简介格式升级" if legacy and not (cover_changed or desc_changed) else "元数据更新"
                    self.log(f"《{sub['title']}》NFO 已重写（{reason}）：{'、'.join(rewritten[:3])}"
                             + ("…" if len(rewritten) > 3 else ""))
                except Exception as exc:  # noqa: BLE001
                    self.log(f"《{sub['title']}》NFO 重写失败：{exc}", "warn")
        # 旧版本可能把推荐位算进基线（如基线 1..13 而实际只有 3 集），导致新增永远被判为已存在
        baseline = set(current.get("baseline") or [])
        if baseline and max(baseline) > max(fresh or [1]):
            healed = sorted(set(range(1, max(fresh or [1]) + 1)) & baseline)
            self.store.update(sub["id"], {"baseline": healed})
            current = self.store.items[sub["id"]]
            self.log(f"《{sub['title']}》基线集数已修正：{len(baseline)} → {len(healed)}")
            if first and current["scope"] == "new":
                added = [e for e in fresh if e not in healed]
        missing = self.missing_episodes(current)
        note = f"新增 {len(added)} 集" if added else "无新集数"
        if missing:
            note += f"，{len(missing)} 集待下载"
        self._update_task(task, state="completed", progress=100, indeterminate=False,
                          finishedAt=_now(), message=note,
                          detail={"reason": task["detail"].get("reason") if isinstance(task["detail"], dict) else "",
                                  "added": added, "missing": missing})
        if added:
            self.log(f"《{sub['title']}》检查结果：发现新集数 {added}", "info")
        elif missing:
            self.log(f"《{sub['title']}》检查结果：无新集数，{len(missing)} 集待下载", "info")
        else:
            self.log(f"《{sub['title']}》检查结果：无新集数，全部已下载（共 {len(fresh)} 集）", "info")
        if missing:
            reason = (task["detail"] or {}).get("reason", "") if isinstance(task.get("detail"), dict) else ""
            manual = reason not in ("", "定时")
            if sub["autoDownload"] or manual:
                label = "手动检查补齐" if manual and not sub["autoDownload"] else "检查补齐"
                try:
                    self.enqueue_download(sub["id"], missing, reason=label)
                except ValueError:
                    self.log(f"《{sub['title']}》已有任务进行中，本次补齐稍后自动执行", "info")
            else:
                self.log(f"《{sub['title']}》有 {len(missing)} 集未下载（自动下载已关闭，可在订阅卡片手动下载）", "info")

    def _run_download(self, task, sub, episodes):
        client = self._client_for(sub)
        sub = self.store.items[sub["id"]]
        save_root = Path(sub["saveRoot"])
        show_dir = save_root / self.show_dir_name(sub)
        season = show_dir / season_dir_label(1)
        season.mkdir(parents=True, exist_ok=True)
        self._write_show_meta(client, sub, show_dir)
        settings = self.settings()
        workers = int(settings.get("hgConcurrent", 4))
        retries = max(0, int(settings.get("hgRetries", 2)))
        retry_wait = max(0, int(settings.get("hgRetryInterval", 30)))
        ok, failed = [], []
        for index, ep in enumerate(episodes):
            if task.get("_stop").is_set():
                self._update_task(task, state="cancelled", finishedAt=_now())
                return
            self._update_task(task, state="downloading", startedAt=task.get("startedAt") or _now(),
                              currentEpisode=ep, indeterminate=True,
                              message=f"下载第 {ep} 集（{index + 1}/{len(episodes)}）")
            self.log(f"《{sub['title']}》开始下载第 {ep} 集（{index + 1}/{len(episodes)}）：解析分集页与播放地址")
            if self.records.is_done(sub["videoId"], ep, sub.get("source")):
                ok.append(ep)
                continue
            last_error = ""
            for attempt in range(retries + 1):
                task["attempts"] = attempt + 1
                try:
                    self._download_one(client, sub, show_dir, season, ep, workers, task=task)
                    ok.append(ep)
                    last_error = ""
                    task.pop("_progressAt", None)
                    self._update_task(task, progress=int((index + 1) / len(episodes) * 100),
                                      message=f"第 {ep} 集完成（{index + 1}/{len(episodes)}）")
                    self.log(f"《{sub['title']}》第 {ep} 集下载完成（{index + 1}/{len(episodes)}）")
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)[:200]
                    if attempt < retries and not task.get("_stop").is_set():
                        time.sleep(retry_wait)
            if last_error:
                failed.append({"episode": ep, "error": last_error})
                self.log(f"《{sub['title']}》第{ep}集下载失败：{last_error}", "error")
            self._update_task(task, progress=int((index + 1) / len(episodes) * 100), indeterminate=False)
        with self.lock:
            final_state = "cancelled" if task.get("_stop").is_set() else ("completed" if not failed else "failed")
        summary = f"完成 {len(ok)} 集" + (f"，失败 {len(failed)} 集" if failed else "")
        self._update_task(task, state=final_state, finishedAt=_now(),
                          error="；".join(f"第{f['episode']}集：{f['error']}" for f in failed[:3]) if failed else "",
                          message=summary)
        self.log(f"《{sub['title']}》下载任务结束：{summary}", "error" if final_state == "failed" else "info")
        self._update_task(task, detail={**task["detail"], "ok": ok, "failed": failed})

    def _download_one(self, client, sub, show_dir, season, ep, workers, task=None):
        video = season / f"{episode_stem(sub['title'], 1, ep)}.mp4"
        m3u8 = client.episode_stream(sub["videoId"], ep, sub["title"])
        referer = client.episode_page_url(sub["videoId"], ep)
        # 播放地址带短时签名，出问题时需要原样核对，故按解析结果直接记录。
        self.log(f"《{sub['title']}》第 {ep} 集播放地址：{m3u8}")
        settings = self.settings()
        proxy = proxy_from_settings(settings)

        def on_segment(done, seg_total):
            if not task:
                return
            percent = int(done / max(1, seg_total) * 100)
            stamp = int(_now())
            # 节流：同秒内仅当百分比变化才更新，避免高频加锁/刷 revision
            last = task.get("_progressAt")
            if last and last[0] == stamp and last[1] // 5 == percent // 5:
                return
            task["_progressAt"] = (stamp, percent)
            self._update_task(task, progress=percent, indeterminate=False,
                              message=f"第 {ep} 集下载中 {done}/{seg_total} 分片（{percent}%）")

        total = client.download_hls(m3u8, referer, video, proxy=proxy, workers=max(1, min(workers, 8)),
                                    segment_limit=None, progress=on_segment,
                                    refresh=lambda: client.episode_stream(sub["videoId"], ep, sub["title"]))
        if task:
            self._update_task(task, message=f"第 {ep} 集合并转码中…", progress=99, indeterminate=True)
        self._episode_meta(client, sub, season, ep)
        thumb = video.with_name(video.stem + "-thumb.jpg")
        thumb_error = None
        try:
            client.first_frame_thumb(video, thumb, proxy=None)
        except Exception as exc:  # noqa: BLE001
            thumb_error = str(exc)[:200]
        self.records.mark(sub["videoId"], ep, video, total, thumb=thumb if thumb.is_file() else None,
                          thumb_error=thumb_error, source=sub.get("source"))
        if thumb_error:
            self.log(f"《{sub['title']}》第 {ep} 集截帧图失败（视频已保存）：{thumb_error}", "warn")

    def _legacy_episode_nfo(self, show_dir, video_id=None):
        """True if any episode NFO carries the old <plot> intro or wrong uniqueid."""
        season = show_dir / season_dir_label(1)
        if not season.is_dir():
            return False
        for nfo in season.glob("* - S01E*.nfo"):
            try:
                text = nfo.read_text(encoding="utf-8")
            except OSError:
                continue
            if "<plot>" in text:
                return True
            if video_id:
                match = re.search(r'<uniqueid[^>]*>([^<]*)</uniqueid>', text)
                if match and not match.group(1).startswith(f"{video_id}-"):
                    return True
        return False

    def rewrite_nfos(self, sub, show_dir):
        """Rewrite show-level and existing episode NFOs with cleaned plot text."""
        written = []
        (show_dir / "tvshow.nfo").write_text(tvshow_nfo(sub), encoding="utf-8")
        written.append("tvshow.nfo")
        season = show_dir / season_dir_label(1)
        if season.is_dir():
            for video in sorted(season.glob("* - S01E*.mp4")):
                match = re.search(r"S01E(\d{2})$", video.stem)
                if not match:
                    continue
                ep = int(match.group(1))
                nfo = video.with_suffix(".nfo")
                nfo.write_text(episode_nfo(sub, f"第{ep}集", 1, ep), encoding="utf-8")
                written.append(f"{video.stem}.nfo")
        return written

    def _write_show_meta(self, client, sub, show_dir):
        tvshow = show_dir / "tvshow.nfo"
        if not tvshow.exists():
            tvshow.write_text(tvshow_nfo(sub), encoding="utf-8")
            self.log(f"《{sub['title']}》已写入 tvshow.nfo")
        poster = show_dir / "poster.jpg"
        if sub.get("cover") and not poster.exists():
            try:
                data = client.fetch_image(sub["cover"], referer=sub["url"])
                if data:
                    atomic_write(poster, data)
                    self.log(f"《{sub['title']}》封面已保存 poster.jpg（{len(data)} 字节）")
            except Exception as exc:  # noqa: BLE001
                self.log(f"封面保存失败：{exc}", "warn")

    def _episode_meta(self, client, sub, season, ep):
        stem = episode_stem(sub["title"], 1, ep)
        nfo = season / f"{stem}.nfo"
        if not nfo.exists():
            nfo.write_text(episode_nfo(sub, f"第{ep}集", 1, ep), encoding="utf-8")

    def _run_thumb(self, task, sub):
        ep = task["detail"]["episode"]
        client = self._client_for(sub)
        season = Path(sub["saveRoot"]) / self.show_dir_name(sub) / season_dir_label(1)
        video = season / f"{episode_stem(sub['title'], 1, ep)}.mp4"
        if not video.is_file():
            raise HuangguoError("视频文件不存在，无法截图")
        thumb = video.with_name(video.stem + "-thumb.jpg")
        self._update_task(task, state="downloading", startedAt=_now(), message="截取第 10 帧")
        client.first_frame_thumb(video, thumb)
        self.records.mark_thumb(sub["videoId"], ep, thumb=thumb, source=sub.get("source"))
        self._update_task(task, state="completed", finishedAt=_now(), progress=100, indeterminate=False,
                          message="缩略图已生成")
        self.log(f"《{sub['title']}》第 {ep} 集截帧图（第10帧）已生成")

    def repair_assets(self, sub_id, description=None, title=None):
        """Re-fetch the correct poster, rewrite NFOs and refresh cover/description.

        Used for subscriptions created before the cover/description parsing fix,
        which stored the wrong image and template-polluted plots.
        """
        sub = self.store.items.get(str(sub_id))
        if not sub:
            raise KeyError("订阅不存在")
        client = self._client_for(sub)
        info = client.detail(sub["videoId"])
        changes = {"cover": info.get("cover") or sub["cover"],
                   "description": info.get("description") or sub["description"],
                   "tags": info.get("tags") or sub["tags"],
                   "title": info.get("title") or sub["title"],
                   "premiered": info.get("premiered") or sub["premiered"],
                   "actors": info.get("actors") or sub["actors"]}
        self.store.update(sub["id"], changes)
        merged = self.store.items[sub["id"]]
        show_dir = Path(merged["saveRoot"]) / self.show_dir_name(merged)
        written = []
        if info.get("cover"):
            try:
                data = client.fetch_image(info["cover"], referer=merged["url"])
                if data:
                    atomic_write(show_dir / "poster.jpg", data)
                    written.append(f"poster.jpg（{len(data)} 字节）")
            except Exception as exc:  # noqa: BLE001
                self.log(f"《{merged['title']}》封面修复失败：{exc}", "warn")
        if show_dir.is_dir():
            written.extend(self.rewrite_nfos(merged, show_dir))
        self.log(f"《{merged['title']}》已修复订阅资源：" + "、".join(written))
        return {"cover": changes["cover"], "written": written}

    # ---------------- views ----------------
    def cover_image(self, sub_id):
        """Return poster bytes for a subscription: local file first, then the site.

        Stale cover URLs (signed links expire) are re-resolved from the detail page
        and the fresh copy is cached as poster.jpg so later reads stay offline.
        """
        sub = self.store.items.get(str(sub_id))
        if not sub:
            raise KeyError("订阅不存在")
        show_dir = Path(sub["saveRoot"]) / self.show_dir_name(sub)
        poster = show_dir / "poster.jpg"
        if poster.is_file() and poster.stat().st_size > 1024:
            return poster.read_bytes()
        cached = self._cover_cache.get(str(sub_id))
        if cached and _now() - cached[0] < 600:
            return cached[1]
        client = self._client_for(sub)
        data = None
        if sub.get("cover"):
            try:
                data = client.fetch_image(sub["cover"], referer=sub["url"])
            except Exception:  # 签名过期或图床异常，回落到详情页重新解析
                data = None
        if not data:
            info = client.detail(sub["videoId"])
            fresh = info.get("cover") or ""
            if fresh:
                data = client.fetch_image(fresh, referer=info.get("url") or sub["url"])
                self.store.update(sub["id"], {"cover": fresh})
        if not data:
            raise HuangguoError("封面获取失败，请稍后重试或点击“修复封面”")
        self._cover_cache[str(sub_id)] = (_now(), data)
        if poster.parent.is_dir():
            try:
                atomic_write(poster, data)
            except OSError:
                pass
        return data

    def subscriptions_view(self):
        tasks = self.snapshot_tasks()["tasks"]
        active = {}
        for task in tasks:
            if task["state"] in ("waiting", "downloading", "checking") and task["subscriptionId"]:
                active.setdefault(task["subscriptionId"], task)
        out = []
        records = self.records.snapshot()
        for sub in self.store.snapshot():
            done = [int(key.rsplit(":", 1)[1]) for key, rec in records.items()
                    if key.startswith(self.records.prefix(sub["videoId"], sub.get("source")))
                    and rec.get("state") == "done"]
            out.append({**sub, "sourceLabel": source_label(sub.get("source")),
                        "downloadedCount": len(done),
                        "pendingCount": len(self.missing_episodes(sub)),
                        "nextCheckIso": iso(sub["nextCheck"]) if sub["autoCheck"] else None,
                        "lastCheckedIso": iso(sub["lastChecked"]),
                        "activeTask": {k: active.get(sub["id"], {}).get(k) for k in ("id", "kind", "state", "message", "progress")}
                        if sub["id"] in active else None})
        return {"subscriptions": out}
