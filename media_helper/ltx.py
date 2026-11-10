"""Jasna 资源库（ltx.libray.workers.dev）：抓取、入库与查询。

站点只有一个公开接口 `GET /api/items`，一次返回全量条目，所以这里的同步就是
「拉一次 → 写原始 JSON → upsert 进 SQLite」。数据库结构与根目录的 `ltxdb.py`
保持一致（同一份 `config/ltxdb/ltx.db`），命令行脚本与本服务共用一份数据：
`ltxdb.py` 只是这里的薄壳，改动只需要落在本模块。

字段来源（接口原样）：
    code / title / title_zh / actors[] / date / maker / cover / url / score /
    votes / links[] / pending_links[] / pending / missing / waiting / shot /
    added_at / director / genres[]（形如 "c5=18"）/ subtitle
顶层另有 updated_at（毫秒）、nyaa、avatars{演员: 头像}、genres{"c5=18": [中, 英, 日]}。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://ltx.libray.workers.dev"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 封面域名白名单：只允许站点的图片 CDN，避免这个接口变成任意 URL 代理。
# dmm 是库内少量历史条目的图片来源（pics.dmm.co.jp），与 jdbstatic 同属官方 CDN。
COVER_HOSTS = ("jdbstatic.com", "javdb.com", "pics.dmm.co.jp")

IMAGE_TTL = 12 * 3600
IMAGE_CACHE_MAX = 400

_lock = threading.Lock()
_sync_lock = threading.Lock()
_image_cache: dict[str, tuple[float, bytes, str]] = {}


def default_data_dir() -> Path:
    """与 ltxdb.py 相同的默认目录：约定 > 环境变量 > config/ltxdb。"""
    env = (os.environ.get("LTXDB_HOME") or "").strip()
    if env:
        return Path(env).expanduser()
    # media_helper/ltx.py -> 项目根
    return Path(__file__).resolve().parents[1] / "config" / "ltxdb"


def db_path(data_dir=None) -> Path:
    return Path(data_dir or default_data_dir()) / "ltx.db"


def raw_path(data_dir=None) -> Path:
    return Path(data_dir or default_data_dir()) / "items.json"


# ------------------------------------------------------------------ 抓取
def fetch_items(timeout: int = 120) -> dict:
    """拉全量接口数据。失败时抛 RuntimeError，消息可直接显示给用户。"""
    request = urllib.request.Request(BASE + "/api/items",
                                     headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"资源站返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接资源站：{exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("资源站响应超时，请稍后重试") from exc
    try:
        data = json.loads(payload.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("资源站返回的不是有效 JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError("资源站返回结构异常（缺少 items）")
    return data


# ------------------------------------------------------------------ 入库
SCHEMA = """CREATE TABLE IF NOT EXISTS items (
    code TEXT PRIMARY KEY,
    title TEXT, title_zh TEXT, actors TEXT, date TEXT, maker TEXT,
    cover TEXT, url TEXT, score REAL, votes INTEGER,
    links TEXT, pending_links TEXT, pending INTEGER, missing INTEGER,
    waiting INTEGER, shot TEXT, added_at INTEGER
)"""

# 接口后来新增的字段；老库缺列时按需补上，不重建表。
EXTRA_COLUMNS = (("director", "TEXT"), ("genres", "TEXT"), ("subtitle", "TEXT"))


def connect(path=None) -> sqlite3.Connection:
    target = Path(path or db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    for name, kind in EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {name} {kind}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_date ON items(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_maker ON items(maker)")
    conn.commit()


def _bool(value) -> int:
    return 1 if value else 0


def _json(value) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def sync(timeout: int = 120, data_dir=None, progress=None) -> dict:
    """拉一次全量并写库；返回可直接展示的报告。同一时间只允许一个同步。"""
    say = progress or (lambda _msg: None)
    if not _sync_lock.acquire(blocking=False):
        raise RuntimeError("同步已在进行中")
    started = time.time()
    try:
        say("正在从资源站拉取全量数据…")
        data = fetch_items(timeout=timeout)
        items = data.get("items") or []

        target = Path(data_dir or default_data_dir())
        target.mkdir(parents=True, exist_ok=True)
        raw = target / "items.json"
        temp = target / "items.json.tmp"
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, raw)  # 原子替换，避免中途失败留下半份 JSON
        say(f"接口返回 {len(items)} 条，正在写入数据库…")

        with _lock, connect(target / "ltx.db") as conn:
            init_db(conn)
            conn.executemany("""INSERT OR REPLACE INTO items
                (code,title,title_zh,actors,date,maker,cover,url,score,votes,links,
                 pending_links,pending,missing,waiting,shot,added_at,director,genres,subtitle)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (item.get("code"), item.get("title"), item.get("title_zh"),
                 _json(item.get("actors")), item.get("date"), item.get("maker"),
                 item.get("cover"), item.get("url"), item.get("score"), item.get("votes"),
                 _json(item.get("links")), _json(item.get("pending_links")),
                 _bool(item.get("pending")), _bool(item.get("missing")), _bool(item.get("waiting")),
                 item.get("shot"), item.get("added_at"),
                 item.get("director"), _json(item.get("genres")), item.get("subtitle"))
                for item in items])
            now = int(time.time())
            conn.executemany("INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)", [
                ("updated_at", str(data.get("updated_at") or "")),
                ("synced_at", str(now)),
                ("avatars", json.dumps(data.get("avatars") or {}, ensure_ascii=False)),
                ("genres", json.dumps(data.get("genres") or {}, ensure_ascii=False)),
                ("nyaa", json.dumps(data.get("nyaa") or {}, ensure_ascii=False)),
                ("last_error", ""),
            ])
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        elapsed = time.time() - started
        say(f"同步完成：接口 {len(items)} 条，库内 {total} 条，用时 {elapsed:.1f}s")
        return dict(added=len(items), total=total, seconds=round(elapsed, 1),
                    updated_at=str(data.get("updated_at") or ""), synced_at=now)
    finally:
        _sync_lock.release()


