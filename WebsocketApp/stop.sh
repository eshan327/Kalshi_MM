#!/bin/bash
# Script to stop the Kalshi WebSocket Dashboard

echo "Stopping Kalshi WebSocket Dashboard..."

# Find and kill app.py processes
PIDS=$(ps aux | grep "[p]ython.*app.py" | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "No running app.py processes found"
else
    for PID in $PIDS; do
        echo "Stopping process $PID..."
        kill $PID 2>/dev/null
    done
    echo "Stopped all app.py processes"
fi

# Also check for processes on common ports
for port in 5000 5001 5002 5003 5004 5005; do
    PID=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$PID" ]; then
        echo "Stopping process on port $port (PID: $PID)..."
        kill $PID 2>/dev/null
    fi
done

echo "Done!"

