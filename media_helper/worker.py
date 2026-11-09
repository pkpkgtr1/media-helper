"""单个后台任务的执行进程：stdout 是 JSONL 事件流，其余输出全部走 stderr。

任务由 `server.TaskManager` 以 `python -u -m media_helper.worker JOB.json` 拉起，
一个子进程只服务一个任务，因此这里的超时、代理、UA 设置不会互相串味。
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable

if __package__ in (None, ""):
    # 被 `python media_helper/worker.py JOB.json` 直接执行时没有父包，相对导入
    # 会抛 "attempted relative import with no known parent package"；这里改用
    # 模块方式重新拉起自己，行为与 TaskManager 的 `-m media_helper.worker` 一致。
    import subprocess
    raise SystemExit(subprocess.call(
        [sys.executable, "-u", "-m", "media_helper.worker", *sys.argv[1:]],
        cwd=str(Path(__file__).resolve().parents[1]),
    ))

from . import net
from .config import PROJECT_ROOT, atomic_write, configure_proxy_env, contained_file, month_directory, publish_month_resolution


def _base_path(month_dir: Path, item: dict) -> Path:
    name = str(item.get("title_fs") or item.get("title") or item.get("id") or "").strip()
    if not name or name in (".", "..") or any(c in name for c in '/\\\0<>:"|?*'):
        raise ValueError("条目文件名无效，无法确定安全的输出路径")
    path = (month_dir / name).resolve()
    if path.parent != month_dir.resolve():
        raise ValueError("条目路径超出所选月份目录")
    for suffix in (".nfo", ".nfo.tmp", "-poster.jpg", "-fanart.jpg", "-screenshot.jpg", ".mp4", ".mp4.part"):
        contained_file(month_dir, str(path) + suffix)
    return path


def _present(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _video_file(path: Path) -> bool:
    if not _present(path):
        return False
    with path.open("rb") as f:
        header = f.read(64)
    return len(header) >= 12 and header[4:8] in (b"ftyp", b"styp", b"moov", b"moof")


def _configure(settings: dict):
    configure_proxy_env(settings)
    net.configure(settings)  # 代理、FlareSolverr 与 UA 一并发布给本进程
    os.environ["PATH"] = str(PROJECT_ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")
    # This process belongs to exactly one job, so request limits cannot leak to
    # another user task. Explicit legacy timeouts are replaced by the UI setting.
    import requests
    original = requests.sessions.Session.request
    timeout = max(1.0, min(float(settings.get("requestTimeout", 30)), 3600.0))
    os.environ["MEDIA_REQUEST_TIMEOUT"] = str(timeout)

    def request(session, method, url, **kwargs):
        kwargs["timeout"] = (min(10.0, timeout), timeout)
        return original(session, method, url, **kwargs)

    requests.sessions.Session.request = request


class Progress:
    def __init__(self, emit: Callable[[dict], None]):
        self.emit = emit
        self.expected = 0
        self.index = 0
        self.failures = []
        self.current = {}

    def log(self, msg, level="info"):
        self.emit({"type": "log", "msg": str(msg), "level": level})

    def legacy(self, event):
        kind = event.get("type")
        if kind == "start":
            self.expected = int(event.get("total") or 0)
            self.emit({"type": "progress", "progress": 0, "indeterminate": not self.expected,
                       "itemTotal": self.expected, "processed": 0, "phase": event.get("phase", "已读取月份列表")})
        elif kind == "item":
            self.index = int(event.get("index") or 1)
            total = self.expected or int(event.get("total") or 0)
            self.current = dict(currentCode=str(event.get("id") or ""), currentTitle=str(event.get("title") or ""),
                                currentIndex=self.index, itemTotal=total)
            self.emit({"type": "progress", "progress": min(99, 100 * (self.index - 1) / total) if total else 0,
                       "indeterminate": not total, "processed": self.index - 1, "phase": event.get("phase", "正在读取详情"), **self.current})
            self.log(f"正在处理第 {self.index}/{total or '?'} 个条目")
        elif kind == "item_done":
            self.emit({"type": "progress", "progress": min(99, 100 * self.index / self.expected) if self.expected else 0,
                       "indeterminate": not self.expected, "processed": self.index, "phase": "本部处理完毕", **self.current})
        elif kind == "asset_error":
            self.failures.append(str(event.get("msg") or "文件处理失败"))
            self.log(self.failures[-1], "error")
        elif kind == "save_nfo":
            self.log("NFO 已保存")
            self.emit({"type": "progress", "progress": min(99, 100 * (self.index - 1) / self.expected) if self.expected else 0,
                       "indeterminate": not self.expected, "phase": "NFO 已保存，正在处理图片", **self.current})
        elif kind == "save_poster":
            self.log("截图已保存" if event.get("mode") == "screenshot" else "图片已保存")
            self.emit({"type": "progress", "progress": min(99, 100 * (self.index - 1) / self.expected) if self.expected else 0,
                       "indeterminate": not self.expected, "phase": "图片已保存", **self.current})
        elif kind == "log":
            self.log(event.get("msg", ""), event.get("level", "info"))


def _download_item(crawler, item, month_dir, settings, progress, index, count):
    base = _base_path(month_dir, item)
    destination = Path(str(base) + ".mp4")
    if settings.get("existingVideo", "skip") == "skip" and _present(destination):
        progress.log(f"第 {index + 1}/{count} 个视频已存在，跳过")
        return
    attempts = max(1, min(int(settings.get("retries", 2)) + 1, 21))
    last_error = None
    for attempt in range(attempts):
        started = time.monotonic()

        def on_progress(*args):
            if len(args) == 2:
                progress.log(args[1])
                # A phase percentage from the external adapter is not bytes.
                progress.emit({"type": "progress", "progress": index * 100 / count, "indeterminate": True})
                return
            if len(args) != 3:
                return
            downloaded, total, _ = args
            downloaded, total = max(0, int(downloaded or 0)), max(0, int(total or 0))
            elapsed = max(0.01, time.monotonic() - started)
            speed = downloaded / elapsed
            fraction = min(1, downloaded / total) if total else 0
            progress.emit({"type": "progress", "progress": min(99, (index + fraction) * 100 / count),
                           "downloaded": downloaded, "total": total, "speed": speed,
                           "eta": max(0, (total - downloaded) / speed) if total and speed else None,
                           "indeterminate": not total})

        progress.emit({"type": "progress", "progress": index * 100 / count, "indeterminate": True})
        try:
            # Same volume => the final os.replace is atomic. The old destination
            # survives every failed attempt, including the legacy cleanup paths.
            with tempfile.TemporaryDirectory(prefix=".media-download-", dir=month_dir) as staging:
                result = crawler.download_video_for_item(dict(item), staging, logger=progress.log,
                                                         progress_callback=on_progress)
                if not result:
                    raise RuntimeError("下载器未返回成功文件")
                result_path = Path(result).resolve()
                if not result_path.is_relative_to(Path(staging).resolve()) or not _video_file(result_path):
                    raise RuntimeError("下载结果不是有效的 MP4 文件")
                os.replace(result_path, destination)
            progress.log(f"第 {index + 1}/{count} 个视频已完成")
            return
        except Exception as exc:
            last_error = exc
            progress.log(f"第 {index + 1} 个视频第 {attempt + 1}/{attempts} 次失败：{exc}", "error")
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"第 {index + 1} 个视频下载失败：{last_error}")


def _repair_files(crawler, items, month_dir, settings, progress):
    session = crawler._make_session()
    for index, item in enumerate(items):
        base = _base_path(month_dir, item)
        nfo = Path(str(base) + ".nfo")
        poster = Path(str(base) + "-poster.jpg")
        fanart = Path(str(base) + "-fanart.jpg")
        if not _present(nfo):
            if not item.get("title"):
                progress.failures.append(f"第 {index + 1} 个条目缺少标题，无法补写 NFO")
            else:
                crawler.write_movie_nfo(str(base), title_raw=str(item["title"]),
                    title_zh=item.get("title_zh", ""), plot_raw=item.get("plot_raw", ""),
                    plot_zh=item.get("plot_zh", ""), premiered=item.get("premiered", ""),
                    tags=item.get("original_tags", item.get("tags", [])),
                    thumb=poster.name, fanart=fanart.name, mid=str(item.get("id", "")),
                    maker=item.get("artist", ""), nfo_settings=settings)
                progress.log("已用现存索引字段补写 NFO；缺失的剧情等字段保留为空")
        for target, url in ((poster, item.get("cover_url")),
                            (fanart, item.get("fanart_url") or item.get("cover_url"))):
            if _present(target):
                continue
            if not url:
                progress.failures.append(f"第 {index + 1} 个条目没有可用图片地址")
                continue
            _, ok, _ = crawler._download_image(session, url, str(target), item.get("url", ""))
            if not ok:
                progress.failures.append(f"第 {index + 1} 个条目图片补齐失败")
        try:
            _download_item(crawler, item, month_dir, {**settings, "existingVideo": "skip"}, progress, index, len(items))
        except Exception as exc:
            progress.failures.append(str(exc))
        progress.emit({"type": "progress", "progress": min(99, (index + 1) * 100 / len(items)), "indeterminate": False})


def run_job(job: dict, emit: Callable[[dict], None], crawler=None):
    settings = job.get("settings") or {}
    year, month = int(job["year"]), int(job["month"])
    if not 1 <= month <= 12 or not 1900 <= year <= 2200:
        raise ValueError("年份或月份无效")
    if job.get("kind") not in ("metadata", "covers", "video", "repair", "resolutions"):
        raise ValueError("未知任务类型")
    month_dir = month_directory(job["outputRoot"], year, month)
    for filename in (f"{year:04d}-{month:02d}.json", f"{year:04d}-{month:02d}.csv", "images"):
        contained_file(month_dir, month_dir / filename)
    month_dir.mkdir(parents=True, exist_ok=True)
    items = job.get("items") or []
    for item in items:
        _base_path(month_dir, item)
    if crawler is None:
        _configure(settings)
        from . import crawler as _crawler
        crawler = _crawler
    progress = Progress(emit)
    cover_site = "ani-map" if settings.get("coverSite") == "animap" else settings.get("coverSite", "dmm")
    kind = job["kind"]
    emit({"type": "progress", "progress": 0, "indeterminate": True})
    if kind == "metadata":
        result = crawler.crawl_month(year, month, str(month_dir.parent),
            progress=progress.legacy, cover_site=cover_site,
            redownload_cover=bool(settings.get("redownloadCover")), nfo_settings=settings)
        if progress.expected and len(result) != progress.expected:
            progress.failures.append(f"应处理 {progress.expected} 个条目，实际完成 {len(result)} 个")
        if not result:
            raise RuntimeError(f"{year}-{month:02d} 网站月份页未返回作品，未生成图片和 NFO；请查看网站筛选结果")
        for item in result:
            base = _base_path(month_dir, item)
            for suffix in (".nfo", "-poster.jpg"):
                if not _present(Path(str(base) + suffix)):
                    progress.failures.append(f"{item.get('title') or item.get('id')} 缺少 {suffix} 文件")
    elif kind == "resolutions":
        from .resolution import read_download_resolutions
        if not items:
            raise ValueError("没有可获取画质的条目")
        progress.legacy(dict(type="start", total=len(items), phase="正在查询下载页画质"))
        session = crawler._make_session()
        for index, item in enumerate(items, 1):
            progress.legacy(dict(type="item", index=index, id=item.get("id"), title=item.get("title"), phase="正在查询下载页画质"))
            try:
                values = read_download_resolutions(item.get("id"), int(settings.get("requestTimeout", 30)) * 1000,
                                                  session=session)
                if not values:
                    raise RuntimeError("下载页未返回可用画质")
                publish_month_resolution(str(month_dir.parent), year, month, item, values)
                progress.log(f"已更新画质：{values[0]}p")
            except Exception as exc:
                progress.failures.append(f"条目 {item.get('id')}：{exc}")
                progress.log(progress.failures[-1], "error")
            progress.legacy(dict(type="item_done"))
    elif kind == "covers":
        if not items:
            raise ValueError("没有可更新封面的条目")
        crawler.redownload_covers_only(year, month, str(month_dir.parent), cover_site=cover_site,
            progress=progress.legacy, items=items, force=True)
    elif kind == "repair":
        if not items:
            raise ValueError("没有可补齐的条目")
        _repair_files(crawler, items, month_dir, settings, progress)
    else:
        if not items:
            raise ValueError("没有可下载的条目")
        for index, item in enumerate(items):
            try:
                _download_item(crawler, item, month_dir, settings, progress, index, len(items))
            except Exception as exc:
                progress.failures.append(str(exc))
            emit({"type": "progress", "progress": min(99, (index + 1) * 100 / len(items)), "indeterminate": False})
            if index + 1 < len(items):
                delay = max(0, min(float(settings.get("downloadInterval", 5000)) / 1000, 3600))
                if delay:
                    progress.log(f"等待 {delay:g} 秒后处理下一条")
                    time.sleep(delay)
    if progress.failures:
        raise RuntimeError(f"{len(progress.failures)} 项处理失败：" + "；".join(progress.failures[:3]))
    emit({"type": "progress", "progress": 100, "indeterminate": False,
          **({"processed": progress.expected, "phase": "处理完成"} if progress.expected else {})})
    emit({"type": "done"})


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    # Keep a separate copy of the pipe for JSON. Redirect FD 1 as well as the
    # Python stream so inherited ffmpeg / yt-dlp output cannot corrupt events.
    event_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with os.fdopen(event_fd, "w", encoding="utf-8", buffering=1) as events:
        def emit(event):
            events.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            events.flush()
        try:
            if len(args) != 1:
                raise ValueError("用法：python -m media_helper.worker JOB_JSON_PATH")
            job = json.loads(Path(args[0]).read_text(encoding="utf-8-sig"))
            with contextlib.redirect_stdout(sys.stderr):
                run_job(job, emit)
            return 0
        except Exception as exc:
            emit({"type": "error", "msg": str(exc)})
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
