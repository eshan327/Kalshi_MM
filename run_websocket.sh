#!/bin/bash

# Launch script for Kalshi WebSocket Streamer
# Runs the websocket streamer to receive real-time market data
# Usage: ./run_websocket.sh [--market-id MARKET_ID] [--market-ids MARKET1 MARKET2 ...] [--demo] [--background]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
MARKET_ID=""
MARKET_IDS=()
DEMO_FLAG=""
BACKGROUND=false
LOG_FILE=""
CHANNELS_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --market-id)
            MARKET_ID="$2"
            shift 2
            ;;
        --market-ids)
            shift
            while [[ $# -gt 0 ]] && [[ ! "$1" =~ ^-- ]]; do
                MARKET_IDS+=("$1")
                shift
            done
            ;;
        --demo)
            DEMO_FLAG="--demo"
            shift
            ;;
        --background)
            BACKGROUND=true
            shift
            ;;
        --channels)
            shift
            CHANNELS_FLAG="--channels"
            while [[ $# -gt 0 ]] && [[ ! "$1" =~ ^-- ]]; do
                CHANNELS_FLAG="$CHANNELS_FLAG $1"
                shift
            done
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--market-id MARKET_ID] [--market-ids MARKET1 MARKET2 ...] [--demo] [--background] [--channels CH1 CH2 ...]"
            exit 1
            ;;
    esac
done

# Check if at least one market is provided
if [ -z "$MARKET_ID" ] && [ ${#MARKET_IDS[@]} -eq 0 ]; then
    echo "Error: At least one market ID is required"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --market-id MARKET_ID      Single market ticker ID (e.g., KXMLBGAME-25OCT31LADTOR-LAD)"
    echo "  --market-ids MARKET1 ...   Multiple market ticker IDs"
    echo "  --demo                     Use demo environment instead of production"
    echo "  --background               Run in background (logs to file)"
    echo "  --channels CH1 CH2 ...    Channels to subscribe to (default: ticker orderbook_delta trade)"
    echo "                             Valid: ticker, orderbook_delta, trade, fill, position"
    echo ""
    echo "Examples:"
    echo "  $0 --market-id KXMLBGAME-25OCT31LADTOR-LAD"
    echo "  $0 --market-ids KXMLBGAME-25OCT31LADTOR-LAD KXNHLSPREAD-25NOV01CARBOS-BOS1"
    echo "  $0 --market-id KXMLBGAME-25OCT31LADTOR-LAD --demo"
    echo "  $0 --market-id KXMLBGAME-25OCT31LADTOR-LAD --channels fill position"
    echo "  $0 --market-ids MARKET1 MARKET2 --background"
    exit 1
fi

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Warning: Virtual environment not found at venv/bin/activate"
    echo "Continuing without virtual environment..."
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Build Python command
PYTHON_CMD="python Websocket/market_streamer.py"

if [ -n "$MARKET_ID" ]; then
    PYTHON_CMD="$PYTHON_CMD --market-id $MARKET_ID"
elif [ ${#MARKET_IDS[@]} -gt 0 ]; then
    PYTHON_CMD="$PYTHON_CMD --market-ids ${MARKET_IDS[*]}"
fi

if [ -n "$DEMO_FLAG" ]; then
    PYTHON_CMD="$PYTHON_CMD $DEMO_FLAG"
fi

if [ -n "$CHANNELS_FLAG" ]; then
    PYTHON_CMD="$PYTHON_CMD $CHANNELS_FLAG"
fi

# If running in background, set up logging
if [ "$BACKGROUND" = true ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    if [ -n "$MARKET_ID" ]; then
        SAFE_MARKET_ID=$(echo "$MARKET_ID" | sed 's/[\/\\]/_/g')
        LOG_FILE="$PROJECT_ROOT/logs/websocket_${SAFE_MARKET_ID}_${TIMESTAMP}.log"
        PID_FILE="$PROJECT_ROOT/logs/websocket_${SAFE_MARKET_ID}.pid"
    else
        LOG_FILE="$PROJECT_ROOT/logs/websocket_multiple_${TIMESTAMP}.log"
        PID_FILE="$PROJECT_ROOT/logs/websocket_multiple.pid"
    fi
    
    # Stop existing websocket if running
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "Stopping existing websocket (PID: $OLD_PID)..."
            kill "$OLD_PID" 2>/dev/null
            sleep 2
        fi
        rm -f "$PID_FILE"
    fi
    
    echo "Starting WebSocket streamer in background..."
    echo "Log file: $LOG_FILE"
    echo "PID file: $PID_FILE"
    
    # Run with caffeinate to prevent sleep (macOS)
    nohup caffeinate -i -d -m $PYTHON_CMD > "$LOG_FILE" 2>&1 &
    
    WS_PID=$!
    echo $WS_PID > "$PID_FILE"
    echo "WebSocket streamer started with PID: $WS_PID"
    echo "To check logs: tail -f $LOG_FILE"
    echo "To stop: ./stop_websocket.sh${MARKET_ID:+ $MARKET_ID}"
else
    # Run in foreground
    echo "Starting WebSocket streamer..."
    echo "Press Ctrl+C to stop"
    echo ""
    $PYTHON_CMD
fi

