"""登录：密码散列、会话令牌、失败冷却与 HTTP 拦截。"""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_helper.auth import AuthError, AuthStore, check_password_policy
from media_helper.config import Storage
from media_helper.server import Application, handler_for


class PolicyTests(unittest.TestCase):
    def test_rejects_short_blank_and_padded_passwords(self):
        for value in ("", "abc", "  abcdef  "):
            with self.assertRaises(AuthError):
                check_password_policy(value)
        with self.assertRaises(AuthError):
            check_password_policy("x" * 200)
        with self.assertRaises(AuthError):
            check_password_policy(None)
        self.assertEqual(check_password_policy("secret123"), "secret123")


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_password_is_persisted_as_salted_hash(self):
        store = AuthStore(self.dir)
        self.assertFalse(store.has_password)
        store.set_password("hunter2!")
        raw = (self.dir / "auth.json").read_text(encoding="utf-8")
        self.assertNotIn("hunter2!", raw)
        record = json.loads(raw)
        self.assertEqual(record["iterations"], 260_000)
        self.assertEqual(len(bytes.fromhex(record["salt"])), 16)

        again = AuthStore(self.dir)
        self.assertTrue(again.has_password)
        self.assertTrue(again.verify("hunter2!"))
        self.assertFalse(again.verify("hunter2"))
        self.assertFalse(again.verify(None))

    def test_same_password_gets_different_salt(self):
        first = AuthStore(self.dir / "a")
        first.set_password("same-pass")
        second = AuthStore(self.dir / "b")
        second.set_password("same-pass")
        self.assertNotEqual(first._record["salt"], second._record["salt"])

    def test_corrupt_file_raises_readable_error(self):
        (self.dir / "auth.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(AuthError):
            AuthStore(self.dir)

    def test_changing_password_drops_existing_sessions(self):
        store = AuthStore(self.dir)
        store.set_password("first-pass")
        token = store.issue()
        self.assertTrue(store.check(token))
        store.set_password("second-pass")
        self.assertFalse(store.check(token))
        self.assertTrue(store.verify("second-pass"))

    def test_session_expiry_and_revocation(self):
        now = [1000.0]
        store = AuthStore(self.dir, clock=lambda: now[0])
        store.set_password("secret123")
        token = store.issue()
        self.assertTrue(store.check(token))
        now[0] += 60  # 使用中续期
        self.assertTrue(store.check(token))
        store.revoke(token)
        self.assertFalse(store.check(token))
        self.assertFalse(store.check(""))

        other = store.issue()
        now[0] += 31 * 24 * 3600
        self.assertFalse(store.check(other))

    def test_failures_lock_out_after_threshold(self):
        now = [0.0]
        store = AuthStore(self.dir, clock=lambda: now[0])
        for _ in range(7):
            store.note_failure("10.0.0.9")
        self.assertEqual(store.blocked_for("10.0.0.9"), 0)
        store.note_failure("10.0.0.9")
        self.assertGreater(store.blocked_for("10.0.0.9"), 0)
        self.assertEqual(store.blocked_for("10.0.0.10"), 0)
        now[0] += 61
        self.assertEqual(store.blocked_for("10.0.0.9"), 0)
        store.reset_failures("10.0.0.9")
        self.assertEqual(store.blocked_for("10.0.0.9"), 0)


class AuthHttpTests(unittest.TestCase):
    """整条链路：未登录 401、登录发 Cookie、带 Cookie 才放行。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / "state")
        self.storage.settings["outputRoot"] = str(self.root / "media")
        self.app = Application(self.storage, dist=self.root / "ui")
        self.ui = self.root / "ui"
        self.ui.mkdir(parents=True, exist_ok=True)
        (self.ui / "index.html").write_text("<html>ui</html>", encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(5)
        self.server.server_close()
        self.app.tasks.close()
        self.temp.cleanup()

    def request(self, method, path, body=None, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            headers = {}
            payload = None
            if body is not None:
                payload = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            if cookie:
                headers["Cookie"] = cookie
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            return response.status, response.read(), response.getheaders()
        finally:
            conn.close()

    def cookie_of(self, headers):
        for name, value in headers:
            if name.lower() == "set-cookie":
                return value.split(";", 1)[0]
        return ""

    def test_no_password_keeps_api_open(self):
        status, body, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        json.loads(body)
        status, body, _ = self.request("GET", "/api/auth/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["hasPassword"], False)

    def test_setup_then_api_requires_cookie(self):
        status, _, headers = self.request("POST", "/api/auth/setup", {"password": "secret123"})
        self.assertEqual(status, 200)
        cookie = self.cookie_of(headers)
        self.assertIn("mh_session=", cookie)
        self.assertIn("HttpOnly", "".join(v for _, v in headers))

        self.assertEqual(self.request("GET", "/api/state")[0], 401)
        status, body, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        json.loads(body)
        # 静态资源不拦，否则登录页自己都加载不出来。
        self.assertEqual(self.request("GET", "/")[0], 200)

    def test_login_rejects_wrong_password_and_accepts_right_one(self):
        self.request("POST", "/api/auth/setup", {"password": "secret123"})
        status, body, _ = self.request("POST", "/api/auth/login", {"password": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("密码不正确", json.loads(body)["error"])

        status, _, headers = self.request("POST", "/api/auth/login", {"password": "secret123"})
        self.assertEqual(status, 200)
        cookie = self.cookie_of(headers)
        self.assertEqual(self.request("GET", "/api/state", cookie=cookie)[0], 200)

        status, _, headers = self.request("POST", "/api/auth/logout", {}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/state", cookie=cookie)[0], 401)

    def test_setup_twice_requires_current_password(self):
        self.request("POST", "/api/auth/setup", {"password": "secret123"})
        status, body, _ = self.request("POST", "/api/auth/setup", {"password": "another1"})
        self.assertEqual(status, 400)
        self.assertIn("当前密码", json.loads(body)["error"])
        status, _, _ = self.request("POST", "/api/auth/setup",
                                    {"password": "another1", "current": "secret123"})
        self.assertEqual(status, 200)
        self.assertTrue(self.app.auth.verify("another1"))

    def test_change_password_needs_current(self):
        self.request("POST", "/api/auth/setup", {"password": "secret123"})
        status, _, _ = self.request("POST", "/api/auth/password", {"current": "wrong", "password": "abcdef"})
        self.assertEqual(status, 400)
        status, _, headers = self.request("POST", "/api/auth/password",
                                          {"current": "secret123", "password": "abcdef"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/state", cookie=self.cookie_of(headers))[0], 200)

    def test_no_auth_flag_bypasses_instead_of_blocking(self):
        self.request("POST", "/api/auth/setup", {"password": "secret123"})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app, no_auth=True))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                conn.request("GET", "/api/state")
                self.assertEqual(conn.getresponse().status, 200)
            finally:
                conn.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
