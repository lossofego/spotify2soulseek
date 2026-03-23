@echo off
title spotify2slsk

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found!
    echo Download from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

:: Install dependencies if needed
python -c "import rich" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt --quiet
)

:: Run
python downloader.py
pause
