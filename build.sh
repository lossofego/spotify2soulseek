#!/bin/bash
echo "========================================"
echo "  Building spotify2slsk executable"
echo "========================================"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found"
    exit 1
fi

# Install build dependencies
echo "Installing build dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller
python3 -m pip install -r requirements.txt

# Install tray and notification packages (will be bundled into exe)
echo
echo "Installing system tray and notification support..."
python3 -m pip install pystray pillow plyer

# Clean previous builds
echo
echo "Cleaning previous builds..."
rm -rf build dist

# Build
echo
echo "Building executable..."
python3 -m PyInstaller spotify2slsk.spec --clean

if [ $? -ne 0 ]; then
    echo
    echo "BUILD FAILED"
    exit 1
fi

echo
echo "========================================"
echo "  BUILD SUCCESSFUL!"
echo "========================================"
echo
echo "Executable location:"
echo "  dist/spotify2slsk"
echo
echo "File size:"
ls -lh dist/spotify2slsk | awk '{print "  " $5}'
echo
echo "Bundled features:"
echo "  [x] Spotify OAuth login"
echo "  [x] Soulseek auto-registration"
echo "  [x] System tray icon"
echo "  [x] Desktop notifications"
echo

# Copy to release folder
mkdir -p release
cp dist/spotify2slsk release/
echo "Copied to release/spotify2slsk"
