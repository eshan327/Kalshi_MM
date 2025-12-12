# Architecture Overview

This document explains the architecture of the Kalshi Market Maker application.

## Design Philosophy

This market maker follows a **spread-capture strategy**:
- We don't predict prices or calculate "fair value"
- We profit from the bid-ask spread by quoting both sides
- Risk is managed through position limits and inventory skew

## Directory Structure

```
Kalshi_MM/
├── run.py                 # Web server entry point
├── cli.py                 # CLI test script entry point
├── config.py              # Centralized configuration
├── .env                   # API credentials (not in git)
├── requirements.txt       # Python dependencies
│
├── app/                   # Flask web application layer
│   ├── __init__.py        # Flask app factory
│   ├── routes/
│   │   ├── dashboard.py   # HTML page routes
│   │   └── api.py         # JSON API routes
│   └── templates/
│       └── dashboard.html # Web dashboard UI
│
├── services/              # Business logic layer
│   ├── kalshi_client.py   # Kalshi SDK wrapper
│   ├── orderbook.py       # Real-time orderbook (WebSocket)
│   ├── risk_manager.py    # Risk management engine
│   └── market_maker.py    # Trading strategy engine
│
├── private_key.pem        # Production API key (not in git)
└── private_demo_key.pem   # Demo API key (not in git)
```

## Layer Architecture

