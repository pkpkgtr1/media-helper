"""一键启动：必要时准备依赖、构建前端，然后运行本地服务。

依赖装在项目内的 .venv；缺失时自动创建并按 requirements.txt 安装。这样项目目录
改名或搬到别处后，脚本不会再去猜旧路径下的虚拟环境。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
VENV = ROOT / ".venv"
DEFAULT_PORT = 8766
REQUIRED = ("requests", "bs4", "lxml", "PIL", "cryptography")
LOOPBACK = ("", "127.0.0.1", "localhost", "::1")


def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def has_dependencies(python):
    probe = subprocess.run([str(python), "-c", f"import {','.join(REQUIRED)}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    return probe.returncode == 0


def ensure_dependencies():
    """保证 .venv 存在且依赖齐全；返回需要切换过去的解释器，当前解释器已可用则返回 None。

    注意：.venv/bin/python 通常是指向系统 python 的软链接，所以不能用 resolve()
    比较两个解释器是否相同——必须实际探测导入能力，否则会误判为“已经就绪”。
    """
    if has_dependencies(sys.executable):
        return None
    target = venv_python()
    if not target.exists():
        print("创建虚拟环境 .venv…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    if not has_dependencies(target):
        print("安装依赖…", flush=True)
        subprocess.run([str(target), "-m", "pip", "install", "--upgrade", "pip"],
                       stdout=subprocess.DEVNULL, check=False)
        subprocess.run([str(target), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    if not has_dependencies(target):
        raise RuntimeError("依赖安装后仍无法导入，请检查 requirements.txt 与网络")
    return target


def run_frontend(arguments):
    executable = shutil.which("pnpm")
    if not executable:
        raise RuntimeError("未找到 pnpm，请先安装 Node.js 并执行 npm install -g pnpm")
    # 固定可执行文件路径，命令参数不来自用户输入。
    subprocess.run([executable, *arguments], cwd=WEB, check=True)


def frontend_stale():
    output = WEB / "dist" / "index.html"
    if not output.exists():
        return True
    sources = [WEB / "package.json", WEB / "vite.config.ts", WEB / "index.html",
               *(path for path in (WEB / "src").rglob("*") if path.is_file())]
    return any(path.stat().st_mtime > output.stat().st_mtime for path in sources)


def build_frontend():
    if not (WEB / "node_modules" / "vite").exists():
        print("安装界面依赖…", flush=True)
        run_frontend(["install"])
    if frontend_stale():
        print("构建界面…", flush=True)
        run_frontend(["run", "build"])


LAN_FLAGS = ("--host", "--lan", "--allow-lan")


def listen_args(argv):
    """默认对整个局域网开放；想只留给本机时加 --local-only。

    只监听回环时其他设备根本连不上，所以这里在没有显式给定监听相关参数时
    补上 `--host 0.0.0.0 --lan`，来源仍受 server 的网段白名单约束。
    """
    if "--local-only" in argv:
        rest = [value for value in argv if value != "--local-only"]
        return [*rest, "--host", "127.0.0.1"]
    if any(flag in argv for flag in LAN_FLAGS) or os.environ.get("MEDIA_HOST"):
        return list(argv)
    return [*argv, "--host", "0.0.0.0", "--lan"]


def port_of(argv):
    for index, flag in enumerate(argv):
        if flag.startswith("--port="):
            return flag.split("=", 1)[1]
        if flag == "--port" and index + 1 < len(argv):
            return argv[index + 1]
    return os.environ.get("MEDIA_PORT", str(DEFAULT_PORT))


def already_running(argv):
    """已启动时直接打开浏览器，不再抢端口。"""
    if "--state-dir" in argv:  # 测试实例不参与探测
        return False
    port = port_of(argv)
    url = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(url + "/api/bootstrap", timeout=1) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        # 设了登录密码时 /api/bootstrap 会返回 401；能应答就说明服务已经在跑。
        if exc.code != 401:
            return False
        data = {"settings": {}}
    except (OSError, ValueError):
        return False
    if "settings" not in data:
        return False
    if "--no-browser" not in argv:
        webbrowser.open(url)
    print(f"媒体下载助手已在运行：{url}")
    return True


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if sys.version_info < (3, 11):
        raise RuntimeError("需要 Python 3.11 或更高版本")
    replacement = ensure_dependencies()
    if replacement is not None:
        raise SystemExit(subprocess.call([str(replacement), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT))
    if already_running(sys.argv[1:]):
        return
    build_frontend()
    dist = ROOT / "web" / "dist" / "index.html"
    if not dist.exists():  # 构建被跳过或失败时给出明确原因，而不是等到页面 404
        raise RuntimeError(f"界面未生成，请检查 pnpm 构建日志：{dist}")
    from media_helper.server import main as serve

    # 监听参数通过 argv 交给 media_helper.server 的 argparse。
    sys.argv = [sys.argv[0], *listen_args(sys.argv[1:])]
    serve()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - 启动失败要给出可读原因
        print(f"启动失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
