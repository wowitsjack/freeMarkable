#!/bin/bash
# freeMarkable (Linux/Mac)
# Easy launcher script for freeMarkable

echo "======================================================"
echo "                freeMarkable"
echo "======================================================"
echo ""
echo "Starting freeMarkable..."
echo ""

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
RESOURCES_DIR="$DIR/resources"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed or not in PATH"
    echo "Please install Python 3 and try again."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if resources directory exists
if [ ! -d "$RESOURCES_DIR" ]; then
    echo "ERROR: Resources directory not found at $RESOURCES_DIR"
    echo "Please make sure the resources folder is in the same directory as this launcher script."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if main.py exists in resources
if [ ! -f "$RESOURCES_DIR/main.py" ]; then
    echo "ERROR: main.py not found in resources directory"
    echo "Please make sure all application files are in the resources folder."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Install requirements if needed
if [ -f "$RESOURCES_DIR/requirements.txt" ]; then
    echo "Installing Python dependencies..."
    python3 -m pip install -r "$RESOURCES_DIR/requirements.txt" 
    echo ""
fi

# Change to resources directory and run the Python application
cd "$RESOURCES_DIR"
python3 main.py

# Check exit status
if [ $? -eq 0 ]; then
    echo ""
    echo "Application closed successfully."
else
    echo ""
    echo "Application exited with an error."
    read -p "Press Enter to exit..."
fi