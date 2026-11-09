"""启动脚本：默认对局域网开放，显式参数优先，--local-only 可退回本机。"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import start  # noqa: E402


class ListenArgsTests(unittest.TestCase):
    def test_defaults_to_lan_wide_open(self):
        self.assertEqual(["--host", "0.0.0.0", "--lan"], start.listen_args([]))
        self.assertEqual(["--no-browser", "--host", "0.0.0.0", "--lan"],
                         start.listen_args(["--no-browser"]))

    def test_keeps_user_port_and_adds_listen_flags(self):
        self.assertEqual(["--port", "9000", "--host", "0.0.0.0", "--lan"],
                         start.listen_args(["--port", "9000"]))

    def test_explicit_listen_flags_are_untouched(self):
        argv = ["--host", "192.168.11.250", "--lan"]
        self.assertEqual(argv, start.listen_args(argv))

    def test_cidr_only_still_opens_a_listenable_address(self):
        # 只给白名单不给监听地址时，旧行为会绑回环导致局域网连不上。
        self.assertEqual(["--lan-cidr", "192.168.11.0/24", "--host", "0.0.0.0", "--lan"],
                         start.listen_args(["--lan-cidr", "192.168.11.0/24"]))

    def test_local_only_falls_back_to_loopback(self):
        self.assertEqual(["--no-browser", "--host", "127.0.0.1"],
                         start.listen_args(["--local-only", "--no-browser"]))

    def test_env_host_suppresses_defaults(self):
        with patch.dict(os.environ, {"MEDIA_HOST": "127.0.0.1"}):
            self.assertEqual(["--no-browser"], start.listen_args(["--no-browser"]))


class PortTests(unittest.TestCase):
    def test_port_from_flags_and_env(self):
        self.assertEqual("9001", start.port_of(["--port", "9001"]))
        self.assertEqual("9002", start.port_of(["--port=9002"]))
        self.assertEqual(str(start.DEFAULT_PORT), start.port_of([]))
        with patch.dict(os.environ, {"MEDIA_PORT": "9100"}):
            self.assertEqual("9100", start.port_of([]))


if __name__ == "__main__":
    unittest.main()
