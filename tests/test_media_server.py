"""Task lifecycle checks use an isolated fake worker and temporary state only."""
import ctypes
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import threading
import unittest
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_server import AccessPolicy, Application, TaskManager, handler_for, split_host, with_browser_hint
from media_storage import Storage, atomic_write


FAKE_WORKER = r'''
import json, pathlib, subprocess, sys, time
job = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
mode = job.get('scenario', 'success')
marker = pathlib.Path(job['marker'])
attempt = int(marker.read_text()) + 1 if marker.exists() else 1
marker.write_text(str(attempt))
def emit(event):
    print(json.dumps(event), flush=True)
if mode in ('block', 'block_then_success') and not (mode == 'block_then_success' and attempt > 1):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    marker.with_suffix('.child').write_text(str(child.pid))
    emit({'type': 'progress', 'progress': 10, 'indeterminate': True})
    while True:
        time.sleep(.02)
if mode == 'error_done':
    emit({'type': 'error', 'msg': 'fixture failed'})
if mode != 'no_done':
    emit({'type': 'progress', 'progress': 90, 'downloaded': 1024, 'total': 2048, 'speed': 1024, 'eta': 1, 'currentTitle': 'River Study', 'currentCode': '1', 'currentIndex': 1, 'processed': 1, 'itemTotal': 2, 'phase': 'Files saved'})
    emit({'type': 'done'})
if mode == 'nonzero':
    print('fixture stderr', file=sys.stderr)
    raise SystemExit(7)
'''