def record_error(message: str, data_dir=None) -> None:
    """同步失败时把原因留在 meta 里，界面下次打开还能看到。"""
    try:
        with _lock, connect(Path(data_dir or default_data_dir()) / "ltx.db") as conn:
            init_db(conn)
            conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)", ("last_error", str(message)[:300]))
            conn.commit()
    except (sqlite3.Error, OSError):
        pass


# ------------------------------------------------------------------ 查询
def normalize_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def ed2k_size(link: str) -> int:
    """ed2k://|file|名字|字节数|hash|/ -> 字节数"""
    if not link.startswith("ed2k://"):
        return 0
    parts = link.split("|")
    if len(parts) > 3:
        try:
            return int(parts[3])
        except ValueError:
            return 0
    return 0


def link_name(link: str) -> str:
    if link.startswith("ed2k://"):
        parts = link.split("|")
        if len(parts) > 2:
            return urllib.parse.unquote(parts[2])
        return ""
    if link.startswith("magnet:"):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        if query.get("dn"):
            return query["dn"][0]
    return ""


def human_size(value: int) -> str:
    if not value:
        return "-"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def describe_links(links, pending_links=None):
    """把链接数组转成界面直接可用的结构（类型、文件名、大小、原文）。"""
    rows = []
    for link in links or []:
        if not isinstance(link, str):
            continue
        kind = "ed2k" if link.startswith("ed2k://") else "magnet" if link.startswith("magnet:") else "other"
        rows.append(dict(kind=kind, name=link_name(link), size=ed2k_size(link),
                         sizeText=human_size(ed2k_size(link)), url=link))
    for link in pending_links or []:
        if isinstance(link, str) and link:
            rows.append(dict(kind="pending", name="待确认", size=0, sizeText="-", url=link))
    return rows


def _meta(conn: sqlite3.Connection) -> dict:
    return {row["k"]: row["v"] for row in conn.execute("SELECT k,v FROM meta")}


