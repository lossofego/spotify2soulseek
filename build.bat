@echo off
echo ========================================
echo   Building spotify2slsk executable
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    echo Install from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install/upgrade build dependencies
echo Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m pip install -r requirements.txt

:: Install tray and notification packages (will be bundled into exe)
echo.
echo Installing system tray and notification support...
python -m pip install pystray pillow plyer

:: Install cryptography for HTTPS callback server
echo Installing cryptography for Spotify OAuth...
python -m pip install cryptography

:: Clean previous builds
echo.
echo Cleaning previous builds...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

:: Build
echo.
echo Building executable...
python -m PyInstaller spotify2slsk.spec --clean

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable location:
echo   dist\spotify2slsk.exe
echo.
echo File size:
for %%A in (dist\spotify2slsk.exe) do echo   %%~zA bytes
echo.
echo Bundled features:
echo   [x] Spotify OAuth login
echo   [x] Soulseek auto-registration  
echo   [x] System tray icon
echo   [x] Desktop notifications
echo.

:: Copy to release folder
mkdir release 2>nul
copy dist\spotify2slsk.exe release\
echo Copied to release\spotify2slsk.exe
echo.

pause
