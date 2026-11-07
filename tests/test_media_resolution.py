import unittest
from media_resolution import read_download_resolutions
from media_resolution import download_resolutions, entry_resolution, resolution_from_url


class ResolutionTests(unittest.TestCase):
    def test_url_quality_ignores_ids_and_query_tokens(self):
        self.assertEqual(720, resolution_from_url('https://example.invalid/406532-sc-720p.mp4?token=1080'))
        self.assertEqual(0, resolution_from_url('https://example.invalid/1080406.mp4?quality=1080p'))
        self.assertEqual(1080, resolution_from_url('https://example.invalid/1080p/video.mp4'))

    def test_download_table_uses_highest_available_and_ignores_content_tags(self):
        html = '<div class="tag">2160p</div><table>' + ''.join(
            f'<tr><td>HD ({q}p)</td><td>mp4</td><td><a href="/file?id={q}">Download</a></td></tr>'
            for q in (720, 1080, 480)) + '</table>'
        self.assertEqual([1080, 720, 480], download_resolutions(html))
        self.assertEqual([], download_resolutions('<h1>Verify access</h1>'))

    def test_available_quality_overrides_playback_and_filtered_tags_do_not_matter(self):
        item = dict(stream_url='https://example.invalid/fixture-720p.mp4', tags=[], available_resolutions=[480,1080,720])
        self.assertEqual('1080p', entry_resolution(item)[0])
        item.pop('available_resolutions')
        self.assertEqual('', entry_resolution(item)[0])
        self.assertEqual('', entry_resolution({'tags':['1080p']})[0])

    def test_transient_http_failure_retries(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                return '<h1>Service Unavailable</h1>', 503
            return '<table><tr><td>1080p</td><td><a href="/file">Download</a></td></tr></table>', 200

        self.assertEqual([1080], read_download_resolutions('123', fetch=fetch))
        self.assertEqual(2, len(calls))
        self.assertTrue(calls[0].endswith('/download?v=123'))

    def test_missing_quality_is_reported_after_retry(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return '<h1>No download table</h1>', 200

        with self.assertRaises(RuntimeError):
            read_download_resolutions('123', fetch=fetch)
        self.assertEqual(2, len(calls))

    def test_non_numeric_id_never_calls_the_network(self):
        def fetch(url):
            raise AssertionError('must not fetch')

        self.assertEqual([], read_download_resolutions('abc', fetch=fetch))
