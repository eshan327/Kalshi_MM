#!/bin/bash
# Installation script for Kalshi WebSocket Dashboard

echo "Installing dependencies from requirements.txt..."

# Try different installation methods
if pip install --user -r requirements.txt 2>/dev/null; then
    echo "✅ Successfully installed with --user flag"
elif pip install --break-system-packages -r requirements.txt 2>/dev/null; then
    echo "✅ Successfully installed with --break-system-packages flag"
else
    echo "❌ Installation failed. Trying with virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "✅ Successfully installed in virtual environment"
    echo "⚠️  Remember to activate the virtual environment before running:"
    echo "   source venv/bin/activate"
fi

echo ""
echo "Installation complete! Run the app with:"
echo "  python3 app.py"
echo ""
echo "Or if using virtual environment:"
echo "  source venv/bin/activate && python3 app.py"

