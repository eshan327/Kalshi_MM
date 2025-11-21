#!/bin/bash
# Script to run the Kalshi WebSocket Dashboard

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the app
python3 app.py

