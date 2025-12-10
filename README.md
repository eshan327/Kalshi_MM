# Kalshi Market Making Bot

A Python-based automated trading system for [Kalshi](https://kalshi.com) prediction markets. Features market analysis, real-time WebSocket streaming, and automated market making strategies.

## Features

- **Market Analysis**: Scan thousands of markets for spread opportunities
- **Real-time Data**: WebSocket streaming for live orderbook and trade updates
- **Market Making**: Automated bid/ask placement to capture spreads
- **Web Dashboard**: Flask-based UI for monitoring markets in real-time
- **Dual Environment**: Support for both demo and production trading

## Quick Start

```bash
# 1. Clone and install dependencies
git clone https://github.com/eshan327/Kalshi_MM.git
cd Kalshi_MM
pip install -r requirements.txt

# 2. Set up credentials (see Setup section below)
cp Setup/config_template.py Setup/config.py
# Edit Setup/config.py with your API credentials

# 3. Run the universal launcher
python Setup/run_universal.py demo    # Safe testing mode
python Setup/run_universal.py prod    # Production (real money!)
```

## Project Structure

```
Kalshi_MM/
├── Setup/                      # Configuration & API setup
│   ├── apiSetup.py            # KalshiAPI client wrapper
│   ├── config_template.py     # Template for credentials
│   ├── config.py              # Your credentials (gitignored)
│   └── run_universal.py       # Universal launcher script
│
├── Strategies/                 # Trading strategies
│   └── basicMM.py             # Market maker (spread detection + trading)
│
├── Getdata/                    # Market data utilities
│   ├── getData.py             # Fetch & sort markets by spread
│   ├── filterMarkets.py       # Filter markets by type/volume
│   └── orderBookListener.py   # Monitor orderbook changes
│
├── Websocket/                  # Real-time streaming
│   ├── market_streamer.py     # WebSocket client for live data
│   └── websocket_interactive.py # Interactive CLI for streaming
│
├── WebsocketApp/               # Web dashboard
│   ├── app.py                 # Flask application
│   ├── websocket_handler.py   # WebSocket-to-Flask bridge
│   ├── templates/             # HTML templates
│   └── static/                # CSS/JS assets
│
├── visualize_orderbook.py     # Orderbook visualization tool
├── requirements.txt           # Python dependencies
├── data/                      # Output data (gitignored)
└── logs/                      # Trade logs (gitignored)
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Credentials

1. Get your API credentials from [Kalshi](https://kalshi.com) (Settings → API Keys)
2. Create your config file:

```bash
cp Setup/config_template.py Setup/config.py
```

3. Edit `Setup/config.py` with your credentials:

```python
PRODUCTION_API_KEY_ID = "your-api-key-id-here"
DEMO_API_KEY_ID = "your-demo-api-key-id-here"  # Optional
```

4. Place your private key files in `Setup/`:
   - Production: `Setup/private_key.pem`
   - Demo: `Setup/private_demo_key.pem`

### 3. Verify Setup

```bash
python Setup/run_universal.py demo
# Should display account balance and market opportunities
```

## Usage

### Universal Launcher (Recommended)

```bash
# Interactive mode
python Setup/run_universal.py

# Command line mode
python Setup/run_universal.py demo        # Demo environment
python Setup/run_universal.py production  # Production (real money!)
```

### Find Trading Opportunities

```bash
python Strategies/basicMM.py
```

This will:
1. Fetch all active markets
2. Identify opportunities with spread > 3% and volume > 1000
3. Save results to `data/marketData/`

### Get Markets by Spread

```bash
python Getdata/getData.py --top 20
python Getdata/getData.py --limit 100 --top 10 --output my_markets.json
```

### Real-time WebSocket Streaming

```bash
# Stream a specific market
python Websocket/market_streamer.py --market-id KXBTC-25JAN03-T98500

# Interactive mode
python Websocket/websocket_interactive.py --market-id KXBTC-25JAN03-T98500

# Demo environment
python Websocket/market_streamer.py --market-id KXBTC-25JAN03-T98500 --demo
```

### Web Dashboard

```bash
cd WebsocketApp
python app.py
# Open http://localhost:5001
```

## Trading Strategy

The `basicMM.py` market maker uses a spread capture strategy:

1. **Scan**: Find markets with bid-ask spread > 3% and volume > 1000
2. **Quote**: Place buy order at `bid + 1¢`, sell order at `ask - 1¢`
3. **Capture**: Profit from the spread when both orders fill

**Example:**
```
Market: "Will BTC exceed $98,500?"
Current: Bid 45¢ / Ask 52¢ (7¢ spread)
Bot places: Buy @ 46¢, Sell @ 51¢
Potential profit: 5¢ per contract
```

## Configuration

Edit `Strategies/basicMM.py` to adjust parameters:

```python
# In BasicMM.__init__():
reserve_limit = 10      # Keep $10 in reserve
demo = False            # True for demo environment

# In filter_market_opportunities():
min_spread = 0.03       # Minimum 3% spread
min_volume = 1000       # Minimum volume
max_spread = 0.10       # Maximum 10% spread
```

## API Reference

### KalshiAPI

```python
from Setup.apiSetup import KalshiAPI

client = KalshiAPI().get_client(demo=False)
balance = client.get_balance()
markets = client.get_markets(limit=100)
```

### BasicMM

```python
from Strategies.basicMM import BasicMM

mm = BasicMM(reserve_limit=10, demo=True)
mm.identify_market_opportunities()
print(f"Found {len(mm.market_opportunities)} opportunities")
```

## Data Output

| Type | Location | Format |
|------|----------|--------|
| Market opportunities | `data/marketData/` | CSV |
| Orderbook snapshots | `data/orderbookData/` | JSON |
| Trade logs | `logs/trade_logs/` | LOG |
| Price data | `WebsocketApp/data/` | JSON |

## Demo vs Production

| Feature | Demo | Production |
|---------|------|------------|
| API URL | demo-api.kalshi.co | api.elections.kalshi.com |
| Real money | No | Yes |
| Credentials | DEMO_API_KEY_ID | PRODUCTION_API_KEY_ID |

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Private key file not found" | Ensure `Setup/private_key.pem` exists |
| "API key ID not found" | Create `Setup/config.py` from template |
| WebSocket won't connect | Check credentials, try `--demo` flag |
| "Invalid status filter" | Pass `status=None` to `get_markets()` |

## Safety Warnings

⚠️ **This bot trades real money in production mode.**

- Always test in demo mode first
- Start with small positions
- Monitor your positions actively
- Set appropriate reserve limits
- Review code before running in production

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - Use at your own risk.
