# Kalshi Real-time Dashboard

A web application for displaying real-time market data from Kalshi WebSocket API.

## Features

1. **Real-time Market Subscription**: Subscribe to markets by entering a Market ID
2. **WebSocket Console**: Terminal-style console displaying all WebSocket messages
3. **Orderbook Display**: Live orderbook updates for subscribed markets
4. **Price Chart**: Real-time price charts for YES and NO contracts with market selector
5. **Data Caching**: Orderbook data cached every 10 minutes for historical reconstruction
6. **Price Data Storage**: Separate price data storage for efficient chart rendering

## Installation

1. Install dependencies:

**Option 1: Using --user flag (recommended for system-wide Python)**
```bash
pip install --user -r requirements.txt
```

**Option 2: Using --break-system-packages (if you understand the risks)**
```bash
pip install --break-system-packages -r requirements.txt
```

**Option 3: Using virtual environment (best practice)**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Make sure you have your Kalshi API credentials configured in the project (see main project setup).

## Running the Application

```bash
cd WebsocketApp
python app.py
```

The dashboard will be available at: http://localhost:5000

## Usage

1. **Subscribe to a Market**: Enter a Market ID (e.g., `KXRELEASECPI-25`) in the input box and click "Subscribe"
2. **View Orderbook**: Select a subscribed market from the orderbook dropdown to view live orderbook data
3. **View Price Chart**: Select a subscribed market from the chart dropdown to view price history
4. **Monitor Console**: Watch the terminal console for all WebSocket messages and connection status

## Data Storage

- Orderbook snapshots are cached every 10 minutes in `data/orderbook_{market_id}_{timestamp}.json`
- Price data is stored in memory and can be reconstructed from cached orderbooks
- Price data is limited to the last 1000 data points per market for performance

## Architecture

- **app.py**: Flask application with SocketIO for real-time communication
- **websocket_handler.py**: Wrapper around KalshiMarketStreamer with caching and data management
- **templates/index.html**: Main dashboard HTML
- **static/js/app.js**: Frontend JavaScript for real-time updates
- **static/css/style.css**: Terminal-style CSS styling

## Notes

- The WebSocket connection runs in a separate thread to avoid blocking the Flask app
- All market data is stored in memory and cleared when markets are unsubscribed
- The dashboard automatically reconnects on connection loss

