#!/bin/bash

# freeMarkable macOS Launcher
# Double-click this file to launch freeMarkable on macOS

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Make sure we're in the right directory
if [ ! -f "resources/main.py" ]; then
    echo "Error: Could not find freeMarkable application files."
    echo "Make sure this script is in the freeMarkable directory."
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed or not in PATH."
    echo "Please install Python 3 from https://python.org or via Homebrew:"
    echo "  brew install python3"
    read -p "Press Enter to exit..."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)
MAJOR_VERSION=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR_VERSION=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR_VERSION" -lt 3 ] || ([ "$MAJOR_VERSION" -eq 3 ] && [ "$MINOR_VERSION" -lt 6 ]); then
    echo "Python 3.6 or higher is required. Found Python $PYTHON_VERSION"
    echo "Please upgrade your Python installation."
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Found Python $PYTHON_VERSION - OK"

# Install/upgrade pip if needed
echo "Ensuring pip is available..."
python3 -m pip --version &> /dev/null
if [ $? -ne 0 ]; then
    echo "Installing pip..."
    python3 -m ensurepip --default-pip
fi

# Install required packages
echo "Installing required Python packages..."
python3 -m pip install -q --user -r resources/requirements.txt

# Launch the application
echo "Starting freeMarkable..."
echo "=========================="
cd resources
python3 main.py

# Keep terminal open if there was an error
if [ $? -ne 0 ]; then
    echo ""
    echo "freeMarkable exited with an error."
    read -p "Press Enter to close this window..."
fi