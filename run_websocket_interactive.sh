#!/bin/bash

# Launch script for Interactive WebSocket Streamer
# Allows subscribing/unsubscribing to channels while websocket is running
# Usage: ./run_websocket_interactive.sh [--market-id MARKET_ID] [--market-ids MARKET1 MARKET2 ...] [--demo] [--channels CH1 CH2 ...]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
MARKET_ID=""
MARKET_IDS=()
DEMO_FLAG=""
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
            echo "Usage: $0 [--market-id MARKET_ID] [--market-ids MARKET1 MARKET2 ...] [--demo] [--channels CH1 CH2 ...]"
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
    echo "  --channels CH1 CH2 ...    Initial channels to subscribe to (default: ticker orderbook_delta trade)"
    echo ""
    echo "Examples:"
    echo "  $0 --market-id KXMLBGAME-25OCT31LADTOR-LAD"
    echo "  $0 --market-id KXMLBGAME-25OCT31LADTOR-LAD --channels fill position"
    echo ""
    echo "Once running, you can use commands like:"
    echo "  subscribe <market_id> <channel1> [channel2] ..."
    echo "  unsubscribe <market_id> [channel1] [channel2] ..."
    echo "  list"
    echo "  help"
    exit 1
fi

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Warning: Virtual environment not found at venv/bin/activate"
    echo "Continuing without virtual environment..."
fi

# Build Python command
PYTHON_CMD="python websocket_interactive.py"

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

# Run interactive mode
echo "Starting Interactive WebSocket Streamer..."
echo ""
$PYTHON_CMD

