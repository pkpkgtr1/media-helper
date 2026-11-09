@echo off
chcp 65001
echo Checking system environment......

:: 1. Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Node.js is not installed!
    echo Please install Node.js from: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

:: 2. Check pnpm
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] pnpm is not installed!
    echo Please run: npm install -g pnpm
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js and pnpm are ready.
echo Starting python start.py ...
echo ----------------------------------------

python start.py

pause