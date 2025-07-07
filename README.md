# Kalshi Scraper & Market Making Bot

A Python-based trading automation system for Kalshi prediction markets that includes API integration, scraping, and automated market making strategies.

## Features

- **Kalshi API Integration**: Direct HTTP and WebSocket connections to Kalshi's trading API
- **Market Making Bot**: Automated trading bot that identifies spread opportunities and places limit orders
- **Web Scraping**: Selenium-based market data extraction and order placement
- **Trading Simulation**: Built-in simulator for backtesting strategies with P&L tracking
- **Real-time Data**: WebSocket connections for live market updates
- **Order Management**: Comprehensive order tracking and fill detection
- **Visualization**: Matplotlib charts for balance history and profit/loss analysis

## Project Structure

```
kalshi_scraper/
├── main.py              # Main API client demo
├── clients.py           # Kalshi HTTP/WebSocket API clients
├── scraper.py           # Basic market data scraper
├── scraper2.py          # Trading simulator
├── scraper3.py          # Full market making bot with order management
├── requirements.txt     # Python dependencies
├── caleb/              # Additional trading utilities
│   ├── trader.py       # Limit order balancing logic
│   ├── trade.py        # Chrome automation helper
│   └── openChromeWindows.py # Chrome debugging setup
└── config/             # Configuration files
    └── settings.py     # Trading parameters
```

## Installation

1. **Clone the repository (SSH)**
   ```bash
   git clone git@github.com:eshan327/Kalshi_MM.git
   cd kalshi_scraper
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the project root:
   ```env
   DEMO_KEYID=
   DEMO_KEYFILE=
   PROD_KEYID=
   PROD_KEYFILE=
   ```

5. **Configure trading parameters**
   Create a `config.ini` file, and fill in each field:
   ```ini
   [Credentials]
   username =
   password =

   [Trading]
   max_position =
   max_capital =
   url =
   ```

## Usage

Test the Kalshi API connection and get account balance:
```bash
python main.py
```

Expected output:
```
Balance: {'balance': 1000.00}
WebSocket connection opened.
Received message: {"type": "ticker_update", "data": {...}}
```

Run the latest market scraper to monitor bid-ask spreads, backtest strategies, and run the full bot with live trading:
```bash
python scraper3.py
```

**Warning**: `scraper3.py` places real orders on Kalshi. Use with caution and start with small position limits.

## Configuration

### Trading Strategy Parameters

The market making bot uses the following default settings:

- **Spread Threshold**: 3¢ minimum bid-ask spread to trigger trades
- **Position Limit**: 1 open contract maximum
- **Capital**: $1000 starting balance
- **Sell Timing**: Random intervals between 10-15 seconds
- **Markets**: First 3 contracts in the target market group

### Risk Management

- Position limits prevent over-exposure
- Real-time P&L tracking
- Order fill confirmation before placing new orders

## API Reference

### KalshiHttpClient

```python
from clients import KalshiHttpClient, Environment

client = KalshiHttpClient(
    key_id="your_key_id",
    private_key=private_key,
    environment=Environment.DEMO  # or Environment.PROD
)

# Get account balance
balance = client.get_balance()

# Get market trades
trades = client.get_trades(ticker="PRES-24")
```

### KalshiWebSocketClient

```python
from clients import KalshiWebSocketClient

ws_client = KalshiWebSocketClient(
    key_id="your_key_id", 
    private_key=private_key,
    environment=Environment.DEMO
)

# Connect and subscribe to ticker updates
await ws_client.connect()
```

## Market Making Strategy

The bot implements a simple market making strategy:

1. **Scan Markets**: Monitor bid-ask spreads across target contracts
2. **Identify Opportunities**: Look for spreads ≥ 3¢
3. **Place Orders**: Submit limit orders at improved prices
4. **Manage Risk**: Limit open positions and capital exposure
5. **Take Profits**: Sell positions at predetermined intervals

### Example Trade Flow

```
Market: "Will NYC's highest temperature today exceed 85°F?"
Yes Contract: Bid 43¢, Ask 49¢ (6¢ spread)
Bot Action: Bid 44¢, Ask 48¢ (4¢ potential profit)
```

## Output & Monitoring

### Console Output
- Real-time market data and spread analysis
- Order placement and fill confirmations
- Position and balance updates
- P&L calculations

### Generated Files
- `plots/trading_balance_history.png` - Account balance over time
- `plots/trading_profit_history.png` - Cumulative profit/loss
- Trading summary with win rates and statistics

## Browser Requirements

For functionality:
- **Firefox**: Default browser for Selenium automation
- **Chrome**: Alternative browser with debugging support, may break
- **WebDriver**: Automatically managed by webdriver-manager

## Security Considerations

- **API Keys**: Store securely in `.env` file (never commit to git)
- **Private Keys**: Use separate demo/prod key files
- **2FA**: Supported for manual login flows
- **Rate Limiting**: Built-in API rate limiting (100ms between calls)

## Troubleshooting

### Common Issues

1. **Login Failures**
   - Verify credentials in `config.ini`
   - Check for 2FA requirements
   - Ensure browser automation permissions

2. **Order Placement Errors**
   - Confirm market is active and tradeable
   - Check position limits and available capital
   - Verify WebDriver compatibility

3. **API Connection Issues**
   - Validate API keys and private key files
   - Check network connectivity
   - Verify environment settings (DEMO vs PROD)

### Debug Mode

Enable verbose logging by setting environment variable, e.g.
```bash
export DEBUG=1
python scraper3.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details.