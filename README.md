# Kalshi Market Maker

A market-making bot for [Kalshi](https://kalshi.com) prediction markets, focused on NYC high temperature weather contracts.

## What It Does

This application automatically provides liquidity on Kalshi weather markets by:

1. **Monitoring Markets**: Scans the KXHIGHNY series (NYC high temperature) for trading opportunities
2. **Calculating Fair Value**: Uses National Weather Service forecast data to estimate true probabilities
3. **Quoting Both Sides**: Places bid and ask orders around fair value to capture the spread
4. **Managing Risk**: Enforces position limits, tracks P&L, and adjusts quotes based on inventory

## Features

- 📊 **Web Dashboard**: Real-time monitoring at `http://localhost:5000`
- 🌡️ **Weather-Based Pricing**: Fair value from NWS hourly forecasts
- ⚡ **Real-Time Orderbook**: WebSocket streaming for live market data
- 🛡️ **Risk Management**: Position limits, daily loss limits, inventory skew
- 🔌 **SDK Integration**: Uses official `kalshi-python` SDK

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- Kalshi API key with trading permissions

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Kalshi_MM.git
cd Kalshi_MM

# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt

# Or with pip
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

1. **Add your API key**: Place your Kalshi private key file in the project root:
   ```
   private_key.pem      # Production key
   private_demo_key.pem # Demo key (optional)
   ```

2. **Update config** (optional): Edit `config.py` to change:
   - API key ID
   - Risk limits (position size, daily loss)
   - Strategy parameters (target spread, order size)

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
│
├── app/                # Flask web app
│   ├── routes/         # API endpoints
│   └── templates/      # Dashboard HTML
│
└── services/           # Business logic
    ├── kalshi_client.py   # SDK wrapper
    ├── orderbook.py       # WebSocket streaming
    ├── risk_manager.py    # Risk engine
    ├── fair_value.py      # Weather pricing
    └── market_maker.py    # Strategy engine
```

See [Architecture.md](Architecture.md) for detailed documentation.

## Dashboard

The web dashboard provides:

| Section | Description |
|---------|-------------|
| **Strategy Controls** | Start/stop trading, adjust parameters |
| **Account** | Balance, positions, open orders |
| **Markets** | Live bid/ask/spread for each contract |
| **Risk Panel** | Current exposure, daily P&L, limits |
| **Recent Fills** | Trade execution history |

## Configuration Reference

Key settings in `config.py`:

```python
# Risk Limits
max_position_per_market = 100   # Max contracts per market
max_daily_loss = 50.00          # Stop trading if exceeded (USD)

# Strategy
target_series = "KXHIGHNY"      # NYC High Temp series
min_spread = 5                  # Minimum spread to quote (cents)
default_order_size = 10         # Contracts per order

# Environment
use_prod = True                 # True = production, False = demo
```

## How Market Making Works

1. **Fair Value Calculation**:
   - Fetch NWS hourly forecast for NYC
   - Calculate probability that high temp exceeds threshold
   - Convert to fair price (e.g., 70% probability → 70¢)

2. **Quote Generation**:
   - Place bid at `fair_value - half_spread`
   - Place ask at `fair_value + half_spread`
   - Adjust for inventory (skew quotes to reduce position)

3. **Risk Management**:
   - Check position limits before each order
   - Track realized + unrealized P&L
   - Trigger kill switch if daily loss exceeded

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/account/balance` | Account balance |
| `GET /api/account/positions` | Current positions |
| `GET /api/account/orders` | Open orders |
| `GET /api/strategy/status` | Strategy state |
| `POST /api/strategy/start` | Start market making |
| `POST /api/strategy/stop` | Stop market making |
| `GET /api/risk/status` | Risk metrics |

## Development

**Run in debug mode:**
```bash
python run.py  # Flask debug mode is enabled by default
```

**Test SDK connectivity:**
```bash
python cli.py
```

## Dependencies

- `kalshi-python` - Official Kalshi SDK
- `flask` - Web framework
- `flask-socketio` - WebSocket support
- `requests` - HTTP client (for NWS API)
- `scipy` - Statistical calculations

## Disclaimer

⚠️ **Use at your own risk.** This software is for educational purposes. Trading on Kalshi involves real money. The authors are not responsible for any financial losses.

## License

MIT