def status(data_dir=None) -> dict:
    """界面顶部的数据源状态：条数、上次同步、下次计划、资源站自身更新时间。"""
    path = db_path(data_dir)
    empty = dict(total=0, withLinks=0, pending=0, makers=0, genres=0, syncedAt=None,
                 nextSync=None, updatedAt=None, lastError="", nyaa=None, ready=False,
                 dateFrom="", dateTo="")
    if not path.exists():
        return empty
    try:
        with connect(path) as conn:
            init_db(conn)
            meta = _meta(conn)
            row = conn.execute("""SELECT COUNT(*) total,
                    SUM(CASE WHEN links != '[]' THEN 1 ELSE 0 END) withLinks,
                    SUM(CASE WHEN pending = 1 THEN 1 ELSE 0 END) pending,
                    COUNT(DISTINCT maker) makers,
                    MIN(NULLIF(date,'')) dateFrom, MAX(NULLIF(date,'')) dateTo
                FROM items""").fetchone()
            genre_map = json.loads(meta.get("genres") or "{}")
            nyaa = meta.get("nyaa") or ""
            return dict(
                total=row["total"] or 0,
                withLinks=row["withLinks"] or 0,
                pending=row["pending"] or 0,
                makers=row["makers"] or 0,
                genres=len(genre_map),
                dateFrom=row["dateFrom"] or "",
                dateTo=row["dateTo"] or "",
                syncedAt=int(meta["synced_at"]) if str(meta.get("synced_at") or "").isdigit() else None,
                nextSync=int(meta["next_sync"]) if str(meta.get("next_sync") or "").isdigit() else None,
                updatedAt=int(meta["updated_at"]) if str(meta.get("updated_at") or "").isdigit() else None,
                lastError=meta.get("last_error") or "",
                nyaa=json.loads(nyaa) if nyaa else None,
                ready=True,
            )
    except (sqlite3.Error, OSError, ValueError):
        return empty


def set_next_sync(timestamp, data_dir=None) -> None:
    try:
        with _lock, connect(Path(data_dir or default_data_dir()) / "ltx.db") as conn:
            init_db(conn)
            conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)", ("next_sync", str(int(timestamp))))
            conn.commit()
    except (sqlite3.Error, OSError):
        pass


def genres(data_dir=None) -> dict:
    path = db_path(data_dir)
    if not path.exists():
        return {}
    try:
        with connect(path) as conn:
            return json.loads(_meta(conn).get("genres") or "{}")
    except (sqlite3.Error, OSError):
        return {}


def makers(data_dir=None, limit: int = 400) -> list:
    path = db_path(data_dir)
    if not path.exists():
        return []
    try:
        with connect(path) as conn:
            return [dict(name=row["maker"], count=row["c"])
                    for row in conn.execute("""SELECT maker, COUNT(*) c FROM items
                        WHERE maker != '' GROUP BY maker ORDER BY c DESC LIMIT ?""", (limit,))]
    except (sqlite3.Error, OSError):
        return []


SORTS = {
    "date": "COALESCE(NULLIF(date,''),'0000-00-00') DESC, added_at DESC",
    "score": "COALESCE(score,0) DESC, date DESC",
    "added": "COALESCE(added_at,0) DESC",
    "votes": "COALESCE(votes,0) DESC",
}


