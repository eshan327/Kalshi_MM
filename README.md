# Kalshi Market Maker

A spread-capturing market maker for [Kalshi](https://kalshi.com) prediction markets, focused on NYC high temperature weather contracts.

## What It Does

This application automatically provides liquidity on Kalshi weather markets by:

1. **Monitoring Markets**: Scans the KXHIGHNY series (NYC high temperature) for trading opportunities
2. **Capturing Spreads**: Quotes both sides of the market to profit from the bid-ask spread
3. **Managing Risk**: Enforces position limits, tracks P&L, and adjusts quotes based on inventory

## Philosophy

This market maker operates on a simple principle: **capture the spread**. We don't try to predict fair value or forecast weather—we simply provide liquidity where spreads are wide enough to profit.

## Features

- 📊 **Web Dashboard**: Real-time monitoring at `http://localhost:5000`
- ⚡ **Real-Time Orderbook**: WebSocket streaming for live market data
- 🛡️ **Risk Management**: Position limits, daily loss limits, inventory skew
- 🔌 **SDK Integration**: Uses official `kalshi-python` SDK

## Quick Start

### Prerequisites

- Python 3.11+
- Kalshi API key with trading permissions

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Kalshi_MM.git
cd Kalshi_MM

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

1. **Create your `.env` file**:
   ```bash
   cp .env.example .env
   ```

2. **Add your API credentials**:
   ```env
   KALSHI_API_KEY_ID=your-api-key-id-here
   KALSHI_PRIVATE_KEY_FILE=private_key.pem
   ```

3. **Place your private key** in the project root as `private_key.pem`

### Running

**Start the web dashboard:**
```bash
python run.py
```
Then open http://localhost:5000 in your browser.

**Quick CLI test:**
```bash
python cli.py
```

## Project Structure

```
Kalshi_MM/
├── run.py              # Start web server
├── cli.py              # CLI test script
├── config.py           # All configuration
├── .env                # Your API credentials (not in git)
│
├── app/                # Flask web app
│   ├── routes/         # API endpoints
│   └── templates/      # Dashboard HTML
│
└── services/           # Business logic
    ├── kalshi_client.py   # SDK wrapper
    ├── orderbook.py       # WebSocket streaming
    ├── risk_manager.py    # Risk engine
    └── market_maker.py    # Strategy engine
```

See [Architecture.md](Architecture.md) for detailed documentation.

## Dashboard

The web dashboard provides:

| Section | Description |
|---------|-------------|
| **Strategy Controls** | Start/stop trading, kill switch |
| **Account** | Balance, positions, open orders |
| **Markets** | Live bid/ask/mid/spread for each contract |
| **Risk Panel** | Current exposure, daily P&L, limits |
| **Recent Fills** | Trade execution history |

## Configuration Reference

Key settings in `config.py` (override via environment variables):

| Setting | Default | Env Variable | Description |
|---------|---------|--------------|-------------|
| `min_spread` | 5 | `MIN_SPREAD` | Minimum spread to trade (cents) |
| `max_position_per_market` | 100 | `MAX_POSITION_PER_MARKET` | Max contracts per market |
| `max_daily_loss` | 50.00 | `MAX_DAILY_LOSS` | Stop trading if exceeded (USD) |
| `default_order_size` | 10 | `DEFAULT_ORDER_SIZE` | Contracts per order |
| `target_series` | KXHIGHNY | `TARGET_SERIES` | Market series to trade |

## How It Works

### Spread-Capture Strategy

On Kalshi, market making works by placing limit orders:

1. **Buy Side**: Place limit bid at `best_bid` or `best_bid + 1¢` to undercut and get filled
2. **Acquire Contracts**: When bid fills, we now hold contracts
3. **Sell Side**: Offer contracts at `best_ask` or `best_ask - 1¢` to undercut sellers
4. **Profit**: The spread between buy and sell price (minimum 5¢)

**Example:**
- Market shows Bid: 42¢ / Ask: 48¢ (6¢ spread)
- We bid at 43¢, get filled
- We offer at 47¢, get filled
- Profit: 4¢ per contract

### Risk Management

- **Position limits**: Cap exposure per market and total
- **Daily loss limit**: Halt trading if losses exceed threshold
- **Inventory skew**: Adjust quotes to reduce large positions
- **Kill switch**: Emergency button to cancel all orders

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/account/balance` | Account balance |
| `GET /api/account/positions` | Current positions |
| `GET /api/account/orders` | Open orders |
| `GET /api/strategy/status` | Strategy state & stats |
| `POST /api/strategy/start` | Start market making |
| `POST /api/strategy/stop` | Stop market making |
| `POST /api/risk/kill-switch` | Emergency stop |
| `GET /api/risk/status` | Risk metrics |

## Dependencies

- `kalshi-python` - Official Kalshi SDK
- `flask` / `flask-socketio` - Web framework
- `websockets` - Real-time orderbook streaming
- `cryptography` - API authentication
- `python-dotenv` - Environment configuration

## Disclaimer

⚠️ **Use at your own risk.** This software is for educational purposes. Trading on Kalshi involves real money. The authors are not responsible for any financial losses.

## License

MIT
