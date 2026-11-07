import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import media_worker


def legacy_functions(*names, source_file="hanime_nfo_crawler.py"):
    """Load pure function bodies without importing browser/translation modules."""
    import os, re, time, unicodedata
    from xml.sax.saxutils import escape
    source = ast.parse((ROOT / source_file).read_text(encoding="utf-8-sig"))
    nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(os=os, re=re, time=time, tempfile=tempfile, unicodedata=unicodedata,
                     __file__=str(ROOT / source_file),
                     xml_escape=escape, Optional=__import__("typing").Optional, Dict=dict,
                     urlparse=__import__("urllib.parse", fromlist=["urlparse"]).urlparse,
                     unquote=__import__("urllib.parse", fromlist=["unquote"]).unquote,
                     Tuple=__import__("typing").Tuple, requests=SimpleNamespace(Session=object),
                     List=__import__("typing").List, Callable=__import__("typing").Callable,
                     TAG_BLACKLIST_NORM=set(), TAG_BLACKLIST_NORM_LOWER=set(),
                     TITLE_SUFFIX_PATTERN=re.compile(r"(?:\s*\[[^\]]+\]\s*)+$"))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "legacy_test", "exec"), namespace)
    return namespace


class WorkerTests(unittest.TestCase):
    def test_empty_metadata_never_reports_completion(self):
        self.job["kind"] = "metadata"
        with self.assertRaisesRegex(RuntimeError, "未返回作品"):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(crawl_month=lambda *a, **kw: []))
        self.assertFalse(any(e["type"] == "done" for e in self.events))

    def test_metadata_missing_actual_files_never_reports_completion(self):
        self.job["kind"] = "metadata"
        with self.assertRaisesRegex(RuntimeError, "缺少"):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(crawl_month=lambda *a, **kw: [self.item]))
        self.assertFalse(any(e["type"] == "done" for e in self.events))

    def test_metadata_progress_tracks_current_title_and_published_files(self):
        self.job["kind"] = "metadata"
        def crawl(*args, progress, **kwargs):
            progress(dict(type="start", total=1))
            progress(dict(type="item", index=1, total=1, id="1", title="Fixture"))
            (self.month / "Fixture.nfo").write_text("<movie><title>Fixture</title></movie>")
            progress(dict(type="save_nfo"))
            (self.month / "Fixture-poster.jpg").write_bytes(b"fixture image")
            progress(dict(type="save_poster"))
            progress(dict(type="item_done"))
            return [self.item]
        media_worker.run_job(self.job, self.events.append, SimpleNamespace(crawl_month=crawl))
        phases = [e for e in self.events if e.get("currentCode") == "1"]
        self.assertEqual("Fixture", phases[0]["currentTitle"])
        self.assertEqual(1, phases[-1]["processed"])
        self.assertEqual(1, phases[-1]["itemTotal"])
        self.assertEqual("done", self.events[-1]["type"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.month = self.root / "2026-03"
        self.item = {"id": "1", "title": "Fixture", "title_fs": "Fixture", "tags": ["Example"]}
        self.job = dict(id="test", kind="video", year=2026, month=3, outputRoot=str(self.root),
                        items=[self.item], settings=dict(retries=0, downloadInterval=0))
        self.events = []

    def video_path(self):
        self.month.mkdir(exist_ok=True)
        return self.month / "Fixture.mp4"

    def test_existing_video_skip_does_not_call_downloader(self):
        target = self.video_path()
        target.write_bytes(b"existing movie")
        crawler = SimpleNamespace(download_video_for_item=Mock())
        media_worker.run_job(self.job, self.events.append, crawler)
        crawler.download_video_for_item.assert_not_called()
        self.assertEqual(target.read_bytes(), b"existing movie")
        self.assertEqual(self.events[-1], {"type": "done"})

    def test_failed_redownload_preserves_original(self):
        target = self.video_path()
        target.write_bytes(b"original")
        self.job["settings"]["existingVideo"] = "redownload"

        def download(item, output, **kwargs):
            candidate = Path(output) / "Fixture.mp4"
            candidate.write_bytes(b"<html>error</html>")
            return str(candidate)

        with self.assertRaisesRegex(RuntimeError, "MP4"):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(download_video_for_item=download))
        self.assertEqual(target.read_bytes(), b"original")
        self.assertFalse(any(e["type"] == "done" for e in self.events))
        self.assertFalse(list(self.month.glob(".media-download-*")))

    def test_successful_redownload_is_published_after_validation(self):
        target = self.video_path()
        target.write_bytes(b"original")
        self.job["settings"]["existingVideo"] = "redownload"
        mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 128

        def download(item, output, **kwargs):
            self.assertEqual(target.read_bytes(), b"original")
            candidate = Path(output) / "Fixture.mp4"
            candidate.write_bytes(mp4)
            kwargs["progress_callback"](len(mp4), len(mp4), str(candidate))
            return str(candidate)

        media_worker.run_job(self.job, self.events.append, SimpleNamespace(download_video_for_item=download))
        self.assertEqual(target.read_bytes(), mp4)
        self.assertEqual(self.events[-1]["type"], "done")
        self.assertTrue(any(e.get("downloaded") == len(mp4) for e in self.events))

    def test_unknown_total_and_phase_callbacks_are_not_fake_percentages(self):
        def download(item, output, **kwargs):
            kwargs["progress_callback"](5, "Opening page")
            kwargs["progress_callback"](100, 0, "Fixture.mp4")
            return None

        with self.assertRaises(RuntimeError):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(download_video_for_item=download))
        byte_event = next(e for e in self.events if e.get("downloaded") == 100)
        self.assertTrue(byte_event["indeterminate"])
        self.assertEqual(byte_event["progress"], 0)

    def test_item_cannot_escape_month_directory(self):
        self.job["items"] = [{"title_fs": "../outside"}]
        crawler = SimpleNamespace(download_video_for_item=Mock())
        with self.assertRaises(ValueError):
            media_worker.run_job(self.job, self.events.append, crawler)
        crawler.download_video_for_item.assert_not_called()

    def test_video_symlink_cannot_escape_output_directory(self):
        self.month.mkdir()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "other.mp4"
            target.write_bytes(b"other file")
            try:
                (self.month / "Fixture.mp4").symlink_to(target)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
            crawler = SimpleNamespace(download_video_for_item=Mock())
            with self.assertRaisesRegex(ValueError, "月份目录之外"):
                media_worker.run_job(self.job, self.events.append, crawler)
            self.assertEqual(target.read_bytes(), b"other file")
            crawler.download_video_for_item.assert_not_called()

    def test_month_symlink_cannot_escape_output_directory(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                self.month.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "媒体根目录之外"):
                media_worker.run_job(self.job, self.events.append, SimpleNamespace())

    def test_partial_metadata_is_failure(self):
        self.job["kind"] = "metadata"

        def crawl(*args, **kwargs):
            kwargs["progress"]({"type": "start", "total": 2})
            return [self.item]

        with self.assertRaisesRegex(RuntimeError, "实际完成 1"):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(crawl_month=crawl))
        self.assertFalse(any(e["type"] == "done" for e in self.events))

    def test_cover_failure_event_does_not_report_success(self):
        self.job["kind"] = "covers"

        def covers(*args, **kwargs):
            kwargs["progress"]({"type": "asset_error", "msg": "fixture failure"})
            return [self.item]

        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            media_worker.run_job(self.job, self.events.append, SimpleNamespace(redownload_covers_only=covers))

    def test_repair_does_not_rewrite_existing_files(self):
        self.job["kind"] = "repair"
        self.month.mkdir()
        for suffix in (".nfo", "-poster.jpg", "-fanart.jpg", ".mp4"):
            (self.month / ("Fixture" + suffix)).write_bytes(b"existing")
        crawler = SimpleNamespace(_make_session=Mock(), write_movie_nfo=Mock(),
                                  _download_image=Mock(), download_video_for_item=Mock())
        media_worker.run_job(self.job, self.events.append, crawler)
        crawler.write_movie_nfo.assert_not_called()
        crawler._download_image.assert_not_called()
        crawler.download_video_for_item.assert_not_called()

    def test_repair_missing_source_reports_failure(self):
        self.job["kind"] = "repair"
        self.video_path().write_bytes(b"existing")
        (self.month / "Fixture.nfo").write_bytes(b"existing")
        crawler = SimpleNamespace(_make_session=Mock(), _download_image=Mock(), download_video_for_item=Mock())
        with self.assertRaisesRegex(RuntimeError, "没有可用图片地址"):
            media_worker.run_job(self.job, self.events.append, crawler)
        crawler._download_image.assert_not_called()

    def test_repair_legacy_screenshot_mode_downloads_cover_instead(self):
        self.job["kind"] = "repair"
        self.job["settings"]["posterMode"] = "screenshot"
        self.item["url"] = "https://fixture.invalid/page"
        self.item["cover_url"] = "https://fixture.invalid/cover.jpg"
        self.video_path().write_bytes(b"existing video")
        (self.month / "Fixture.nfo").write_bytes(b"existing nfo")

        def download(session, url, path, *args, **kwargs):
            Path(path).write_bytes(b"cover fixture")
            return path, True, "download"

        crawler = SimpleNamespace(_make_session=Mock(), _download_image=download,
                                  download_video_for_item=Mock())
        media_worker.run_job(self.job, self.events.append, crawler)
        self.assertEqual((self.month / "Fixture-poster.jpg").read_bytes(), b"cover fixture")
        self.assertEqual((self.month / "Fixture-fanart.jpg").read_bytes(), b"cover fixture")
        self.assertEqual(self.events[-1]["type"], "done")

    def test_cli_stdout_is_json_even_for_child_process_output(self):
        job_file = self.root / "job.json"
        job_file.write_text("{}", encoding="utf-8")
        script = """
import media_worker, subprocess, sys
def fake(job, emit):
    print('python diagnostic')
    subprocess.run([sys.executable, '-c', "print('child diagnostic')"], check=True)
    emit({'type': 'done'})
media_worker.run_job = fake
raise SystemExit(media_worker.main([sys.argv[1]]))
"""
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(job_file)],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], [{"type": "done"}])
        self.assertIn("python diagnostic", result.stderr)
        self.assertIn("child diagnostic", result.stderr)


