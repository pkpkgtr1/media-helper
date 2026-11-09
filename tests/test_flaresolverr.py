"""FlareSolverr session wiring: every solver call carries the configured session.

Run from the project root: python -m unittest discover -s tests -p test_flaresolverr.py
The solver itself is mocked; no network access is needed.
"""
from __future__ import annotations

import os
import unittest

import media_helper.net as fs


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttp:
    """Records every request.get / sessions.create payload."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(json)
        reply = self.replies.pop(0) if self.replies else {"status": "ok", "solution": {}}
        return FakeResponse(reply)


OK_PAGE = {"status": "ok", "solution": {"status": 200, "response": "<html>ok</html>",
                                        "userAgent": "SolvedUA/1", "cookies": []}}


class SessionSettingTests(unittest.TestCase):
    def setUp(self):
        self.keep = {name: os.environ.get(name) for name in
                     (fs.ENV_ENABLED, fs.ENV_URL, fs.ENV_SESSION)}

        def restore():
            for name, value in self.keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value
        self.addCleanup(restore)

    def test_normalize_session_strips_whitespace(self):
        # 会话 ID 进 JSON 载荷，空白一律去掉，避免带出不可见字符。
        self.assertEqual("mysession", fs.normalize_session(" my \n session "))

    def test_normalize_session_rejects_overlong_value(self):
        with self.assertRaisesRegex(ValueError, "会话 ID"):
            fs.normalize_session("a" * (fs.MAX_SESSION_LENGTH + 1))

    def test_configure_publishes_and_clears_session(self):
        fs.configure({"flaresolverrEnabled": True, "flaresolverrSession": " s1 "})
        self.assertEqual("s1", fs.session_name())
        fs.configure({"flaresolverrEnabled": False, "flaresolverrSession": "s1"})
        self.assertEqual("", fs.session_name())

    def test_solve_sends_session_when_configured(self):
        fs.configure({"flaresolverrEnabled": True, "flaresolverrSession": "s1"})
        http = FakeHttp([OK_PAGE])
        solution = fs.solve("https://example.invalid/a", session=http)
        self.assertEqual("s1", http.calls[0]["session"])
        self.assertEqual("request.get", http.calls[0]["cmd"])
        self.assertEqual(200, solution.status)
        self.assertEqual("SolvedUA/1", solution.user_agent)

    def test_solve_omits_session_when_empty(self):
        fs.configure({"flaresolverrEnabled": True})
        http = FakeHttp([OK_PAGE])
        fs.solve("https://example.invalid/a", session=http)
        self.assertNotIn("session", http.calls[0])

    def test_missing_session_is_created_and_retried_once(self):
        fs.configure({"flaresolverrEnabled": True, "flaresolverrSession": "s1"})
        http = FakeHttp([
            {"status": "error", "message": "Error: invalid session"},
            {"status": "ok", "message": "Session created successfully."},
            OK_PAGE,
        ])
        solution = fs.solve("https://example.invalid/a", session=http)
        self.assertEqual(["request.get", "sessions.create", "request.get"],
                         [call["cmd"] for call in http.calls])
        self.assertEqual("s1", http.calls[1]["session"])
        self.assertEqual(200, solution.status)

    def test_other_errors_are_not_retried(self):
        fs.configure({"flaresolverrEnabled": True, "flaresolverrSession": "s1"})
        http = FakeHttp([{"status": "error", "message": "Challenge failed"}])
        with self.assertRaisesRegex(fs.FlareSolverrError, "Challenge failed"):
            fs.solve("https://example.invalid/a", session=http)
        self.assertEqual(1, len(http.calls))

    def test_create_session_tolerates_already_existing(self):
        http = FakeHttp([{"status": "error", "message": "Session already exists."}])
        self.assertEqual("s1", fs.create_session("s1", http=http))
        http = FakeHttp([{"status": "error", "message": "boom"}])
        with self.assertRaisesRegex(fs.FlareSolverrError, "会话创建失败"):
            fs.create_session("s1", http=http)


if __name__ == "__main__":
    unittest.main()
