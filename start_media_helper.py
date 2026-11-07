"""Build if needed, then launch the local media UI with this Python runtime."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
UI = ROOT / "Design app interface"


def run_frontend(arguments):
    executable = shutil.which("pnpm")
    if not executable:
        raise RuntimeError("未找到 pnpm，请先安装 Node.js 并执行 npm install -g pnpm")
    # Resolve a fixed package-manager path; no command text is built from user input.
    subprocess.run([executable, *arguments], cwd=UI, check=True)


LOOPBACK_HOSTS = ("", "127.0.0.1", "localhost", "::1")


def requested_host(argv, default="127.0.0.1"):
    """Resolve the --host / MEDIA_HOST value a launch would use."""
    host = os.environ.get("MEDIA_HOST", "").strip() or default
    for index, flag in enumerate(argv):
        if flag.startswith("--host="):
            host = flag.split("=", 1)[1]
        elif flag == "--host" and index + 1 < len(argv):
            host = argv[index + 1]
    return host.strip()


def running_check_urls(argv):
    """URLs to probe for an existing instance, honouring a custom bind host."""
    hosts = ["127.0.0.1"]
    host = requested_host(argv, default="")
    if host and host not in LOOPBACK_HOSTS and host not in ("0.0.0.0", "::") and host not in hosts:
        hosts.append(host)
    return [f"http://{value}:8765" for value in hosts]


def wants_lan(argv):
    return any(flag in ("--lan", "--allow-lan") for flag in argv) or \
        os.environ.get("MEDIA_ALLOW_LAN", "").strip().lower() in ("1", "true", "yes", "on")


def warn_when_lan_requested_but_instance_is_loopback_only(argv):
    """An already-running loopback instance would silently ignore --lan."""
    if not wants_lan(argv):
        return
    if requested_host(argv, default="") in LOOPBACK_HOSTS:
        print("提示：当前实例仍只监听 127.0.0.1，局域网地址不可用。请先停止旧进程，"
              "再执行：./.venv/bin/python start_media_helper.py --host 0.0.0.0 --lan", flush=True)


def ensure_browser():
    """Install chromium into the project ms-playwright bundle when none is found.

    Runs on Windows and Linux alike after the venv re-exec, so a fresh clone
    only needs “双击 启动新界面.bat / ./启动新界面.sh”. A failed download is not
    fatal: the hanime crawler will report it later with the exact fix command.
    """
    from media_storage import browser_install_hint, find_browser_executable
    if find_browser_executable():
        return
    bundle = ROOT / "ms-playwright"
    print("未检测到浏览器组件，正在下载 Chromium 到项目内 ms-playwright/（约 150MB，可能需要代理）…", flush=True)
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(bundle))
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       cwd=ROOT, env=env, check=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"浏览器自动下载失败：{exc}", file=sys.stderr, flush=True)
        print("其他功能不受影响；hanime 任务需要浏览器，可稍后手动执行：", flush=True)
        print("  " + browser_install_hint(), flush=True)
        return
    if find_browser_executable([bundle]):
        print("浏览器组件已就绪：ms-playwright/", flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    if sys.version_info < (3, 11):
        raise RuntimeError("需要 Python 3.11 或更高版本")
    virtual_root = ROOT / ".venv"
    virtual_python = virtual_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if virtual_python.exists() and Path(sys.prefix).resolve() != virtual_root.resolve():
        try:
            probe = subprocess.run([str(virtual_python), "-c", "import requests,bs4,lxml,PIL,playwright,selenium,webdriver_manager"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if probe.returncode == 0:
                raise SystemExit(subprocess.call([str(virtual_python), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT))
        except (OSError, subprocess.TimeoutExpired):
            pass
    if "--port" not in sys.argv and "--state-dir" not in sys.argv:
        for candidate in running_check_urls(sys.argv):
            try:
                with urllib.request.urlopen(candidate + "/api/bootstrap", timeout=1) as response:
                    data = json.load(response)
            except (OSError, ValueError):
                continue
            if "settings" in data and "defaults" in data:
                if "--no-browser" not in sys.argv:
                    webbrowser.open(candidate)
                print("媒体下载助手已在运行：" + candidate)
                warn_when_lan_requested_but_instance_is_loopback_only(sys.argv)
                return
    ensure_browser()
    if not (UI / "node_modules" / "vite").exists():
        print("安装界面依赖…", flush=True)
        run_frontend(["install", "--frozen-lockfile"])
    output = UI / "dist" / "index.html"
    sources = [UI / "package.json", UI / "pnpm-lock.yaml", UI / "vite.config.ts", UI / "index.html", *list((UI / "src").rglob("*"))]
    if not output.exists() or any(p.is_file() and p.stat().st_mtime > output.stat().st_mtime for p in sources):
        print("检查并构建新界面…", flush=True)
        run_frontend(["run", "typecheck"])
        run_frontend(["run", "build"])
    from media_server import main as serve
    serve()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