class LegacyWriteTests(unittest.TestCase):
    def test_empty_remote_listing_does_not_replace_existing_index(self):
        ns = legacy_functions("crawl_month", "ensure_dir", "_browser_timeout", "_proxy_url", "_proxy_kwargs")
        soup = Mock()
        soup.select.return_value = []
        ns.update(_fetch_html=lambda *a, **kw: ("<html></html>", 200), _make_session=Mock(),
                  BeautifulSoup=lambda *args: soup, BASE_SEARCH="https://fixture.invalid/{year}/{month}",
                  LIST_WRAPPER="fixture", LIST_ITEMS="fixture", time=SimpleNamespace(sleep=lambda x: None))
        with tempfile.TemporaryDirectory() as directory:
            month = Path(directory) / "2026-03"
            month.mkdir()
            index = month / "2026-03.json"
            old = '[{"id":"1","title":"Fixture"}]'
            index.write_text(old, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "未返回作品"):
                ns["crawl_month"](2026, 3, directory)
            self.assertEqual(index.read_text(encoding="utf-8"), old)
            index.unlink()
            with self.assertRaisesRegex(RuntimeError, "未返回作品"):
                ns["crawl_month"](2026, 3, directory)
            self.assertFalse(index.exists())
            self.assertFalse((month / "2026-03.csv").exists())

    def test_external_download_failure_does_not_emit_saved_or_return_path(self):
        ns = legacy_functions("download_html", "safe_filename_for_windows", source_file="download_move.py")
        ns["_extract_urls_via_requests"] = lambda *args, **kwargs: (["Fixture"], ["https://fixture.invalid/1080p.mp4"])
        ns["download_file"] = Mock(return_value=False)
        events = []
        with tempfile.TemporaryDirectory() as directory:
            result = ns["download_html"]("1", "202603", lambda *args: events.append(args), out_dir=directory)
        self.assertIsNone(result)
        self.assertFalse(any(e[0] == 100 for e in events))

    def test_nfo_is_valid_xml_and_writes_same_selected_tags_and_genres(self):
        import media_storage
        catalog_patch = patch.object(media_storage, "official_categories", return_value=[dict(name="A & B", group="Fixture")])
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)
        import xml.etree.ElementTree as ET
        ns = legacy_functions("write_movie_nfo", "clean_title_suffix", "rating_to_10")
        with tempfile.TemporaryDirectory() as directory:
            base = str(Path(directory) / "fixture")
            settings = dict(writeTags=False, writeGenres=True, unseenDefault="exclude",
                            categories=[dict(name="A & B", checked=True), dict(name="Hidden", checked=False)])
            ns["write_movie_nfo"](base, title_raw="Example & <test>", title_zh="Caption ]]>",
                                   plot_raw="Text ]]>", plot_zh="", tags=["A & B", "Hidden", "Unknown"],
                                   premiered="Date & <unknown>", maker="Studio & <X>", label="Label & <X>",
                                   series_name="Series & <X>", mid="1&2", num="N&1", release="Date & <X>",
                                   thumb="https://fixture.invalid/?a=1&b=2", fanart="Art & <X>",
                                   nfo_settings=settings)
            root = ET.parse(base + ".nfo").getroot()
            self.assertEqual(root.findtext("title"), "Example & <test>")
            self.assertEqual(root.findtext("outline"), "Caption ]]>")
            self.assertEqual(root.findtext("premiered"), "Date & <unknown>")
            self.assertEqual(root.findtext("maker"), "Studio & <X>")
            self.assertEqual(root.findtext("series"), "Series & <X>")
            self.assertEqual(root.findtext("thumb"), "https://fixture.invalid/?a=1&b=2")
            self.assertEqual([e.text for e in root.findall("tag")], ["A & B"])
            self.assertEqual([e.text for e in root.findall("genre")], ["A & B"])

    def test_failed_forced_image_download_preserves_original(self):
        ns = legacy_functions("_download_image", "ensure_dir")
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.content = b"<html>blocked</html>"
        session = Mock()
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poster.jpg"
            path.write_bytes(b"original image")
            _, ok, _ = ns["_download_image"](session, "https://fixture.invalid/image", str(path), force=True)
            self.assertFalse(ok)
            self.assertEqual(path.read_bytes(), b"original image")


if __name__ == "__main__":
    unittest.main()
