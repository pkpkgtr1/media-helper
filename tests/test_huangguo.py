"""Offline checks for the huangguo module: naming, store, records, parsing, routes."""
import json
import re
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import huangguo_client as hc
import huangguo_manager as hm

SUGGEST_HTML = """
<section class="hg-search-suggest__section">
 <div class="hg-search-suggest__title">猜你喜欢</div>
 <div class="hg-search-suggest__guess"><div class="hg-drama-card" data-track-item-name="热门推荐剧">
  <div class="hg-drama-card__cover"><a class="hg-drama-card__cover-link" href="/video/99999/">
   <img data-src="https://pic.drleao.cn/hot.jpg?auth_key=h"></a></div>
  <div class="hg-drama-card__body"><div class="hg-drama-card__title"><a href="/video/99999/">热门推荐剧</a></div>
  </div></div></div></section>
"""

SEARCH_HTML = """
<div class="hg-card-grid">
 <div class="hg-drama-card" data-track-item-name="测试剧">
  <div class="hg-drama-card__cover"><a class="hg-drama-card__cover-link" href="/video/123/">
   <img data-src="https://pic.drleao.cn/a.jpg?auth_key=1" alt="测试剧"></a>
   <span class="hg-drama-card__score">8.6分</span>
   <span class="hg-drama-card__episode" data-ep-at="1" data-ep-base="更新至15集"></span></div>
  <div class="hg-drama-card__body">
   <div class="hg-drama-card__title"><a href="/video/123/">测试剧<span class="sr-only">全集在线观看</span></a></div>
   <p class="hg-drama-card__desc">一段简介 </p>
   <div class="hg-drama-card__tags"><a class="hg-tag" href="/tag/a/">都市<span class="sr-only">x</span></a></div>
  </div>
 </div>
</div>
"""

DETAIL_HTML = """
<meta property="og:title" content="测试剧 - 黄果短剧">
<meta property="og:description" content="剧情简介">
<div class="hg-detail" data-src="https://pic.drleao.cn/poster.jpg?auth_key=2"></div>
<span>全7集</span>
<a href="/video/123/ep-2/">2</a><a href="/video/123/ep-7/">7</a><a href="/video/123/ep-7/">7</a>
<a class="hg-tag" href="/tag/a/">都市<span class="sr-only">x</span></a>
"""

EPISODE_HTML = '''<source src="https://cdn.hzjvlo.cn/x.m3u8?auth_key=99&amp;v=3">'''

PROTOCOL_JS = '''window.CryptoImageProtocol = Object.freeze({"decryptEnabled": true, "decryptKey": "f5d965df75336270", "decryptIV": "97b60394abc2fbe1"})'''


class FakeResponse:
    def __init__(self, text="", content=b"", status_code=200):
        self.text, self.content, self.status_code = text, content or text.encode(), status_code


class FakeClient(hc.Client):
    """Serve canned HTML; record requested URLs."""

    def __init__(self, pages=None, **kwargs):
        super().__init__(**kwargs)
        self.pages = pages or {}
        self.requested = []

    def _get(self, url, referer=None, retries=3, wait=2.0, allow_cdn=False):
        self.requested.append(url)
        hc._safe(url, allow_cdn=allow_cdn)
        for needle, payload in self.pages.items():
            if needle in url:
                return payload
        raise hc.HuangguoError(f"no fixture for {url}")


class NamingTests(unittest.TestCase):
    def test_titles_stems_and_seasons(self):
        self.assertEqual(hm.safe_title('a/b\\\\c:d*e"fg<h>i|j'), "a b c d e fg h i j")
        self.assertEqual(hm.episode_stem("我的剧", 1, 2), "我的剧 - S01E02")
        self.assertEqual(hm.season_dir_label(1), "Season 01")

    def test_year_only_when_valid_and_suffix_for_conflicts(self):
        self.assertEqual(hm.video_dir_name({"title": "剧A", "premiered": "2026"}), "剧A (2026)")
        self.assertEqual(hm.video_dir_name({"title": "剧A", "premiered": ""}), "剧A")
        self.assertEqual(hm.video_dir_name({"title": "剧A", "premiered": "未知"}), "剧A")
        self.assertEqual(hm.video_dir_name({"title": "剧A", "premiered": "2026"}, suffix="12"), "剧A (2026) [12]")


