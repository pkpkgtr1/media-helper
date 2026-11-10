"""Jasna 资源库（ltx）：入库结构、搜索过滤与同步周期换算。

这些用例全部离线：数据库直接在临时目录里造，不碰 ltx.libray.workers.dev。
"""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from media_helper import ltx

SAMPLE = {
    "updated_at": "1794297843896",
    "avatars": {"三上悠亜": "https://c0.jdbstatic.com/avatars/x.jpg"},
    "genres": {"c5=18": ["中出", "Creampie", "中出し"], "c1=52": ["巨乳", "Big Tits", "巨乳"]},
    "nyaa": {"ok": True, "checked_at": 1794297800},
    "items": [
        {"code": "SSIS-834", "title": "完全引退", "title_zh": "完全引退 中文",
         "actors": ["三上悠亜"], "date": "2023-08-16", "maker": "S1",
         "cover": "https://c0.jdbstatic.com/covers/a.jpg", "url": "https://javdb.com/v/abc",
         "score": 4.5, "votes": 120,
         "links": ["ed2k://|file|SSIS-834.mp4|8891234567|ABCDEF|/"],
         "pending_links": [], "pending": False, "missing": False, "waiting": False,
         "shot": "", "added_at": 1794200000, "director": "監督A",
         "genres": ["c5=18", "c1=52"], "subtitle": "https://x.invalid/a.srt"},
        {"code": "ABC-001", "title": "Another", "title_zh": "", "actors": ["演员乙"],
         "date": "2020-01-01", "maker": "Moodyz", "cover": "", "url": "",
         "score": 3.0, "votes": 5, "links": [], "pending_links": ["https://x.invalid/p"],
         "pending": True, "missing": False, "waiting": False, "shot": "",
         "added_at": 1700000000, "director": "", "genres": ["c1=52"], "subtitle": ""},
    ],
}


def write_db(root, data=SAMPLE):
    """按 ltx.sync 的写法把样例数据落库，避免测试依赖网络。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "items.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    conn = sqlite3.connect(str(root / "ltx.db"))
    conn.row_factory = sqlite3.Row
    ltx.init_db(conn)
    conn.executemany("""INSERT OR REPLACE INTO items
        (code,title,title_zh,actors,date,maker,cover,url,score,votes,links,
         pending_links,pending,missing,waiting,shot,added_at,director,genres,subtitle)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
        (item["code"], item["title"], item["title_zh"], json.dumps(item["actors"], ensure_ascii=False),
         item["date"], item["maker"], item["cover"], item["url"], item["score"], item["votes"],
         json.dumps(item["links"]), json.dumps(item["pending_links"]),
         int(item["pending"]), int(item["missing"]), int(item["waiting"]), item["shot"],
         item["added_at"], item["director"], json.dumps(item["genres"]), item["subtitle"])
        for item in data["items"]])
    conn.executemany("INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)", [
        ("updated_at", data["updated_at"]), ("synced_at", "1794300000"),
        ("avatars", json.dumps(data["avatars"], ensure_ascii=False)),
        ("genres", json.dumps(data["genres"], ensure_ascii=False)),
        ("nyaa", json.dumps(data["nyaa"], ensure_ascii=False))])
    conn.commit()
    conn.close()


class IntervalTests(unittest.TestCase):
    def test_defaults_to_six_hours(self):
        self.assertEqual(21600, ltx.interval_seconds({}))

    def test_each_unit(self):
        self.assertEqual(600, ltx.interval_seconds({"ltxIntervalValue": 10, "ltxIntervalUnit": "minute"}))
        self.assertEqual(21600, ltx.interval_seconds({"ltxIntervalValue": 6, "ltxIntervalUnit": "hour"}))
        self.assertEqual(172800, ltx.interval_seconds({"ltxIntervalValue": 2, "ltxIntervalUnit": "day"}))

    def test_bad_values_fall_back(self):
        self.assertEqual(21600, ltx.interval_seconds({"ltxIntervalValue": "x", "ltxIntervalUnit": "week"}))
        self.assertEqual(21600, ltx.interval_seconds({"ltxIntervalValue": 0, "ltxIntervalUnit": "hour"}))


