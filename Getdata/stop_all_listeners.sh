#!/bin/bash

# Script to stop all running orderbook listeners
# Usage: ./stop_all_listeners.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Stopping all orderbook listeners..."

# Find all PID files
PID_FILES=$(find "$PROJECT_ROOT/logs" -name "orderbook_listener_*.pid" 2>/dev/null)

if [ -z "$PID_FILES" ]; then
    echo "No active listeners found."
    exit 0
fi

STOPPED_COUNT=0
for PID_FILE in $PID_FILES; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        MARKET_ID=$(basename "$PID_FILE" .pid | sed 's/orderbook_listener_//' | sed 's/_/ /')
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping listener (PID: $PID) for market: $MARKET_ID"
            kill "$PID" 2>/dev/null
            STOPPED_COUNT=$((STOPPED_COUNT + 1))
        fi
        
        # Remove PID file
        rm -f "$PID_FILE"
    fi
done

echo ""
if [ $STOPPED_COUNT -gt 0 ]; then
    echo "Stopped $STOPPED_COUNT listener(s)."
else
    echo "No active listeners were running."
fi





