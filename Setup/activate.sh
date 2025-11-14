#!/bin/bash
# Activation script for the Kalshi MM virtual environment

echo "Activating Kalshi MM virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated!"
echo "✓ kalshi-python and all dependencies are available"
echo ""
echo "You can now run:"
echo "  python getData.py --help"
echo "  python main.py"
echo "  python scraper3.py"
echo ""
echo "To deactivate, run: deactivate"