class SearchScopeTests(unittest.TestCase):
    """结果区之外的推荐位不得混入搜索返回值（海贼王 1→5 回归）。"""

    def test_guess_you_like_excluded(self):
        page = SUGGEST_HTML + '<div class="hg-search-results"><div class="hg-card-grid">' + SEARCH_HTML + "</div></div>"
        client = FakeClient(pages={"search": FakeResponse(page)})
        rows = client.search("海贼王")
        self.assertEqual([r["id"] for r in rows], ["123"])
        self.assertNotIn("热门推荐剧", "".join(r["title"] for r in rows))

    def test_no_results_container_falls_back_to_full_page(self):
        # 结构变化时退回旧行为而不是报错
        client = FakeClient(pages={"search": FakeResponse(SEARCH_HTML)})
        self.assertEqual(len(client.search("x")), 1)

    def test_empty_results_section(self):
        page = SUGGEST_HTML + '<div class="hg-search-results"><p>没有找到相关视频</p></div>'
        client = FakeClient(pages={"search": FakeResponse(page)})
        self.assertEqual(client.search("zzz"), [])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = hm.SubscriptionStore(self.root)
        self.defaults = {"hgSaveRoot": str(self.root / "media"), "hgIntervalValue": 6, "hgIntervalUnit": "hour"}
        self.info = {"id": "123", "title": "测试剧", "url": "u", "cover": "", "description": "",
                     "tags": [], "premiered": "", "actors": "", "total": 3, "episodes": [1, 2, 3]}

    def tearDown(self):
        self.temp.cleanup()

    def test_add_rejects_duplicates_and_missing_path(self):
        self.store.add(self.info, self.defaults, scope="new")
        with self.assertRaises(ValueError):
            self.store.add(self.info, self.defaults)
        with self.assertRaises(ValueError):
            self.store.add({**self.info, "id": "9"}, self.defaults, saveRoot="   ")

    def test_scope_new_records_baseline(self):
        sub = self.store.add(self.info, self.defaults, scope="new")
        self.assertEqual(sub["baseline"], [1, 2, 3])

    def test_interval_clamp_and_reload(self):
        sub = self.store.add(self.info, self.defaults, intervalValue=99999, intervalUnit="week")
        self.assertEqual(sub["intervalValue"], 9999)
        self.assertEqual(sub["intervalUnit"], "hour")
        reloaded = hm.SubscriptionStore(self.root)
        self.assertEqual(set(reloaded.items), set(self.store.items))

    def test_update_reschedules_and_pause_clears(self):
        sub = self.store.add(self.info, self.defaults)
        updated = self.store.update(sub["id"], {"intervalValue": 12})
        self.assertEqual(updated["intervalValue"], 12)
        self.assertGreater(updated["nextCheck"], 0)
        paused = self.store.update(sub["id"], {"autoCheck": False})
        self.assertEqual(paused["nextCheck"], 0)
        with self.assertRaises(KeyError):
            self.store.update("missing", {})

    def test_remove(self):
        sub = self.store.add(self.info, self.defaults)
        self.store.remove(sub["id"])
        self.assertEqual(self.store.items, {})
        with self.assertRaises(KeyError):
            self.store.remove(sub["id"])


class ScopeMathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)
        self.defaults = {"hgSaveRoot": str(self.root / "m")}
        self.info = {"id": "5", "title": "T", "url": "u", "cover": "", "description": "",
                     "tags": [], "premiered": "", "actors": "", "total": 5, "episodes": [1, 2, 3]}

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_scopes_pick_wanted_episodes(self):
        new = self.manager.store.add(self.info, self.defaults, scope="new")
        self.manager.store.update(new["id"], {"knownEpisodes": [1, 2, 3, 4]})
        self.assertEqual(self.manager.wanted_episodes(self.manager.store.items[new["id"]]), [4])
        allsub = self.manager.store.add({**self.info, "id": "6"}, self.defaults, scope="all")
        self.assertEqual(self.manager.wanted_episodes(self.manager.store.items[allsub["id"]]), [1, 2, 3])
        listsub = self.manager.store.add({**self.info, "id": "7"}, self.defaults, scope="list", episodeList=[9, 1])
        self.assertEqual(self.manager.wanted_episodes(self.manager.store.items[listsub["id"]]), [1, 9])

    def test_missing_respects_completed_records(self):
        sub = self.manager.store.add(self.info, self.defaults, scope="all")
        done_file = self.root / "v.mp4"
        done_file.write_bytes(b"x")
        self.manager.records.mark("5", 1, done_file, 1)
        self.assertEqual(self.manager.missing_episodes(self.manager.store.items[sub["id"]]), [2, 3])

    def test_done_record_requires_existing_file(self):
        ghost = self.root / "gone.mp4"
        ghost.write_bytes(b"x")
        self.manager.records.mark("5", 2, ghost, 1)
        ghost.unlink()
        self.assertFalse(self.manager.records.is_done("5", 2))


