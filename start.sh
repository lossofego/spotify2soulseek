#!/bin/bash

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found!"
    echo "Install with: sudo apt install python3 python3-pip"
    exit 1
fi

# Install dependencies if needed
python3 -c "import rich" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt --quiet
fi

# Run
python3 downloader.py
