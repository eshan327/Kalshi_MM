#!/bin/bash

# Script to run orderbook listeners for multiple markets from a file
# Usage: ./run_multiple_listeners.sh <markets_file> [interval_minutes] [--demo]
#
# The markets file should contain one market ID per line, for example:
#   KXNBASPREAD-25NOV05BKNIND-IND12
#   KXMLBGAME-25OCT31LADTOR-LAD
#   KXNHLSPREAD-25NOV01CARBOS-BOS1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Check if markets file is provided
if [ -z "$1" ]; then
    echo "Error: Markets file is required"
    echo "Usage: $0 <markets_file> [interval_minutes] [--demo]"
    echo ""
    echo "Example:"
    echo "  $0 markets.txt 5"
    echo "  $0 markets.txt 5 --demo"
    echo ""
    echo "The markets file should contain one market ID per line:"
    echo "  KXNBASPREAD-25NOV05BKNIND-IND12"
    echo "  KXMLBGAME-25OCT31LADTOR-LAD"
    echo "  KXNHLSPREAD-25NOV01CARBOS-BOS1"
    exit 1
fi

MARKETS_FILE="$1"
INTERVAL="${2:-5}"  # Default to 5 minutes if not provided
DEMO_FLAG=""
if [ "$3" == "--demo" ]; then
    DEMO_FLAG="--demo"
fi

# Check if markets file exists
if [ ! -f "$MARKETS_FILE" ]; then
    echo "Error: Markets file not found: $MARKETS_FILE"
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run from project root."
    exit 1
fi

source venv/bin/activate

# Read market IDs from file (ignore empty lines and comments starting with #)
MARKET_COUNT=0
PIDS=()

echo "=========================================="
echo "Starting OrderBook Listeners"
echo "=========================================="
echo "Markets file: $MARKETS_FILE"
echo "Interval: $INTERVAL minutes"
echo "Environment: $([ -n "$DEMO_FLAG" ] && echo "DEMO" || echo "PRODUCTION")"
echo ""

# Read each market ID and start listener
while IFS= read -r market_id || [ -n "$market_id" ]; do
    # Skip empty lines and comments
    market_id=$(echo "$market_id" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [ -z "$market_id" ] || [[ "$market_id" =~ ^# ]]; then
        continue
    fi
    
    MARKET_COUNT=$((MARKET_COUNT + 1))
    echo "[$MARKET_COUNT] Starting listener for: $market_id"
    
    # Use the existing run_orderbook_listener.sh script
    if [ -n "$DEMO_FLAG" ]; then
        "$SCRIPT_DIR/run_orderbook_listener.sh" "$market_id" "$INTERVAL" "$DEMO_FLAG" > /dev/null 2>&1
    else
        "$SCRIPT_DIR/run_orderbook_listener.sh" "$market_id" "$INTERVAL" > /dev/null 2>&1
    fi
    
    # Get the PID from the PID file
    SAFE_MARKET_ID=$(echo "$market_id" | sed 's/[\/\\]/_/g')
    PID_FILE="$PROJECT_ROOT/logs/orderbook_listener_${SAFE_MARKET_ID}.pid"
    
    # Wait a moment for the process to start
    sleep 1
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            PIDS+=("$PID")
            echo "  ✓ Started (PID: $PID)"
        else
            echo "  ✗ Failed to start"
        fi
    else
        echo "  ✗ Failed to start (PID file not created)"
    fi
    
    # Small delay between starting listeners to avoid overwhelming the system
    sleep 0.5
    
done < "$MARKETS_FILE"

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Total markets processed: $MARKET_COUNT"
echo "Active listeners: ${#PIDS[@]}"
echo ""

if [ ${#PIDS[@]} -gt 0 ]; then
    echo "Active PIDs: ${PIDS[*]}"
    echo ""
    echo "To monitor logs, use:"
    echo "  tail -f logs/orderbook_listener_<MARKET_ID>_*.log"
    echo ""
    echo "To stop all listeners, use:"
    echo "  ./Getdata/stop_all_listeners.sh"
    echo ""
    echo "Or to stop individual markets:"
    echo "  ./Getdata/stop_orderbook_listener.sh <MARKET_ID>"
    echo ""
    echo "All listeners are running in the background and will continue"
    echo "even if you close this terminal."
fi






