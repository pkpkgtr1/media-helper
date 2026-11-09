@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用 python，其次 python3（部分安装只提供其中一个）。
where python >nul 2>nul
if %errorlevel%==0 (
    python start.py %*
    goto done
)
where python3 >nul 2>nul
if %errorlevel%==0 (
    python3 start.py %*
    goto done
)
echo 未找到 Python，请先安装 Python 3.11 或更高版本：https://www.python.org/downloads/
echo 安装时请勾选 "Add python.exe to PATH"。

:done
echo.
pause
