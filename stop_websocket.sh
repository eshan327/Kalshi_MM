#!/bin/bash

# Stop script for WebSocket Streamer
# Usage: ./stop_websocket.sh [market_id]
# If market_id is not provided, stops all running websockets

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"
cd "$PROJECT_ROOT"

if [ -n "$1" ]; then
    # Stop specific market websocket
    MARKET_ID="$1"
    SAFE_MARKET_ID=$(echo "$MARKET_ID" | sed 's/[\/\\]/_/g')
    PID_FILE="$PROJECT_ROOT/logs/websocket_${SAFE_MARKET_ID}.pid"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping WebSocket streamer for $MARKET_ID (PID: $PID)..."
            kill "$PID" 2>/dev/null
            sleep 1
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Force killing process..."
                kill -9 "$PID" 2>/dev/null
            fi
            rm -f "$PID_FILE"
            echo "WebSocket streamer stopped."
        else
            echo "WebSocket streamer for $MARKET_ID is not running (stale PID file)."
            rm -f "$PID_FILE"
        fi
    else
        echo "No PID file found for market: $MARKET_ID"
        echo "Trying to find and kill by process name..."
        # Try to find by process name
        pkill -f "websocket/market_streamer.py.*--market-id $MARKET_ID" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Killed websocket process for $MARKET_ID"
        else
            echo "No running websocket found for $MARKET_ID"
        fi
    fi
else
    # Stop all websockets
    echo "Stopping all WebSocket streamer instances..."
    STOPPED_COUNT=0
    
    # Stop by PID files
    for PID_FILE in "$PROJECT_ROOT"/logs/websocket_*.pid; do
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                MARKET_ID=$(basename "$PID_FILE" .pid | sed 's/websocket_//')
                echo "Stopping websocket for $MARKET_ID (PID: $PID)..."
                kill "$PID" 2>/dev/null
                sleep 1
                # Force kill if still running
                if ps -p "$PID" > /dev/null 2>&1; then
                    kill -9 "$PID" 2>/dev/null
                fi
                STOPPED_COUNT=$((STOPPED_COUNT + 1))
            fi
            rm -f "$PID_FILE"
        fi
    done
    
    # Also try to kill any remaining websocket processes
    pkill -f "websocket/market_streamer.py" 2>/dev/null
    if [ $? -eq 0 ]; then
        STOPPED_COUNT=$((STOPPED_COUNT + 1))
    fi
    
    if [ $STOPPED_COUNT -gt 0 ]; then
        echo "Stopped $STOPPED_COUNT websocket(s)."
    else
        echo "No active websockets were running."
    fi
fi

