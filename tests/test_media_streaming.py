"""Exercise the real crawl loop with two local HTML fixtures, no network."""
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock
from bs4 import BeautifulSoup
from test_media_worker import legacy_functions

ROOT = Path(__file__).resolve().parents[1]


class NoBrowserTests(unittest.TestCase):
    def test_hanime_path_never_imports_playwright(self):
        for name in ("hanime_nfo_crawler.py", "media_resolution.py", "media_worker.py",
                     "web_fetch.py", "flaresolverr_client.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("sync_playwright", source, name)
            self.assertNotIn("from playwright", source, name)
            self.assertNotIn("playwright.sync_api", source, name)
            self.assertNotIn("_save_page_screenshot", source, name)


class StreamingCrawlTests(unittest.TestCase):
    def test_first_record_and_images_exist_before_second_item_begins(self):
        ns = legacy_functions("crawl_month", "ensure_dir", "_browser_timeout", "_proxy_url", "_proxy_kwargs", "safe_name", "clean_title_suffix")
        listing = '<div class="home-rows-videos-wrapper">' + ''.join(
            f'<a href="/watch?v={i}"><div class="home-rows-videos-title">Study {i}</div><img src="https://fixture.invalid/{i}.jpg"></a>'
            for i in (1, 2)) + '</div>'
        pages = {
            "https://fixture.invalid/2026/5": listing,
            "https://hanime1.me/watch?v=1": '<h1 id="shareBtn-title">Study 1</h1>',
            "https://hanime1.me/watch?v=2": '<h1 id="shareBtn-title">Study 2</h1>',
        }
        requested = []

        def fetch_html(session, url, *args, **kwargs):
            requested.append(url)
            return pages[url], 200

        def download(session, url, path, *args):
            Path(path).write_bytes(b"fixture image")
            return path, True, "download"

        def write_nfo(basepath, **kwargs):
            Path(basepath + '.nfo').write_text('<movie><title>Study</title></movie>')

        def resolutions(video_id, *args, **kwargs):
            return [1080]

        ns.update(_fetch_html=fetch_html, read_download_resolutions=resolutions,
                  _make_session=Mock(), BeautifulSoup=BeautifulSoup,
                  BASE_SEARCH="https://fixture.invalid/{year}/{month}", csv=csv, json=json,
                  LIST_WRAPPER=".home-rows-videos-wrapper", LIST_ITEMS='.home-rows-videos-wrapper a[href*="watch?v="]',
                  DETAIL_TITLE="#shareBtn-title", DETAIL_DESC="#description", DETAIL_TAG_ITEM=".tag",
                  time=SimpleNamespace(sleep=lambda seconds: None), ThreadPoolExecutor=ThreadPoolExecutor,
                  as_completed=as_completed, _download_image=download, write_movie_nfo=write_nfo,
                  translate_text_ja2zh=lambda value: value, pick_fanart_url=lambda *a, **kw: ("", ""),
                  find_stream_url=lambda html: "")
        observed = []
        with tempfile.TemporaryDirectory() as directory:
            month = Path(directory) / '2026-05'
            def progress(event):
                if event.get('type') == 'item' and event['index'] == 2:
                    rows = json.loads((month / '2026-05.json').read_text(encoding='utf-8'))
                    self.assertEqual(['1'], [r['id'] for r in rows])
                    self.assertTrue((month / 'Study 1.nfo').exists())
                    self.assertTrue((month / 'Study 1-poster.jpg').exists())
                    observed.append('first-published')
            result = ns['crawl_month'](2026, 5, directory, progress=progress, nfo_settings={'categories': []})
            self.assertEqual(2, len(result))
            self.assertEqual(['first-published'], observed)
            self.assertEqual(2, len(list(month.glob('*.nfo'))))
            self.assertEqual([1080], [r['available_resolutions'] for r in result][0])
        self.assertEqual("https://fixture.invalid/2026/5", requested[0])


class BlockedListingTests(unittest.TestCase):
    def test_challenge_page_reports_flaresolverr_hint(self):
        ns = legacy_functions("crawl_month", "ensure_dir", "_browser_timeout", "_proxy_url", "_proxy_kwargs", "safe_name", "clean_title_suffix")
        ns.update(_fetch_html=lambda *a, **kw: ("<html>Just a moment...</html>", 403),
                  _make_session=Mock(), BeautifulSoup=BeautifulSoup,
                  BASE_SEARCH="https://fixture.invalid/{year}/{month}", csv=csv, json=json,
                  LIST_WRAPPER=".home-rows-videos-wrapper",
                  LIST_ITEMS='.home-rows-videos-wrapper a[href*="watch?v="]',
                  time=SimpleNamespace(sleep=lambda seconds: None), ThreadPoolExecutor=ThreadPoolExecutor,
                  as_completed=as_completed)

        def progress(event):
            pass

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError) as caught:
                ns['crawl_month'](2026, 5, directory, progress=progress)
        self.assertIn("HTTP 403", str(caught.exception))