class PlotCleanupTests(unittest.TestCase):
    def test_strips_site_template_only(self):
        self.assertEqual(hm.clean_plot("爱的航线全3集，11月5日更新。小镇黄昏市场。免费在线观看。", "爱的航线"), "小镇黄昏市场。")
        self.assertEqual(hm.clean_plot("全12集，10月1日更新。简介正文。", "不匹配"), "简介正文。")

    def test_keeps_plain_text_intact(self):
        self.assertEqual(hm.clean_plot("爱的航线：都市甜宠之旅", "爱的航线"), "爱的航线：都市甜宠之旅")
        self.assertEqual(hm.clean_plot("没有模板前缀的普通简介文本。", "某剧"), "没有模板前缀的普通简介文本。")
        self.assertEqual(hm.clean_plot("", "x"), "")

    def test_tvshow_plot_cleaned(self):
        text = hm.tvshow_nfo({"title": "爱的航线", "id": "1", "url": "u",
                              "description": "爱的航线全3集，11月5日更新。剧情正文。免费在线观看。",
                              "tags": [], "actors": ""})
        self.assertIn("<plot>剧情正文。</plot>", text)
        self.assertNotIn("11月5日更新", text)
        self.assertNotIn("免费在线观看", text)


class CoverResolutionTests(unittest.TestCase):
    def test_prefers_og_named_image_over_first_data_src(self):
        page = ("<meta property=\"og:image\" content=\"https://expose.eisees.com/xiao/p.jpeg?auth=1\">"
                "<img data-src=\"https://pic.drleao.cn/upload/recommend.jpg?auth_key=2\">"
                "<div class=\"cover-link\"><img data-src=\"https://pic.drleao.cn/xiao/p.jpeg?auth_key=3\"></div>"
                "<video poster=\"https://expose.eisees.com/xiao/p.jpeg?auth=4\"></video>")
        client = FakeClient(pages={"video/555": FakeResponse(page)})
        detail = client.detail(555)
        self.assertIn("pic.drleao.cn/xiao/p.jpeg", detail["cover"])

    def test_episodes_come_from_total_not_max_link(self):
        page = ("<meta property=\"og:title\" content=\"小剧 - 黄果短剧\"><span>全3集</span>"
                "<a href=\"/video/555/ep-2/\">2</a><a href=\"/video/777/ep-13/\">13</a>")
        client = FakeClient(pages={"video/555": FakeResponse(page)})
        detail = client.detail(555)
        self.assertEqual(detail["total"], 3)
        self.assertEqual(detail["episodes"], [1, 2, 3])


class BaselineHealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_oversized_baseline_shrinks_and_reveals_new(self):
        info = {"id": "10883", "title": "爱的航线", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 3, "episodes": [1, 2, 3]}
        sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")}, scope="new")
        self.manager.store.update(sub["id"], {"baseline": list(range(1, 14)), "knownEpisodes": [1, 2, 3]})
        page = ("<meta property=\"og:title\" content=\"爱的航线 - 黄果短剧\"><span>全3集</span>"
                "<a href=\"/video/10883/ep-2/\">2</a><a href=\"/video/10883/ep-3/\">3</a>")
        with patch.object(hm.HuangguoManager, "_client", lambda self: FakeClient(pages={"video/10883": FakeResponse(page)})), \
             patch.object(hm.HuangguoManager, "enqueue_download", lambda self, sid, eps=None, reason="": None):
            task = self.manager._new_task("check", sub["id"], detail={"reason": "手动"})
            self.manager._run_check(task, self.manager.store.items[sub["id"]])
        healed = self.manager.store.items[sub["id"]]
        self.assertEqual(healed["baseline"], [1, 2, 3])

    def test_check_enqueues_download_for_missing_when_autodl(self):
        info = {"id": "9001", "title": "缺剧", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 3, "episodes": [1]}
        sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")}, scope="all")
        page = "<meta property=\"og:title\" content=\"缺剧 - 黄果短剧\"><span>全3集</span>"
        enqueued = []
        with patch.object(hm.HuangguoManager, "_client", lambda self: FakeClient(pages={"video/9001": FakeResponse(page)})), \
             patch.object(hm.HuangguoManager, "enqueue_download",
                          lambda self, sid, eps=None, reason="": enqueued.append((eps, reason))):
            task = self.manager._new_task("check", sub["id"], detail={"reason": "手动"})
            self.manager._run_check(task, self.manager.store.items[sub["id"]])
        self.assertEqual(enqueued, [([1, 2, 3], "检查补齐")])

class ManualCheckDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)
        info = {"id": "9100", "title": "漏剧", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 3, "episodes": [1, 2, 3]}
        self.sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")},
                                           scope="all", autoDownload=False)
        page = '<meta property="og:title" content="漏剧 - 黄果短剧"><span>全3集</span>'
        test = self
        self.enq = []
        self.patcher = patch.object(hm.HuangguoManager, "enqueue_download",
                                    lambda _mgr, sid, eps=None, reason="": test.enq.append((eps, reason)))
        self.patcher.start()
        self.clientp = patch.object(hm.HuangguoManager, "_client",
                                   lambda _mgr: FakeClient(pages={"video/9100": FakeResponse(page)}))
        self.clientp.start()

    def tearDown(self):
        self.patcher.stop()
        self.clientp.stop()
        self.manager.close()
        self.temp.cleanup()

    def _check(self, reason):
        task = self.manager._new_task("check", self.sub["id"], detail={"reason": reason})
        self.manager._run_check(task, self.manager.store.items[self.sub["id"]])
        return self.enq[-1] if self.enq else None

    def test_manual_check_downloads_even_when_autodl_off(self):
        self.assertEqual(self._check("手动"), ([1, 2, 3], "手动检查补齐"))

    def test_scheduled_check_respects_autodl_off(self):
        self.assertIsNone(self._check("定时"))


class ThumbFrameTests(unittest.TestCase):
    def test_uses_tenth_frame_then_defers_on_black(self):
        calls = []
        video = Path(__file__).resolve().parent / "fixture.mp4"
        out = Path(__file__).resolve().parent / "thumb.jpg"

        def fake_run(command, proxy=None, timeout=120, remote=False):
            calls.append(command)
            vf = command[command.index("-vf") + 1]
            n = int(re.search(r"eq\(n\\,(\d+)\)", vf).group(1))
            black = (n == 9)  # 第 10 帧全黑 → 应顺延第 30 帧
            out.write_bytes(b"\xff\xd8" + b"0" * 3000 if black else b"\xff\xd8" + b"1" * 3000)
            return type("R", (), {"returncode": 0})()

        client = hc.Client()
        with patch("huangguo_client.run_ffmpeg", fake_run), \
             patch("huangguo_client._not_black", lambda path: path.read_bytes()[2:3] == b"1"):
            size = client.first_frame_thumb(video, out)
        used = [c[c.index("-vf") + 1] for c in calls]
        self.assertIn("eq(n\\,9)", used[0])
        self.assertIn("eq(n\\,29)", used[1])
        self.assertGreater(size, 2000)
        out.unlink(missing_ok=True)

    def test_raises_when_no_frame_producible(self):
        def fail(command, proxy=None, timeout=120, remote=False):
            return type("R", (), {"returncode": 1})()
        video = Path(__file__).resolve().parent / "fixture.mp4"
        out = Path(__file__).resolve().parent / "thumb.jpg"
        with patch("huangguo_client.run_ffmpeg", fail):
            with self.assertRaises(hc.HuangguoError):
                hc.Client().first_frame_thumb(video, out)
        self.assertFalse(out.exists())


class CoverImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)
        info = {"id": "4242", "title": "封面剧", "url": "https://huangguoai.com/video/4242/", "cover":
                "https://pic.drleao.cn/a/stale.jpg?auth_key=1", "description": "d", "tags": [],
                "premiered": "", "actors": "", "total": 1, "episodes": [1]}
        self.media = self.root / "m"
        self.sub = self.manager.store.add(info, {"hgSaveRoot": str(self.media)})
        self.show = self.media / "封面剧"
        self.show.mkdir(parents=True)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_local_poster_wins_without_network(self):
        (self.show / "poster.jpg").write_bytes(b"\xff\xd8" + b"l" * 2000)
        with patch.object(hm.HuangguoManager, "_client",
                          lambda self: self.fail("不应访问网络")):
            data = self.manager.cover_image(self.sub["id"])
        self.assertTrue(data.startswith(b"\xff\xd8"))

    def test_stale_url_falls_back_to_detail_and_caches(self):
        fresh_page = ('<meta property="og:image" content="https://expose.eisees.com/x/new.jpeg?auth=1">'
                      '<img data-src="https://pic.drleao.cn/x/new.jpeg?auth_key=2">')
        client = FakeClient(pages={"video/4242": FakeResponse(fresh_page),
                                   "pic.drleao.cn/x/new.jpeg": FakeResponse(content=b"\xff\xd8\xff" + b"n" * 300)})
        # stale cover 直接返回 None → 触发 detail 重解析
        client.pages["pic.drleao.cn/a/stale.jpg"] = hc.HuangguoError("expired")
        def get(url, *a, **k):
            payload = next(v for needle, v in client.pages.items() if needle in url)
            if isinstance(payload, Exception):
                raise payload
            return payload
        client._get = get
        client.fetch_image = lambda url, referer=None: (b"\xff\xd8\xff" + b"n" * 300) if "new.jpeg" in url else None
        with patch.object(hm.HuangguoManager, "_client", lambda self: client):
            data = self.manager.cover_image(self.sub["id"])
        self.assertEqual(data, b"\xff\xd8\xff" + b"n" * 300)
        self.assertTrue((self.show / "poster.jpg").is_file())
        stored = self.manager.store.items[self.sub["id"]]["cover"]
        self.assertIn("new.jpeg", stored)

    def test_missing_subscription_raises(self):
        with self.assertRaises(KeyError):
            self.manager.cover_image("nope")


class EpisodeNfoMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)
        info = {"id": "10883", "title": "爱的航线", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 2, "episodes": [1, 2]}
        self.sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")}, scope="new")
        season = self.root / "m" / "爱的航线" / "Season 01"
        season.mkdir(parents=True)
        self.nfo = season / "爱的航线 - S01E01.nfo"
        legacy = hm.episode_nfo(self.sub, "第1集", 1, 1).replace(
            "</uniqueid>", "</uniqueid><plot>旧版简介</plot>")
        self.nfo.write_text(legacy, encoding="utf-8")
        (season / "爱的航线 - S01E01.mp4").write_bytes(b"x")

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_legacy_plot_detected(self):
        self.assertTrue(self.manager._legacy_episode_nfo(self.root / "m" / "爱的航线"))

    def test_check_rewrites_legacy_episode_nfo(self):
        page = '<meta property="og:title" content="爱的航线 - 黄果短剧"><span>全2集</span>'
        with patch.object(hm.HuangguoManager, "_client",
                          lambda self: FakeClient(pages={"video/10883": FakeResponse(page)})):
            task = self.manager._new_task("check", self.sub["id"], detail={"reason": "手动"})
            self.manager._run_check(task, self.manager.store.items[self.sub["id"]])
        text = self.nfo.read_text(encoding="utf-8")
        self.assertNotIn("<plot>", text)
        self.assertIn("<episode>1</episode>", text)

    def test_wrong_uniqueid_detected_as_legacy(self):
        self.nfo.write_text(hm.episode_nfo({**self.sub, "videoId": "10883"}, "第1集", 1, 1), encoding="utf-8")
        self.assertFalse(self.manager._legacy_episode_nfo(self.root / "m" / "爱的航线", "10883"))
        bad = hm.episode_nfo({"videoId": "local-uuid"}, "第1集", 1, 1)
        self.nfo.write_text(bad, encoding="utf-8")
        self.assertTrue(self.manager._legacy_episode_nfo(self.root / "m" / "爱的航线", "10883"))

    def test_clean_nfo_not_detected_as_legacy(self):
        self.nfo.write_text(hm.episode_nfo(self.sub, "第1集", 1, 1), encoding="utf-8")
        self.assertFalse(self.manager._legacy_episode_nfo(self.root / "m" / "爱的航线"))


class CheckFeedbackLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lines = []
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root,
                                          logger=lambda msg, level="info": self.lines.append(msg))
        info = {"id": "5001", "title": "已完结剧", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 2, "episodes": [1, 2]}
        self.sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")}, scope="all")
        self.page = '<meta property="og:title" content="已完结剧 - 黄果短剧"><span>全2集</span>'

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def _run(self):
        fixture = {"video/5001": FakeResponse(self.page)}
        with patch.object(hm.HuangguoManager, "_client", lambda _mgr: FakeClient(pages=fixture)):
            task = self.manager._new_task("check", self.sub["id"], detail={"reason": "定时"})
            self.manager._run_check(task, self.manager.store.items[self.sub["id"]])
        return task

    def test_task_carries_subscription_title(self):
        task = self._run()
        self.assertEqual(task["subscriptionTitle"], "已完结剧")
        self.assertIn("无新集数", task["message"])

    def test_result_feedback_logged_even_without_updates(self):
        done_file = self.root / "v.mp4"; done_file.write_bytes(b"x")
        self.manager.records.mark("5001", 1, done_file, 1)
        self.manager.records.mark("5001", 2, done_file, 1)
        self._run()
        self.assertTrue(any("检查结果：无新集数，全部已下载" in l for l in self.lines), self.lines)

    def test_pending_missing_feedback_logged(self):
        self._run()
        self.assertTrue(any("检查结果：无新集数，2 集待下载" in l for l in self.lines), self.lines)

    def test_failure_log_names_drama(self):
        boom = FakeClient(pages={})
        with patch.object(hm.HuangguoManager, "_client", lambda _mgr: boom):
            task = self.manager._new_task("check", self.sub["id"], detail={"reason": "定时"})
            self.manager._spawn(task, lambda: (_ for _ in ()).throw(RuntimeError("解析失败")))
            for _ in range(50):
                import time as _t; _t.sleep(0.05)
                if self.manager.snapshot_tasks()["tasks"][-1]["state"] == "failed":
                    break
        self.assertTrue(any("《已完结剧》检查更新失败：解析失败" in l for l in self.lines), self.lines)


class DownloadProgressTests(unittest.TestCase):
    def test_segment_progress_updates_task(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        manager = hm.HuangguoManager(lambda: {"hgConcurrent": 2, "hgRetries": 0, "hgRetryInterval": 0}, root=root)
        info = {"id": "11338", "title": "庆余年3", "url": "u", "cover": "", "description": "d",
                "tags": [], "premiered": "", "actors": "", "total": 2, "episodes": [1, 2]}
        sub = manager.store.add(info, {"hgSaveRoot": str(root / "m")}, scope="all")

        class FakeDL:
            def episode_stream(self, vid, ep, title=""):
                return "https://cdn/x.m3u8"
            def episode_page_url(self, vid, ep):
                return "https://huangguoai.com/video/11338/ep-2/"
            def download_hls(self, m3u8, referer, out, proxy=None, workers=4, segment_limit=None, progress=None):
                season = out.parent
                (season / (out.stem + ".nfo")).write_text("x", encoding="utf-8")
                out.write_bytes(b"\xff" * 5000)
                for i in (10, 30, 42):
                    progress(i, 42)
                return 5000
            def first_frame_thumb(self, v, o, proxy=None):
                o.write_bytes(b"\xff\xd8" + b"0" * 3000)
        task = manager._new_task("download", sub["id"], detail={"episodes": [2], "reason": "测试"})
        season = Path(sub["saveRoot"]) / "庆余年3" / "Season 01"
        season.mkdir(parents=True)
        manager._download_one(FakeDL(), manager.store.items[sub["id"]], season.parent, season, 2, 2, task=task)
        # 分片 100% 后进入转码阶段：99% + “合并转码中”；最终 100% 由任务循环落账
        self.assertEqual(task["progress"], 99)
        self.assertIn("合并转码", task["message"])
        self.assertEqual(task["indeterminate"], True)
        manager.close()
        temp.cleanup()


class DeleteFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {}, root=self.root)
        self.media = self.root / "media"

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def _sub(self):
        info = {"id": "77", "title": "删我", "url": "u", "cover": "", "description": "", "tags": [],
                "premiered": "", "actors": "", "total": 1, "episodes": [1]}
        return self.manager.store.add(info, {"hgSaveRoot": str(self.media)}, scope="all")

    def test_deletes_only_inside_save_root(self):
        sub = self._sub()
        show = self.media / "删我"
        show.mkdir(parents=True)
        (show / "v.mp4").write_bytes(b"x")
        self.manager.records.mark("77", 1, show / "v.mp4", 1)
        deleted = self.manager.delete_downloaded(sub)
        self.assertEqual(deleted, str(show.resolve()))
        self.assertFalse(show.exists())
        self.assertEqual(self.manager.records.snapshot(), {})

    def test_missing_dir_is_noop(self):
        sub = self._sub()
        self.assertIsNone(self.manager.delete_downloaded(sub))

    def test_escape_refused(self):
        sub = self._sub()
        outside = self.root / "outside"
        outside.mkdir()
        evil = {**sub, "saveRoot": str(self.root)}  # show dir == saveRoot parent trick
        evil_dir = self.root / evil["title"]
        evil_dir.mkdir(exist_ok=True)
        # resolved == root 检查：saveRoot 直指 root 时剧目录 root/删我 合法，删除它没问题；
        # 真正防的是 show_dir_name 越界——safe_title 已把 / 变空格，无法构造 ..
        self.manager.delete_downloaded(evil)
        self.assertFalse(evil_dir.exists())
        self.assertTrue(outside.exists())


