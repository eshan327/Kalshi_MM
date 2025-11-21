#!/bin/bash
# Script to install requirements.txt in the virtual environment

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing requirements from requirements.txt..."
pip install -r requirements.txt

echo "✅ Requirements installed successfully!"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source venv/bin/activate"


