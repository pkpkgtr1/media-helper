"""Docker 构建文件的静态检查。

这台机器上没有可用的 Docker 守护进程，所以只能校验"一定会让镜像起不来"的
结构性问题 —— 尤其是入口脚本的可读位：源文件是 600 时 `chmod +x` 只得到 711，
以非 root 用户跑 `/bin/sh 脚本` 会报 `cannot open ...: Permission denied`。
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DockerfileTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.lines = [line.strip() for line in self.text.splitlines()]

    def instructions(self, name):
        return [line for line in self.lines if line.upper().startswith(name.upper())]

    def test_entrypoint_does_not_need_the_executable_bit(self):
        entry = self.instructions("ENTRYPOINT")
        self.assertEqual(len(entry), 1, entry)
        self.assertRegex(entry[0], r'\["/bin/sh",\s*"/usr/local/bin/entrypoint\.sh"\]')

    def test_entrypoint_is_readable_for_everyone(self):
        # chmod +x 会把 600 变成 711，其他人能执行却读不到 —— 必须显式 755。
        self.assertIn("chmod 755 /usr/local/bin/entrypoint.sh", self.text)
        self.assertNotRegex(self.text, r"chmod \+x\s+/usr/local/bin/entrypoint\.sh")

    def test_application_tree_is_readable(self):
        self.assertIn("chmod -R a+rX /app", self.text)

    def test_runs_as_non_root_after_permissions_are_set(self):
        user = self.instructions("USER")
        self.assertEqual([line.upper() for line in user], ["USER APP"])
        # USER 必须在 chmod / chown 之后，否则改不动目录。
        self.assertGreater(self.lines.index("USER app"),
                           self.lines.index("RUN chmod 755 /usr/local/bin/entrypoint.sh \\"))

    def test_builds_frontend_in_a_separate_stage(self):
        self.assertIn("FROM node:22-alpine AS web", self.text)
        self.assertIn("FROM python:3.12-slim AS runtime", self.text)
        self.assertIn("COPY --from=web /build/web/dist ./web/dist", self.text)

    def test_copies_only_existing_paths(self):
        for line in self.instructions("COPY"):
            if "--from" in line:
                continue
            parts = line.split()[1:]
            for source in parts[:-1]:
                self.assertTrue((ROOT / source).exists(), f"{line} -> 缺少 {source}")


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "docker" / "entrypoint.sh"
        self.text = self.path.read_text(encoding="utf-8")

    def test_repository_file_is_readable_and_executable(self):
        mode = os.stat(self.path).st_mode
        self.assertTrue(mode & stat.S_IROTH, "入口脚本必须对其他用户可读")
        self.assertTrue(mode & stat.S_IXUSR)

    def test_uses_posix_shell(self):
        self.assertTrue(self.text.startswith("#!/bin/sh"))
        self.assertNotIn("/bin/bash", self.text)

    def test_passes_through_extra_arguments(self):
        # 额外参数追加在最后，argparse 取最后一个值，所以能覆盖默认端口等。
        self.assertIn('exec python -m media_helper "$@"', self.text)
        self.assertIn('set -- --port "${MEDIA_PORT:-8766}" "$@"', self.text)

    def test_refuses_to_start_on_unwritable_directories(self):
        self.assertIn('if [ ! -w "$dir" ]', self.text)
        self.assertIn("exit 1", self.text)


class DockerignoreTests(unittest.TestCase):
    def setUp(self):
        self.patterns = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split())

    def test_excludes_state_and_dependencies(self):
        for expected in ("config/", "media/", "web/node_modules/", "web/dist/", ".venv/"):
            self.assertIn(expected, self.patterns)

    def test_keeps_files_the_build_needs(self):
        # 构建要用的清单和源码不能被排除。
        for needed in ("web/package.json", "web/pnpm-lock.yaml", "requirements.txt", "media_helper/"):
            self.assertNotIn(needed, self.patterns)
            self.assertNotIn(needed.rstrip("/"), self.patterns)


if __name__ == "__main__":
    unittest.main()