class NfoTests(unittest.TestCase):
    def test_tvshow_only_known_fields(self):
        text = hm.tvshow_nfo({"title": "A/B", "id": "9", "url": "https://x", "description": "d",
                              "premiered": "", "tags": ["t1"], "actors": ""})
        self.assertIn("<title>A B</title>", text)
        self.assertIn("<genre>t1</genre>", text)
        self.assertNotIn("<premiered>", text)  # 未知年份不编造
        self.assertNotIn("<uniqueid>https", text)  # url 只进 source/uniqueid(type=huangguo)
        self.assertIn('uniqueid type="huangguo"', text.replace("<uniqueid ", "<uniqueid ").replace("type=", "type="))
        self.assertIn("<source>https://x</source>", text)

    def test_episode_nfo_numbers(self):
        text = hm.episode_nfo({"videoId": "9"}, "第4集", 1, 4)
        self.assertIn("<season>1</season>", text)
        self.assertIn("<episode>4</episode>", text)
        self.assertNotIn("<plot>", text)  # 按需求：分集 NFO 不含内容简介
        self.assertIn(">9-4</uniqueid>", text)  # uniqueid 用站点视频 id


class ClientParsingTests(unittest.TestCase):
    def make(self):
        return FakeClient(pages={
            "/search/video/": FakeResponse(SEARCH_HTML),
            "/video/123/ep-2": FakeResponse(EPISODE_HTML),
            "/video/123/": FakeResponse(DETAIL_HTML),
            "crypto-image-protocol": FakeResponse(PROTOCOL_JS),
        })

    def test_search_parses_fields(self):
        results = self.make().search("x")
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual((row["id"], row["title"], row["episodeLabel"], row["score"]),
                         ("123", "测试剧", "更新至15集", "8.6分"))
        self.assertEqual(row["tags"], ["都市"])
        self.assertIn("pic.drleao.cn", row["cover"])

    def test_detail_fills_missing_episode_one(self):
        detail = self.make().detail(123)
        self.assertEqual(detail["title"], "测试剧")
        self.assertEqual(detail["total"], 7)
        self.assertEqual(detail["episodes"], list(range(1, 8)))  # 链接里只有 2 和 7

    def test_episode_stream_unescapes_entities(self):
        stream = self.make().episode_stream(123, 2)
        self.assertTrue(stream.endswith("&v=3"))
        self.assertIn("auth_key", stream)

    def test_anti_ssrf_allows_site_and_known_cdn(self):
        hc._safe("https://huangguoai.com/video/1/")
        hc._safe("https://pic.drleao.cn/a.jpg", allow_cdn=True)
        for bad in ("http://evil.com/x", "https://evil.com/x", "https://huangguoai.com.evil.cn/",
                    "file:///etc/passwd"):
            with self.subTest(bad=bad), self.assertRaises(hc.HuangguoError):
                hc._safe(bad, allow_cdn=True)
        with self.assertRaises(hc.HuangguoError):
            hc._safe("https://tp4.drleao.cn/a.ts", allow_cdn=False)

    def test_image_decrypt_roundtrip(self):
        client = self.make()
        key, iv = client.image_keys()
        self.assertEqual((key, iv), (b"f5d965df75336270", b"97b60394abc2fbe1"))
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        plain = b"\xff\xd8\xff" + b"jpegdata" + b"\xff\xd9"
        pad = (16 - len(plain) % 16) % 16
        padded = plain + bytes(range(1, pad + 1)) if pad else plain
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        blob = cipher.update(padded) + cipher.finalize()
        fake_url = "https://pic.drleao.cn/img.jpg?auth_key=1"
        client.pages[fake_url] = FakeResponse(content=blob)
        self.assertEqual(client.fetch_image(fake_url), padded)

    def test_image_passthrough_when_plain_jpeg(self):
        client = self.make()
        url = "https://pic.drleao.cn/pl.jpg"
        client.pages[url] = FakeResponse(content=b"\xff\xd8\xffplain")
        self.assertEqual(client.fetch_image(url), b"\xff\xd8\xffplain")


