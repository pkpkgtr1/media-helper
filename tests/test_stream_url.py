"""直链里的 HTML 转义：`&amp;` 会让签名失效，必须还原后再请求。

真实案例：hanime1 下载页给出的
`https://vdownload-8.hembed.com/143654-720p.mp4?token=xxx&amp;expires=yyy`
原样请求返回 403（服务端只收到 token 一个参数），还原后才是 200。
"""
import unittest

from media_helper.crawler import clean_stream_url, find_stream_url


class CleanStreamUrlTests(unittest.TestCase):
    def test_unescapes_html_entities_in_query(self):
        dirty = "https://vdownload-8.hembed.com/143654-720p.mp4?token=abc&amp;expires=1794343798"
        clean = clean_stream_url(dirty)
        self.assertEqual(
            "https://vdownload-8.hembed.com/143654-720p.mp4?token=abc&expires=1794343798", clean)
        self.assertNotIn("&amp;", clean)

    def test_handles_double_escaped_pages(self):
        self.assertEqual("https://x.invalid/a.mp4?t=1&e=2",
                         clean_stream_url("https://x.invalid/a.mp4?t=1&amp;amp;e=2"))

    def test_other_entities_are_restored_too(self):
        self.assertEqual("https://x.invalid/a.mp4?a=1&b=2&c=3",
                         clean_stream_url("https://x.invalid/a.mp4?a=1&amp;b=2&#38;c=3"))

    def test_leaves_plain_urls_alone(self):
        for url in ("https://x.invalid/a.mp4?secure=abc==,123",
                    "https://x.invalid/hls/index.m3u8?token=1&expires=2",
                    ""):
            self.assertEqual(url, clean_stream_url(url))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual("https://x.invalid/a.mp4?t=1&e=2",
                         clean_stream_url("  https://x.invalid/a.mp4?t=1&amp;e=2\n"))


class FindStreamUrlTests(unittest.TestCase):
    def test_m3u8_and_mp4_sources_are_unescaped(self):
        html = '<video><source src="https://x.invalid/v.mp4?token=1&amp;expires=2"></video>'
        self.assertEqual("https://x.invalid/v.mp4?token=1&expires=2", find_stream_url(html))
        hls = '<script>var u="https://x.invalid/hls/m.m3u8?token=9&amp;expires=8";</script>'
        self.assertEqual("https://x.invalid/hls/m.m3u8?token=9&expires=8", find_stream_url(hls))

    def test_missing_stream_returns_empty(self):
        self.assertEqual("", find_stream_url("<html><body>no video</body></html>"))


if __name__ == "__main__":
    unittest.main()