def _like(value: str) -> str:
    """转义 LIKE 的通配符，避免用户输入 % 时全表命中。"""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(keyword: str = "", maker: str = "", genre: str = "", sort: str = "date",
           page: int = 1, limit: int = 48, data_dir=None) -> dict:
    """按关键词/厂商/分类过滤并分页。关键词同时匹配番号、标题、演员、厂商、导演。"""
    path = db_path(data_dir)
    result = dict(items=[], total=0, page=1, pages=0, limit=limit)
    if not path.exists():
        return result
    keyword = (keyword or "").strip()
    maker = (maker or "").strip()
    genre = (genre or "").strip()
    order = SORTS.get(sort, SORTS["date"])
    where, params = [], []
    if keyword:
        needle = _like(keyword)
        where.append("""(code LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' OR title_zh LIKE ? ESCAPE '\\'
                         OR actors LIKE ? ESCAPE '\\' OR maker LIKE ? ESCAPE '\\' OR director LIKE ? ESCAPE '\\')""")
        params.extend([needle] * 6)
    if maker:
        where.append("maker = ?")
        params.append(maker)
    if genre:
        # 必须连引号一起匹配：`c5=14` 用裸 LIKE 会顺带命中 `c5=141`。
        where.append("genres LIKE ? ESCAPE '\\'")
        params.append('%"' + genre.replace("\\", "\\\\").replace('"', '\\"')
                      .replace("%", "\\%").replace("_", "\\_") + '"%')
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(int(limit or 48), 200))
    try:
        with connect(path) as conn:
            init_db(conn)
            total = conn.execute(f"SELECT COUNT(*) FROM items{clause}", params).fetchone()[0]
            pages = max(1, (total + limit - 1) // limit)
            page = max(1, min(int(page or 1), pages))
            rows = conn.execute(f"""SELECT code,title,title_zh,actors,date,maker,cover,url,score,
                    votes,links,pending,missing,waiting,shot,added_at,director,genres,subtitle
                FROM items{clause} ORDER BY {order} LIMIT ? OFFSET ?""",
                [*params, limit, (page - 1) * limit]).fetchall()
            genre_map = json.loads(_meta(conn).get("genres") or "{}")
            result.update(items=[_row_view(row, genre_map) for row in rows],
                          total=total, page=page, pages=pages)
    except (sqlite3.Error, OSError):
        return result
    return result


def _row_view(row: sqlite3.Row, genre_map: dict) -> dict:
    keys = json.loads(row["genres"] or "[]") if row["genres"] else []
    labels = []
    for key in keys:
        names = genre_map.get(key)
        if isinstance(names, list) and names:
            labels.append(str(names[0]))
    return dict(code=row["code"], title=row["title"] or "", titleZh=row["title_zh"] or "",
                actors=json.loads(row["actors"] or "[]"), date=row["date"] or "",
                maker=row["maker"] or "", cover=row["cover"] or "", url=row["url"] or "",
                score=row["score"] or 0, votes=row["votes"] or 0,
                linkCount=len(json.loads(row["links"] or "[]")),
                pending=bool(row["pending"]), missing=bool(row["missing"]),
                waiting=bool(row["waiting"]), shot=row["shot"] or "",
                director=row["director"] or "", genres=labels,
                subtitle=bool(row["subtitle"]), addedAt=row["added_at"])


def detail(code: str, data_dir=None) -> dict:
    path = db_path(data_dir)
    if not path.exists():
        raise KeyError("资源库还没有同步，请先执行一次同步")
    want = normalize_code(code)
    try:
        with connect(path) as conn:
            init_db(conn)
            row = conn.execute("""SELECT * FROM items
                WHERE replace(replace(upper(code),'-',''),'_','') = ? LIMIT 1""", (want,)).fetchone()
            if row is None:
                raise KeyError(f"资源库里没有 {code}")
            genre_map = json.loads(_meta(conn).get("genres") or "{}")
            view = _row_view(row, genre_map)
            view.update(links=describe_links(json.loads(row["links"] or "[]"),
                                             json.loads(row["pending_links"] or "[]")),
                        subtitleUrl=row["subtitle"] or "",
                        titleRaw=row["title"] or "")
            return view
    except sqlite3.Error as exc:
        raise KeyError(f"资源库读取失败：{exc}") from exc


# ------------------------------------------------------------------ 封面
def _cover_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in COVER_HOSTS)