class LinkTests(unittest.TestCase):
    def test_ed2k_size_and_name(self):
        link = "ed2k://|file|SSIS-834%20abc.mp4|8891234567|ABCDEF|/"
        self.assertEqual(8891234567, ltx.ed2k_size(link))
        self.assertEqual("SSIS-834 abc.mp4", ltx.link_name(link))

    def test_magnet_name(self):
        self.assertEqual("abc", ltx.link_name("magnet:?xt=urn:btih:xx&dn=abc"))

    def test_describe_links_marks_pending(self):
        rows = ltx.describe_links(
            ["ed2k://|file|a.mp4|1024|H|/"], ["https://x.invalid/pending"])
        self.assertEqual(["ed2k", "pending"], [row["kind"] for row in rows])
        self.assertEqual("1.00 KB", rows[0]["sizeText"])


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_counts(self):
        status = ltx.status(self.tmp.name)
        self.assertTrue(status["ready"])
        self.assertEqual(2, status["total"])
        self.assertEqual(1, status["withLinks"])
        self.assertEqual(1, status["pending"])
        self.assertEqual(2, status["genres"])
        self.assertEqual("2023-08-16", status["dateTo"])

    def test_status_before_sync(self):
        with tempfile.TemporaryDirectory() as empty:
            status = ltx.status(empty)
            self.assertFalse(status["ready"])
            self.assertEqual(0, status["total"])

    def test_search_by_code_title_actor_maker_director(self):
        for keyword in ("SSIS", "引退", "三上", "S1", "監督"):
            with self.subTest(keyword=keyword):
                self.assertEqual(1, ltx.search(keyword, data_dir=self.tmp.name)["total"])

    def test_search_is_case_insensitive(self):
        self.assertEqual(1, ltx.search("ssis-834", data_dir=self.tmp.name)["total"])

    def test_genre_filter_is_not_a_prefix_match(self):
        """`c5=14` 不能顺带命中 `c5=141`：分类必须以完整 JSON 字符串比对。"""
        root = Path(self.tmp.name)
        data = json.loads(json.dumps(SAMPLE))
        data["items"][0]["genres"] = ["c5=141"]
        data["items"][1]["genres"] = ["c5=14"]
        data["genres"]["c5=141"] = ["別分類", "Other", "別"]
        write_db(root, data)
        self.assertEqual(["ABC-001"],
                         [row["code"] for row in ltx.search(genre="c5=14", data_dir=root)["items"]])
        self.assertEqual(["SSIS-834"],
                         [row["code"] for row in ltx.search(genre="c5=141", data_dir=root)["items"]])

    def test_genre_filter_ignores_unknown_key(self):
        self.assertEqual(0, ltx.search(genre="c9=999", data_dir=self.tmp.name)["total"])

    def test_wildcards_are_escaped(self):
        # 用户输入 % 时不能退化成全表命中
        self.assertEqual(0, ltx.search("%", data_dir=self.tmp.name)["total"])

    def test_filters(self):
        self.assertEqual(1, ltx.search(maker="S1", data_dir=self.tmp.name)["total"])
        self.assertEqual(2, ltx.search(genre="c1=52", data_dir=self.tmp.name)["total"])
        self.assertEqual(0, ltx.search(maker="S1", genre="c5=18",
                                       keyword="abc", data_dir=self.tmp.name)["total"])

    def test_sort_and_paging(self):
        by_date = ltx.search(sort="date", data_dir=self.tmp.name)["items"]
        self.assertEqual(["SSIS-834", "ABC-001"], [row["code"] for row in by_date])
        page = ltx.search(limit=1, page=2, data_dir=self.tmp.name)
        self.assertEqual(2, page["pages"])
        self.assertEqual(1, len(page["items"]))

    def test_genre_labels_are_localised(self):
        item = ltx.search("SSIS", data_dir=self.tmp.name)["items"][0]
        self.assertEqual(["中出", "巨乳"], item["genres"])

    def test_detail_normalises_code(self):
        detail = ltx.detail("ssis 834", self.tmp.name)
        self.assertEqual("SSIS-834", detail["code"])
        self.assertEqual(1, len(detail["links"]))
        self.assertEqual("https://x.invalid/a.srt", detail["subtitleUrl"])

    def test_detail_missing_code(self):
        with self.assertRaises(KeyError):
            ltx.detail("NOPE-999", self.tmp.name)

    def test_makers_and_genres(self):
        self.assertEqual({"S1", "Moodyz"}, {row["name"] for row in ltx.makers(self.tmp.name)})
        self.assertEqual(2, len(ltx.genres(self.tmp.name)))