def process_running(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.worker = self.root / "fake_worker.py"
        self.worker.write_text(FAKE_WORKER, encoding="utf-8")
        self.storage = Storage(self.root / "state")
        self.storage.settings["downloadInterval"] = 0
        self.storage.settings["openAfter"] = False
        self.manager = TaskManager(self.storage, self.worker)

    def tearDown(self):
        self.manager.close()
        self.manager.thread.join(timeout=10)
        self.temp.cleanup()

    def wait_for(self, condition, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = condition()
            if value:
                return value
            time.sleep(.015)
        self.fail("Task manager condition timed out: " + repr(self.manager.snapshot()))

    def task(self, task_id):
        return next(t for t in self.manager.snapshot()["tasks"] if t["id"] == task_id)

    def enqueue(self, scenario="success", month=3):
        # Hold the scheduler lock until the fixture-only job options are attached.
        with self.manager.lock:
            self.manager.enqueue(dict(kind="metadata", year=2026, month=month, outputRoot=str(self.root / "media")))
            task = self.manager.tasks[-1]
            marker = self.root / (task["id"] + ".attempt")
            task["_job"].update(scenario=scenario, marker=str(marker))
            return task["id"], marker

    def terminal(self, task_id):
        return self.wait_for(lambda: self.task(task_id) if self.task(task_id)["state"] not in ("waiting", "downloading") else None)

    def test_done_plus_clean_exit_completes(self):
        task_id, marker = self.enqueue()
        task = self.terminal(task_id)
        self.assertEqual(task["state"], "completed")
        self.assertEqual(task["progress"], 100)
        self.assertEqual(task["downloaded"], "1.0 KB")
        self.assertEqual(task["speed"], "1.0 KB/s")
        self.assertEqual(task["currentTitle"], "River Study")
        self.assertEqual(task["itemTotal"], 2)
        self.assertEqual(task["processed"], 1)

    def test_done_then_nonzero_exit_is_failed(self):
        task_id, _ = self.enqueue("nonzero")
        task = self.terminal(task_id)
        self.assertEqual(task["state"], "failed")
        self.assertIn("7", task["error"])
        self.assertIn("fixture stderr", task["error"])

    def test_clean_exit_without_done_is_failed(self):
        task_id, _ = self.enqueue("no_done")
        self.assertEqual(self.terminal(task_id)["state"], "failed")

    def test_error_followed_by_done_is_failed(self):
        task_id, _ = self.enqueue("error_done")
        task = self.terminal(task_id)
        self.assertEqual(task["state"], "failed")
        self.assertEqual(task["error"], "fixture failed")

    def test_cancel_waiting_task_never_starts_worker(self):
        active_id, active_marker = self.enqueue("block")
        self.wait_for(lambda: active_marker.with_suffix(".child").exists())
        waiting_id, waiting_marker = self.enqueue("success", month=4)
        self.manager.action(dict(action="cancel", id=waiting_id))
        self.manager.action(dict(action="cancel", id=active_id))
        self.wait_for(lambda: self.manager.process is None)
        self.assertEqual(self.task(waiting_id)["state"], "cancelled")
        self.assertFalse(waiting_marker.exists())

    def test_running_cancel_kills_child_process_tree(self):
        task_id, marker = self.enqueue("block")
        child_marker = marker.with_suffix(".child")
        self.wait_for(child_marker.exists)
        child_pid = int(child_marker.read_text())
        self.assertTrue(process_running(child_pid))
        self.manager.action(dict(action="cancel", id=task_id))
        self.wait_for(lambda: self.manager.process is None)
        self.wait_for(lambda: not process_running(child_pid))
        self.assertEqual(self.task(task_id)["state"], "cancelled")

    def test_immediate_retry_cannot_be_overwritten_by_cancelled_run(self):
        task_id, marker = self.enqueue("block_then_success")
        self.wait_for(lambda: marker.with_suffix(".child").exists())
        # Force retry to race with the previous monitor's final bookkeeping.
        with self.manager.lock:
            self.manager.action(dict(action="cancel", id=task_id))
            with self.assertRaisesRegex(ValueError, "结束处理中"):
                self.manager.action(dict(action="retry", id=task_id))
        self.wait_for(lambda: self.manager.process is None and self.manager.active_id is None)
        self.manager.action(dict(action="retry", id=task_id))
        self.wait_for(lambda: marker.exists() and marker.read_text() == "2")
        self.assertEqual(self.terminal(task_id)["state"], "completed")
        self.assertEqual(marker.read_text(), "2")

    def test_restart_marks_interrupted_tasks_cancelled(self):
        self.manager.close()
        self.manager.thread.join(timeout=10)
        tasks = [dict(id="interrupted", title="Fixture", state="downloading", progress=12),
                 dict(id="queued", title="Fixture 2", state="waiting", progress=0),
                 dict(id="done", title="Fixture 3", state="completed", progress=100)]
        atomic_write(self.storage.state_dir / "tasks.json", json.dumps(tasks).encode())
        self.manager = TaskManager(self.storage, self.worker)
        states = {task["id"]: task["state"] for task in self.manager.snapshot()["tasks"]}
        self.assertEqual(states, dict(interrupted="cancelled", queued="cancelled", done="completed"))
        self.assertIsNone(self.manager.process)


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / "state")
        self.storage.settings["outputRoot"] = str(self.root / "media")
        self.app = Application(self.storage, dist=self.root / "ui")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.app.tasks.close()
        self.app.tasks.thread.join(5)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            content = response.read()
            return response.status, json.loads(content)
        finally:
            conn.close()

    def test_untrusted_host_or_origin_is_rejected(self):
        status, _ = self.request("GET", "/api/state", headers={"Host": "attacker.invalid"})
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/state", headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(status, 403)
        self.assertEqual(self.app.tasks.snapshot()["tasks"], [])

    def test_non_json_post_is_rejected_without_mutation(self):
        before = self.app.tasks.snapshot()
        status, _ = self.request("POST", "/api/task-action", body='{"action":"clear-completed"}',
                                 headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(self.app.tasks.snapshot(), before)

    def test_invalid_json_and_non_object_json_are_rejected(self):
        for body in ("{", "[]"):
            with self.subTest(body=body):
                status, _ = self.request("POST", "/api/settings", body=body,
                                         headers={"Content-Type": "application/json"})
                self.assertEqual(status, 400)
        self.assertFalse((self.storage.state_dir / "settings.json").exists())

    def test_state_get_does_not_write_files_or_change_tasks(self):
        before_tasks = self.app.tasks.snapshot()
        before_files = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                        for p in self.root.rglob("*") if p.is_file()}
        status, result = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(result, before_tasks)
        after_files = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                       for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after_files, before_files)
        self.assertEqual(self.app.tasks.snapshot(), before_tasks)


