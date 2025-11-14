#!/bin/bash

# Status check script for OrderBookListener
# Shows if listeners are running and recent activity

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "OrderBook Listener Status Check"
echo "================================"
echo ""

# Check for PID files
PID_FILES=$(ls logs/orderbook_listener_*.pid 2>/dev/null)

if [ -z "$PID_FILES" ]; then
    echo "❌ No orderbook listeners are running (no PID files found)"
    exit 0
fi

# Check each listener
for PID_FILE in $PID_FILES; do
    PID=$(cat "$PID_FILE" 2>/dev/null)
    MARKET_ID=$(basename "$PID_FILE" .pid | sed 's/orderbook_listener_//')
    
    if [ -z "$PID" ]; then
        continue
    fi
    
    echo "Market: $MARKET_ID"
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "  Status: ✅ RUNNING (PID: $PID)"
        
        # Get latest log file
        LATEST_LOG=$(ls -t logs/orderbook_listener_${MARKET_ID}_*.log 2>/dev/null | head -1)
        if [ -n "$LATEST_LOG" ]; then
            LAST_ENTRY=$(tail -1 "$LATEST_LOG" 2>/dev/null)
            if [ -n "$LAST_ENTRY" ] && [ "$LAST_ENTRY" != "" ]; then
                echo "  Last log: $(echo "$LAST_ENTRY" | cut -c1-80)..."
            fi
        fi
        
        # Check orderbook file
        SAFE_MARKET_ID=$(echo "$MARKET_ID" | sed 's/[\/\\]/_/g')
        ORDERBOOK_FILE="data/orderbookData/orderBook_${SAFE_MARKET_ID}.json"
        if [ -f "$ORDERBOOK_FILE" ]; then
            FILE_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$ORDERBOOK_FILE" 2>/dev/null || stat -c "%y" "$ORDERBOOK_FILE" 2>/dev/null | cut -d'.' -f1)
            echo "  Orderbook file: $ORDERBOOK_FILE (updated: $FILE_TIME)"
        else
            echo "  Orderbook file: Not found yet"
        fi
    else
        echo "  Status: ❌ NOT RUNNING (stale PID file)"
    fi
    echo ""
done