The application follows a **3-layer architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                       │
│                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌───────────────┐  │
│   │  dashboard  │    │   api.py    │    │   cli.py      │  │
│   │    .html    │◄──►│  (JSON API) │    │  (terminal)   │  │
│   └─────────────┘    └──────┬──────┘    └───────┬───────┘  │
│         ▲                   │                   │          │
│         │ polls /api/*      │                   │          │
│         └───────────────────┘                   │          │
└─────────────────────────────────────────────────┼──────────┘
                                                  │
┌─────────────────────────────────────────────────┼──────────┐
│                     BUSINESS LOGIC LAYER        │          │
│                                                 ▼          │
│   ┌──────────────────────────────────────────────────────┐ │
│   │                   market_maker.py                     │ │
│   │         (Strategy / Spread-Based Quoting)             │ │
│   └───────────┬────────────────────────────────┬─────────┘ │
│               │                                │           │
│               ▼                                ▼           │
│   ┌───────────────┐                    ┌────────────┐     │
│   │ risk_manager  │                    │  orderbook │     │
│   │    .py        │                    │    .py     │     │
│   │ (Risk Limits) │                    │ (WebSocket)│     │
│   └───────┬───────┘                    └─────┬──────┘     │
│           │                                  │            │
└───────────┼──────────────────────────────────┼────────────┘
            │                                  │
┌───────────┼──────────────────────────────────┼────────────┐
│           │      DATA ACCESS LAYER           │            │
│           ▼                                  ▼            │
│   ┌────────────────────────────────────────────────────┐  │
│   │              kalshi_client.py                       │  │
│   │         (SDK Wrapper / Authentication)              │  │
│   └────────────────────────┬───────────────────────────┘  │
│                            │                              │
└────────────────────────────┼──────────────────────────────┘
                             │
                             ▼
                   ┌───────────────────┐
                   │   Kalshi API      │
                   │  (REST + WebSocket)│
                   └───────────────────┘
```

## Component Details

### Entry Points

| File | Purpose | When to Use |
|------|---------|-------------|
| `run.py` | Starts Flask web server with dashboard | Production / monitoring |
| `cli.py` | Quick CLI test of API connectivity | Development / debugging |

### Presentation Layer (`app/`)

**Flask** is a lightweight Python web framework. This layer handles HTTP requests.

| Component | Responsibility |
|-----------|----------------|
| `app/__init__.py` | Creates Flask app instance, registers blueprints, initializes SocketIO |
| `app/routes/dashboard.py` | Serves the HTML dashboard at `GET /` |
| `app/routes/api.py` | JSON API endpoints at `GET /api/*` for the frontend |
| `app/templates/dashboard.html` | Single-page dashboard with real-time updates via JavaScript polling |

**Dashboard displays:**
- Market ticker, bid, ask, mid, spread
- Position and P&L tracking
- Strategy controls (start/stop/kill switch)
- Live uptime counter

### Business Logic Layer (`services/`)

This layer contains all trading logic, independent of Flask.

| Service | Responsibility |
|---------|----------------|
| `market_maker.py` | **Core strategy engine**: Finds spread opportunities, places orders, manages order lifecycle |
| `risk_manager.py` | **Risk enforcement**: Position limits, daily loss limits, inventory skew calculations |
| `orderbook.py` | **Real-time data**: Maintains live orderbook state via WebSocket streaming |

**Strategy Logic (Undercut the Spread):**

On Kalshi, you place limit orders to buy/sell contracts:

1. **Find opportunity**: Look for markets with spread ≥ 5¢
2. **Buy side**: Place limit bid at `best_bid` or `best_bid + 1¢` to undercut other buyers
3. **Wait for fill**: When bid fills, we acquire contracts
4. **Sell side**: Offer contracts at `best_ask` or `best_ask - 1¢` to undercut other sellers
5. **Profit**: The difference between buy and sell price

**Example:**
```
Market: Bid 42¢ / Ask 48¢ (6¢ spread)
→ We bid at 43¢, get filled (undercut buyers)
→ We offer at 47¢, get filled (undercut sellers)  
→ Profit: 4¢ per contract
```

**Service Singletons:**
Each service exports a singleton instance for shared state:
```python
# services/kalshi_client.py
kalshi_service = KalshiService()  # Singleton

# Other files import it
from services.kalshi_client import kalshi_service
```

### Data Access Layer (`services/kalshi_client.py`)

Wraps the `kalshi-python` SDK, providing:
- Authentication (RSA key signing)
- REST API calls (balance, orders, positions, markets)
- Error handling and logging

**SDK API Classes Used:**
| Class | Purpose |
|-------|---------|
| `PortfolioApi` | Balance, orders, positions, fills |
| `MarketsApi` | Market data, orderbook |

### Configuration (`config.py`)

Environment-based configuration using Python dataclasses:

```python
@dataclass
class AppConfig:
    kalshi: KalshiConfig      # API endpoints, keys
    risk: RiskConfig          # Position limits, loss limits
    strategy: StrategyConfig  # Target series, spreads
    flask: FlaskConfig        # Host, port, debug mode

config = AppConfig()  # Global singleton
```

**Key Strategy Settings:**
| Setting | Default | Description |
|---------|---------|-------------|
| `min_spread` | 5¢ | Minimum spread to trade |
| `quote_refresh_interval` | 5s | How often to refresh quotes |

## Data Flow Examples

### 1. Dashboard Refresh (Every 2 seconds)
```
dashboard.html (JavaScript)
    │
    ├─► GET /api/account/balance ─► kalshi_service.get_balance() ─► SDK ─► Kalshi API
    ├─► GET /api/account/positions ─► kalshi_service.get_positions() ─► SDK ─► Kalshi API
    ├─► GET /api/strategy/markets ─► market_maker + orderbook data
    └─► GET /api/risk/status ─► risk_manager.get_status()
```

### 2. Start Market Making Strategy
```
User clicks "Start" button
    │
    ▼
POST /api/strategy/start
    │
    ▼
market_maker.start()
    │
    ├─► Fetch markets from kalshi_service
    ├─► Subscribe to orderbook WebSocket
    ├─► Check spreads ≥ min_spread
    ├─► Check risk limits from risk_manager
    └─► Place quotes via kalshi_service.create_order()
```

### 3. Real-time Orderbook Updates
```
orderbook_service.start()
    │
    ▼
WebSocket connect to wss://api.elections.kalshi.com/trade-api/ws/v2
    │
    ▼
Subscribe to orderbook_delta channel
    │
    ▼
On message: Update local orderbook state
    │
    ▼
market_maker reads orderbook_service.get_orderbook(ticker)
```

## Key Design Decisions

1. **No Fair Value Model**: We capture spreads, not predict prices. Simpler and more robust.

2. **Singleton Services**: Services maintain state (positions, orderbook) and are shared across the app.

3. **SDK-Only API Access**: All Kalshi API calls go through the official SDK.

4. **Separation of Concerns**: Flask knows nothing about trading logic; services know nothing about HTTP.

5. **Environment-Based Config**: All settings via environment variables for security and flexibility.

6. **WebSocket for Orderbook**: Real-time streaming is faster than polling for market data.

## External Dependencies

| Dependency | Purpose |
|------------|---------|
| `kalshi-python` | Official Kalshi SDK |
| `flask` | Web framework |
| `flask-socketio` | WebSocket support for Flask |
| `websockets` | Kalshi orderbook WebSocket |
| `cryptography` | RSA key authentication |
| `python-dotenv` | Environment variable loading |