def fetch_cover(url: str, timeout: int = 20):
    """取回封面字节；只允许站点 CDN，结果按 URL 缓存，减少重复请求。"""
    if not url or not _cover_allowed(url):
        return None
    now = time.time()
    hit = _image_cache.get(url)
    if hit and now - hit[0] < IMAGE_TTL:
        return hit[1]
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://javdb.com/"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not data or data[:3] != b"\xff\xd8\xff" and data[:4] != b"\x89PNG":
        return None
    if len(_image_cache) >= IMAGE_CACHE_MAX:
        for key in sorted(_image_cache, key=lambda k: _image_cache[k][0])[:50]:
            _image_cache.pop(key, None)
    _image_cache[url] = (now, data)
    return data


# ------------------------------------------------------------------ 定时同步
UNIT_SECONDS = {"minute": 60, "hour": 3600, "day": 86400}


def interval_seconds(settings) -> int:
    """把设置里的「周期数值 + 单位」换算成秒，非法值退回默认的 6 小时。"""
    settings = settings or {}
    try:
        value = int(settings.get("ltxIntervalValue") or 6)
    except (TypeError, ValueError):
        value = 6
    unit = settings.get("ltxIntervalUnit")
    if unit not in UNIT_SECONDS:
        unit = "hour"
    return max(60, min(value, 9999) * UNIT_SECONDS[unit])


class Scheduler:
    """按设置里的周期在后台同步资源库；设置一改立刻重算下次时间。

    与短剧订阅调度一样用守护线程 + 事件等待，服务退出时 set() 一下就结束，
    不会拖住进程。
    """

    def __init__(self, settings_getter, log=None, data_dir=None):
        self.settings = settings_getter
        self.log = log or (lambda _msg, _level="info": None)
        self.data_dir = data_dir
        self.stop = threading.Event()
        self._thread = None
        self._next = 0.0

    # ---------------- 生命周期
    def start(self):
        self.stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ltx-scheduler")
        self._thread.start()

    def close(self):
        self.stop.set()

    def next_run(self):
        return int(self._next) if self._next else None

    def reschedule(self):
        """设置保存后调用：从此刻起按新周期重算，并清掉旧的 next_sync。"""
        settings = self.settings() or {}
        self._next = (time.time() + interval_seconds(settings)) if settings.get("ltxSyncEnabled") else 0.0
        set_next_sync(int(self._next), self.data_dir)

    # ---------------- 循环
    def _loop(self):
        # 启动时先把「下次同步」对齐到设置：上次同步还没到期就沿用库里的记录。
        self._next = self._initial_deadline()
        set_next_sync(int(self._next), self.data_dir)
        while not self.stop.wait(20):
            settings = self.settings() or {}
            if not settings.get("ltxSyncEnabled"):
                if self._next:
                    self._next = 0.0
                    set_next_sync(0, self.data_dir)
                continue
            if not self._next:
                self._next = time.time() + interval_seconds(settings)
                set_next_sync(int(self._next), self.data_dir)
            if time.time() < self._next:
                continue
            self.run_once(reason="定时")

    def _initial_deadline(self) -> float:
        settings = self.settings() or {}
        if not settings.get("ltxSyncEnabled"):
            return 0.0
        period = interval_seconds(settings)
        snapshot = status(self.data_dir)
        last = snapshot.get("syncedAt") or 0
        if not last:
            return time.time()  # 从没同步过，立即补一次
        return max(time.time(), last + period)

    def run_once(self, reason="手动") -> dict:
        try:
            report = sync(data_dir=self.data_dir, progress=lambda msg: self.log(msg))
            set_next_sync(int(time.time() + interval_seconds(self.settings())), self.data_dir)
            self._next = time.time() + interval_seconds(self.settings())
            self.log(f"资源库{reason}同步完成：{report['total']} 条（接口 {report['added']} 条，"
                     f"用时 {report['seconds']}s）")
            return report
        except Exception as exc:  # noqa: BLE001 - 同步失败不能让调度线程退出
            record_error(str(exc), self.data_dir)
            self.log(f"资源库{reason}同步失败：{exc}", "error")
            # 失败后仍然推进周期，避免网络恢复前每 20 秒重试一次。
            self._next = time.time() + interval_seconds(self.settings())
            set_next_sync(int(self._next), self.data_dir)
            raise