class CoverGuardTests(unittest.TestCase):
    def test_only_site_cdn_allowed(self):
        self.assertTrue(ltx._cover_allowed("https://c0.jdbstatic.com/covers/a.jpg"))
        self.assertTrue(ltx._cover_allowed("https://javdb.com/x.jpg"))
        self.assertFalse(ltx._cover_allowed("http://127.0.0.1/etc/passwd"))
        self.assertFalse(ltx._cover_allowed("https://evil.example.com/jdbstatic.com"))
        self.assertFalse(ltx._cover_allowed("file:///etc/passwd"))
        self.assertFalse(ltx._cover_allowed(""))

    def test_dmm_cover_host_allowed(self):
        """库里有 5 条历史条目封面在 pics.dmm.co.jp，白名单要放行它。"""
        self.assertTrue(ltx._cover_allowed("https://pics.dmm.co.jp/digital/video/abc/abcpl.jpg"))
        # 但只放行该主机本身，换前缀的伪造仍要挡住。
        self.assertFalse(ltx._cover_allowed("https://evil.example.com/pics.dmm.co.jp/a.jpg"))
        self.assertFalse(ltx._cover_allowed("https://notpics.dmm.co.jp.evil.com/a.jpg"))

    def test_disallowed_url_never_fetches(self):
        self.assertIsNone(ltx.fetch_cover("http://127.0.0.1:8766/api/state"))


class InitDbTests(unittest.TestCase):
    def test_old_schema_gets_new_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ltx.db"
            old = sqlite3.connect(str(path))
            old.execute("""CREATE TABLE items (code TEXT PRIMARY KEY, title TEXT, title_zh TEXT,
                actors TEXT, date TEXT, maker TEXT, cover TEXT, url TEXT, score REAL, votes INTEGER,
                links TEXT, pending_links TEXT, pending INTEGER, missing INTEGER, waiting INTEGER,
                shot TEXT, added_at INTEGER)""")
            old.commit()
            old.close()
            conn = ltx.connect(path)
            ltx.init_db(conn)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
            conn.close()
            self.assertTrue({"director", "genres", "subtitle"} <= columns)


if __name__ == "__main__":
    unittest.main()


