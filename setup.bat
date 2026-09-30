@echo off
title KemetLab Automated Team Setup
echo ==========================================================
echo          KemetLab - Automated Team Setup Engine
echo ==========================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [*] Creating isolated virtual environment (.venv)...
    python -m venv .venv
) else (
    echo [OK] Virtual environment (.venv) already exists.
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip
if exist "requirements.txt" (
    pip install -r requirements.txt
)

echo [*] Running system sanity tests...
python -m unittest tests/test_local_runtime.py

echo.
echo ==========================================================
echo    KemetLab setup complete!
echo    To run experiments:
echo      python launch.py my_run --task task-smoke-local --run
echo ==========================================================
pause