class AccessPolicyTests(unittest.TestCase):
    """Loopback stays closed by default; LAN mode widens only to the chosen CIDRs."""

    def setUp(self):
        self.local = AccessPolicy()
        self.lan = AccessPolicy(lan=True, cidrs=["192.168.11.0/24"])

    def test_loopback_policy_rejects_foreign_host_and_lan_peers(self):
        self.assertTrue(self.local.host_ok("127.0.0.1:8765"))
        self.assertTrue(self.local.host_ok("localhost:8765"))
        self.assertFalse(self.local.host_ok("attacker.invalid"))
        self.assertFalse(self.local.host_ok("192.168.11.7:8765"))
        self.assertFalse(self.local.host_ok("nas.example.com:8765"))
        self.assertFalse(self.local.host_ok("nas:8765"))
        self.assertTrue(self.local.peer_ok("127.0.0.1"))
        self.assertFalse(self.local.peer_ok("192.168.11.7"))
        self.assertFalse(self.local.peer_ok("8.8.8.8"))
        self.assertFalse(self.local.peer_ok("not-an-ip"))

    def test_lan_policy_allows_local_subnet_only(self):
        self.assertTrue(self.lan.host_ok("192.168.11.250:8765"))
        self.assertTrue(self.lan.host_ok(f"{socket.gethostname()}:8765"))
        self.assertFalse(self.lan.host_ok("nas:8765"))
        self.assertFalse(self.lan.host_ok("172.22.222.1:8765"))
        self.assertFalse(self.lan.host_ok("8.8.8.8:8765"))
        self.assertFalse(self.lan.host_ok("attacker.invalid:8765"))
        self.assertTrue(self.lan.peer_ok("192.168.11.7"))
        self.assertFalse(self.lan.peer_ok("172.22.222.9"))
        self.assertFalse(self.lan.peer_ok("8.8.8.8"))
    def test_default_cidrs_cover_private_ranges(self):
        default = AccessPolicy(lan=True)
        self.assertTrue(default.peer_ok("10.1.2.3"))
        self.assertTrue(default.peer_ok("172.16.5.4"))
        self.assertFalse(default.peer_ok("172.5.5.4"))
        self.assertTrue(default.peer_ok("192.168.9.9"))

    def test_invalid_cidr_is_reported(self):
        with self.assertRaises(ValueError):
            AccessPolicy(lan=True, cidrs=["192.168.11/999"])

    def test_origin_rules(self):
        self.assertTrue(self.local.origin_ok(""))
        self.assertTrue(self.local.origin_ok("http://127.0.0.1:8765"))
        self.assertTrue(self.local.origin_ok("http://localhost:8443"))
        self.assertFalse(self.local.origin_ok("https://attacker.invalid"))
        self.assertFalse(self.local.origin_ok("null"))
        self.assertFalse(self.local.origin_ok("127.0.0.1:8765"))
        self.assertTrue(self.lan.origin_ok("http://192.168.11.250:8765"))
        self.assertFalse(self.lan.origin_ok("http://172.22.222.1:8765"))

    def test_ipv6_loopback_and_bracketed_hosts(self):
        self.assertTrue(self.local.host_ok("[::1]:8765"))
        self.assertTrue(self.local.peer_ok("::1"))
        self.assertEqual(split_host("[::1]:8765"), ("::1", "8765"))
        self.assertEqual(split_host("192.168.11.250:8765"), ("192.168.11.250", "8765"))
        self.assertEqual(split_host("nas"), ("nas", ""))