class SyncTests(unittest.TestCase):
    """sync() 的落盘路径：原子写 JSON + upsert，全程不打网络。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = ltx.fetch_items
        ltx.fetch_items = lambda timeout=120: SAMPLE  # noqa: ARG005

    def tearDown(self):
        ltx.fetch_items = self.original
        self.tmp.cleanup()

    def test_sync_writes_db_and_raw_json(self):
        report = ltx.sync(data_dir=self.tmp.name)
        self.assertEqual(2, report["total"])
        self.assertTrue((Path(self.tmp.name) / "ltx.db").exists())
        raw = json.loads((Path(self.tmp.name) / "items.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(raw["items"]))
        status = ltx.status(self.tmp.name)
        self.assertTrue(status["ready"])
        self.assertIsNotNone(status["syncedAt"])

    def test_second_sync_is_idempotent(self):
        ltx.sync(data_dir=self.tmp.name)
        report = ltx.sync(data_dir=self.tmp.name)
        self.assertEqual(2, report["total"])  # 主键覆盖，不产生重复行

    def test_sync_failure_is_reported(self):
        def boom(timeout=120):  # noqa: ARG001
            raise RuntimeError("资源站返回 HTTP 502")

        ltx.fetch_items = boom
        with self.assertRaises(RuntimeError):
            ltx.sync(data_dir=self.tmp.name)
        self.assertFalse((Path(self.tmp.name) / "ltx.db").exists())

    def test_older_meta_key_survives_after_error(self):
        ltx.sync(data_dir=self.tmp.name)
        ltx.record_error("网络不通", self.tmp.name)
        self.assertEqual("网络不通", ltx.status(self.tmp.name)["lastError"])


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = ltx.fetch_items
        ltx.fetch_items = lambda timeout=120: SAMPLE  # noqa: ARG005

    def tearDown(self):
        ltx.fetch_items = self.original
        self.tmp.cleanup()

    def test_run_once_syncs_and_advances_deadline(self):
        settings = {"ltxSyncEnabled": True, "ltxIntervalValue": 6, "ltxIntervalUnit": "hour"}
        scheduler = ltx.Scheduler(lambda: settings, data_dir=self.tmp.name)
        before = time.time()
        report = scheduler.run_once()
        self.assertEqual(2, report["total"])
        self.assertGreaterEqual(scheduler.next_run(), int(before + 21600))
        self.assertEqual(scheduler.next_run(), ltx.status(self.tmp.name)["nextSync"])

    def test_disabled_scheduler_has_no_deadline(self):
        scheduler = ltx.Scheduler(lambda: {"ltxSyncEnabled": False}, data_dir=self.tmp.name)
        scheduler.reschedule()
        self.assertIsNone(scheduler.next_run())

    def test_failure_does_not_kill_the_loop(self):
        def boom(timeout=120):  # noqa: ARG001
            raise RuntimeError("资源站响应超时")

        ltx.fetch_items = boom
        settings = {"ltxSyncEnabled": True, "ltxIntervalValue": 1, "ltxIntervalUnit": "hour"}
        scheduler = ltx.Scheduler(lambda: settings, data_dir=self.tmp.name)
        with self.assertRaises(RuntimeError):
            scheduler.run_once()
        # 失败也要排下一次，否则二十秒后就重试一次，把对方打挂
        self.assertIsNotNone(scheduler.next_run())


class ServerRouteTests(unittest.TestCase):
    """Application 层的 /api/ltx/* 路由；直接调 get()，不起 HTTP 服务。"""

    def setUp(self):
        from media_helper.config import Storage
        from media_helper.server import Application

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.storage = Storage(self.root / "state")
        self.storage.settings["outputRoot"] = str(self.root / "media")
        self.app = Application(self.storage, dist=self.root / "ui")
        self.app.ltx_data_dir = self.root / "state" / "ltxdb"
        self.app.ltx.data_dir = self.app.ltx_data_dir
        write_db(self.app.ltx_data_dir)

    def tearDown(self):
        self.app.tasks.close()
        self.tmp.cleanup()

    def get(self, route, **query):
        return self.app.get(route, {key: [value] for key, value in query.items()})

    def test_status_reports_interval_and_enabled(self):
        data = self.get("/api/ltx/status")
        self.assertTrue(data["ready"])
        self.assertEqual(2, data["total"])
        self.assertTrue(data["enabled"])
        self.assertEqual(21600, data["intervalSeconds"])

    def test_items_endpoint_filters(self):
        data = self.get("/api/ltx/items", keyword="SSIS")
        self.assertEqual(1, data["total"])
        self.assertEqual("SSIS-834", data["items"][0]["code"])

    def test_items_endpoint_tolerates_bad_numbers(self):
        data = self.get("/api/ltx/items", page="abc", limit="xyz")
        self.assertEqual(1, data["page"])
        self.assertEqual(2, data["total"])

    def test_detail_endpoint(self):
        data = self.get("/api/ltx/detail", code="ssis-834")
        self.assertEqual("SSIS-834", data["code"])
        self.assertEqual(1, len(data["links"]))

    def test_detail_endpoint_requires_code(self):
        with self.assertRaises(ValueError):
            self.get("/api/ltx/detail")

    def test_filters_endpoint(self):
        data = self.get("/api/ltx/filters")
        self.assertIn("S1", [row["name"] for row in data["makers"]])
        self.assertEqual(2, len(data["genres"]))

    def test_unknown_ltx_route_is_404(self):
        with self.assertRaises(FileNotFoundError):
            self.get("/api/ltx/nope")

    def test_settings_validation_accepts_ltx_keys(self):
        from media_helper.config import validate_settings

        result = validate_settings(dict(self.storage.settings, ltxIntervalValue=12,
                                        ltxIntervalUnit="day", ltxSyncEnabled=False))
        self.assertEqual(12, result["ltxIntervalValue"])
        self.assertEqual("day", result["ltxIntervalUnit"])
        self.assertFalse(result["ltxSyncEnabled"])

    def test_settings_validation_rejects_bad_interval(self):
        from media_helper.config import validate_settings

        for patch in ({"ltxIntervalValue": 0}, {"ltxIntervalValue": "6"},
                      {"ltxIntervalUnit": "week"}, {"ltxSyncEnabled": "yes"}):
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    validate_settings(dict(self.storage.settings, **patch))
