#!/bin/bash

# Launch script for OrderBookListener
# Runs the orderbook listener in the background for a specific market
# Usage: ./run_orderbook_listener.sh <market_id> [interval_minutes]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Check if market ID is provided
if [ -z "$1" ]; then
    echo "Error: Market ID is required"
    echo "Usage: $0 <market_id> [interval_minutes] [--demo]"
    echo "Example: $0 KXNHLSPREAD-25NOV01CARBOS-BOS1 5"
    exit 1
fi

MARKET_ID="$1"
INTERVAL="${2:-5}"  # Default to 5 minutes if not provided
DEMO_FLAG=""
if [ "$3" == "--demo" ]; then
    DEMO_FLAG="--demo"
fi

# Activate virtual environment
source venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

# Sanitize market ID for filenames
SAFE_MARKET_ID=$(echo "$MARKET_ID" | sed 's/[\/\\]/_/g')

# Log file with timestamp and market ID
LOG_FILE="$PROJECT_ROOT/logs/orderbook_listener_${SAFE_MARKET_ID}_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="$PROJECT_ROOT/logs/orderbook_listener_${SAFE_MARKET_ID}.pid"

# Function to stop existing listener for this market
stop_listener() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "Stopping existing listener for $MARKET_ID (PID: $OLD_PID)..."
            kill "$OLD_PID"
            rm "$PID_FILE"
            sleep 2
        else
            rm "$PID_FILE"
        fi
    fi
}

# Stop any existing listener for this market
stop_listener

# Start the listener in the background with caffeinate to prevent sleep
echo "Starting OrderBookListener for market: $MARKET_ID"
echo "Interval: $INTERVAL minutes"
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"

# Run with caffeinate to prevent sleep (even with closed lid), and nohup to keep running after terminal closes
# -i = prevent idle sleep
# -d = prevent display sleep (important when lid is closed)
# -m = prevent disk sleep
nohup caffeinate -i -d -m python Getdata/orderBookListener.py --market-id "$MARKET_ID" --interval "$INTERVAL" $DEMO_FLAG > "$LOG_FILE" 2>&1 &

# Save the PID
LISTENER_PID=$!
echo $LISTENER_PID > "$PID_FILE"

echo "OrderBookListener started with PID: $LISTENER_PID"
echo "To check logs: tail -f $LOG_FILE"
echo "To stop: kill $LISTENER_PID or run: ./stop_orderbook_listener.sh $MARKET_ID"
echo ""
echo "To run multiple markets simultaneously, run this script again with different market IDs!"