class LanHttpTests(unittest.TestCase):
    """Same request pipeline, but with a LAN-enabled policy behind a loopback socket."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / "state")
        self.storage.settings["outputRoot"] = str(self.root / "media")
        self.app = Application(self.storage, dist=self.root / "ui")

    def tearDown(self):
        self.app.tasks.close()
        self.temp.cleanup()

    def serve(self, policy):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app, policy))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        thread.start()
        return server, thread

    def request(self, server, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_lan_host_header_serves_ui_and_api(self):
        server, thread = self.serve(AccessPolicy(lan=True, cidrs=["127.0.0.0/8", "192.168.11.0/24"]))
        try:
            (self.root / "ui").mkdir(parents=True, exist_ok=True)
            (self.root / "ui" / "index.html").write_text("<html>ui</html>", encoding="utf-8")
            status, body = self.request(server, "/", {"Host": f"192.168.11.250:{server.server_port}"})
            self.assertEqual(status, 200)
            self.assertIn(b"<html>ui</html>", body)
            status, body = self.request(server, "/api/state", {"Host": f"192.168.11.250:{server.server_port}"})
            self.assertEqual(status, 200)
            json.loads(body)
            status, _ = self.request(server, "/api/state", {"Host": "attacker.invalid"})
            self.assertEqual(status, 403)
        finally:
            server.shutdown(); thread.join(5); server.server_close()

    def test_lan_host_header_rejected_without_opt_in(self):
        server, thread = self.serve(AccessPolicy())
        try:
            status, _ = self.request(server, "/api/state", {"Host": f"192.168.11.250:{server.server_port}"})
            self.assertEqual(status, 403)
        finally:
            server.shutdown(); thread.join(5); server.server_close()

    def test_cross_origin_from_lan_page_is_allowed_for_same_host(self):
        server, thread = self.serve(AccessPolicy(lan=True, cidrs=["127.0.0.0/8", "192.168.11.0/24"]))
        try:
            headers = {"Host": f"192.168.11.250:{server.server_port}", "Origin": f"http://192.168.11.250:{server.server_port}"}
            self.assertEqual(self.request(server, "/api/state", headers)[0], 200)
            headers = {"Host": f"192.168.11.250:{server.server_port}", "Origin": "http://192.168.11.77:9999"}
            self.assertEqual(self.request(server, "/api/state", headers)[0], 403)
        finally:
            server.shutdown(); thread.join(5); server.server_close()


class ProxyTestEndpointTests(unittest.TestCase):
    """/api/proxy/test validates input and never leaks credentials."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / "state")
        self.storage.settings["outputRoot"] = str(self.root / "media")
        self.app = Application(self.storage, dist=self.root / "ui")

    def tearDown(self):
        self.app.tasks.close()
        self.temp.cleanup()

    def test_blank_and_invalid_urls_return_error(self):
        result = self.app.test_proxy({"proxyUrl": "   "})
        self.assertFalse(result["ok"])
        self.assertIn("代理地址", result["error"])
        result = self.app.test_proxy({"proxyUrl": "ftp://x:21"})
        self.assertFalse(result["ok"])

    def test_unreachable_proxy_reports_failure_without_leaking_password(self):
        closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()
        result = self.app.test_proxy({"proxyUrl": f"http://user:secretpw@127.0.0.1:{port}"})
        self.assertFalse(result["ok"])
        self.assertIn("***", result["proxy"])
        self.assertNotIn("secretpw", json.dumps(result, ensure_ascii=False))

    def test_body_without_url_falls_back_to_saved_settings(self):
        self.storage.save_settings({**self.storage.settings,
                                    "proxyEnabled": True, "proxyUrl": "http://127.0.0.1:9"})
        result = self.app.test_proxy({})
        self.assertFalse(result["ok"])
        self.assertIn("127.0.0.1:9", result["proxy"])


class BrowserHintTests(unittest.TestCase):
    def test_playwright_missing_message_gets_actionable_hint(self):
        raw = ("BrowserType.launch: Executable doesn't exist at "
               "/someone/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell")
        hinted = with_browser_hint(raw)
        self.assertTrue(hinted.startswith(raw))
        self.assertIn("playwright install chromium", hinted)
        self.assertIn("ms-playwright", hinted)

    def test_other_errors_pass_through(self):
        self.assertEqual(with_browser_hint("网络超时"), "网络超时")
        self.assertEqual(with_browser_hint(""), "")


if __name__ == "__main__":
    unittest.main()
