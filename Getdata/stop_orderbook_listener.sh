#!/bin/bash

# Stop script for OrderBookListener
# Usage: ./stop_orderbook_listener.sh [market_id]
# If market_id is not provided, stops all running listeners

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -n "$1" ]; then
    # Stop specific market listener
    MARKET_ID="$1"
    SAFE_MARKET_ID=$(echo "$MARKET_ID" | sed 's/[\/\\]/_/g')
    PID_FILE="$PROJECT_ROOT/logs/orderbook_listener_${SAFE_MARKET_ID}.pid"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping OrderBookListener for $MARKET_ID (PID: $PID)..."
            kill "$PID"
            rm "$PID_FILE"
            echo "OrderBookListener stopped."
        else
            echo "OrderBookListener for $MARKET_ID is not running (stale PID file)."
            rm "$PID_FILE"
        fi
    else
        echo "No PID file found for market: $MARKET_ID"
    fi
else
    # Stop all listeners
    echo "Stopping all OrderBookListener instances..."
    for PID_FILE in "$PROJECT_ROOT"/logs/orderbook_listener_*.pid; do
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            MARKET_ID=$(basename "$PID_FILE" .pid | sed 's/orderbook_listener_//')
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Stopping listener for $MARKET_ID (PID: $PID)..."
                kill "$PID"
                rm "$PID_FILE"
            else
                echo "Removing stale PID file for $MARKET_ID"
                rm "$PID_FILE"
            fi
        fi
    done
    echo "All listeners stopped."
fi