class ImageCacheTests(unittest.TestCase):
    def test_rotated_auth_key_hits_cache(self):
        client = FakeClient(pages={"imgcache1/a.jpg": FakeResponse(content=b"\xff\xd8\xff" + b"z" * 4000)})
        client.decrypt_image = lambda data: data  # 直通
        first = client.fetch_image("https://pic.drleao.cn/imgcache1/a.jpg?auth_key=1")
        self.assertEqual(first[:3], b"\xff\xd8\xff")
        hits = []
        def spy(url, *a, **k):
            hits.append(url)
            raise hc.HuangguoError("不应再回源")
        client._get = spy
        second = hc.Client()  # 全新实例（无 fixture）也应命中模块级缓存
        got = second.fetch_image("https://pic.drleao.cn/imgcache1/a.jpg?auth_key=2")
        self.assertEqual(got, first)
        self.assertEqual(hits, [])

    def test_cache_key_ignores_query(self):
        self.assertEqual(hc._image_cache_key("https://x.c/p.jpg?auth_key=9"), "x.c/p.jpg")
        self.assertIsNone(hc._image_cache_key("garbage"))


class TaskGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = hm.HuangguoManager(lambda: {"hgConcurrent": 2, "hgRetries": 0, "hgRetryInterval": 0}, root=self.root)
        info = {"id": "88", "title": "T88", "url": "u", "cover": "", "description": "", "tags": [],
                "premiered": "", "actors": "", "total": 2, "episodes": [1, 2]}
        self.sub = self.manager.store.add(info, {"hgSaveRoot": str(self.root / "m")}, scope="all")

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def test_duplicate_download_blocked(self):
        release = threading.Event()
        def fake_download(self, task, sub, episodes):
            release.wait(5)
        with patch.object(hm.HuangguoManager, "_run_download", fake_download):
            first = self.manager.enqueue_download(self.sub["id"], [1])
            with self.assertRaises(ValueError):
                self.manager.enqueue_download(self.sub["id"], [2])
            release.set()
            for _ in range(100):
                if self.manager.snapshot_tasks()["tasks"][0]["state"] in ("completed", "failed"):
                    break
                import time as _t; _t.sleep(0.05)

    def test_check_reuses_running_task(self):
        started = threading.Event()
        release = threading.Event()
        def fake_check(self, task, sub):
            started.set()
            release.wait(5)
        with patch.object(hm.HuangguoManager, "_run_check", fake_check):
            one = self.manager.enqueue_check(self.sub["id"])
            started.wait(2)
            two = self.manager.enqueue_check(self.sub["id"])
            self.assertIs(one["id"], two["id"])
            release.set()


if __name__ == "__main__":
    unittest.main()
