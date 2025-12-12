# Architecture Overview

This document explains the architecture of the Kalshi Market Maker application.

## Directory Structure

```
Kalshi_MM/
├── run.py                 # Web server entry point
├── cli.py                 # CLI test script entry point
├── config.py              # Centralized configuration
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
│   ├── fair_value.py      # Weather-based pricing model
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
│   │            (Strategy / Quote Generation)              │ │
│   └───────────┬────────────────┬────────────────┬────────┘ │
│               │                │                │          │
│               ▼                ▼                ▼          │
│   ┌───────────────┐  ┌─────────────────┐  ┌────────────┐  │
│   │ risk_manager  │  │   fair_value    │  │  orderbook │  │
│   │    .py        │  │      .py        │  │    .py     │  │
│   │ (Risk Limits) │  │ (Weather Model) │  │ (WebSocket)│  │
│   └───────┬───────┘  └────────┬────────┘  └─────┬──────┘  │
│           │                   │                 │          │
└───────────┼───────────────────┼─────────────────┼──────────┘
            │                   │                 │
┌───────────┼───────────────────┼─────────────────┼──────────┐
│           │      DATA ACCESS LAYER              │          │
│           ▼                   ▼                 ▼          │
│   ┌────────────────────────────────────────────────────┐   │
│   │              kalshi_client.py                       │   │
│   │         (SDK Wrapper / Authentication)              │   │
│   └────────────────────────┬───────────────────────────┘   │
│                            │                               │
└────────────────────────────┼───────────────────────────────┘
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

**Request Flow:**
```
Browser → GET /api/account/balance → api.py → kalshi_service.get_balance() → JSON response
```

### Business Logic Layer (`services/`)

This layer contains all trading logic, independent of Flask.

| Service | Responsibility |
|---------|----------------|
| `market_maker.py` | **Core strategy engine**: Finds opportunities, generates quotes, manages order lifecycle |
| `risk_manager.py` | **Risk enforcement**: Position limits, daily loss limits, inventory skew calculations |
| `fair_value.py` | **Pricing model**: Fetches NWS weather data, calculates theoretical probabilities |
| `orderbook.py` | **Real-time data**: Maintains live orderbook state via WebSocket streaming |

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
| `MarketsApi` | Market data, orderbook, trades |
| `SeriesApi` | Series metadata |

### Configuration (`config.py`)

Centralized settings using Python dataclasses:

```python
@dataclass
class AppConfig:
    kalshi: KalshiConfig      # API endpoints, keys
    risk: RiskConfig          # Position limits, loss limits
    strategy: StrategyConfig  # Target series, spreads
    flask: FlaskConfig        # Host, port, debug mode

config = AppConfig()  # Global singleton
```

## Data Flow Examples

### 1. Dashboard Refresh (Every 2 seconds)
```
dashboard.html (JavaScript)
    │
    ├─► GET /api/account/balance ─► kalshi_service.get_balance() ─► SDK ─► Kalshi API
    ├─► GET /api/account/positions ─► kalshi_service.get_positions() ─► SDK ─► Kalshi API
    ├─► GET /api/strategy/status ─► market_maker.get_status()
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
    ├─► Calculate fair values from fair_value service
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

1. **Singleton Services**: Services maintain state (positions, orderbook) and are shared across the app.

2. **SDK-Only API Access**: All Kalshi API calls go through the official SDK, no raw REST calls (except NWS weather API).

3. **Separation of Concerns**: Flask knows nothing about trading logic; services know nothing about HTTP.

4. **Configuration as Code**: All settings in `config.py`, not scattered across files.

5. **WebSocket for Orderbook**: Real-time streaming is faster than polling for market data.

## External Dependencies

| Dependency | Purpose |
|------------|---------|
| `kalshi-python` | Official Kalshi SDK |
| `flask` | Web framework |
| `flask-socketio` | WebSocket support for Flask |
| `requests` | HTTP client (for NWS weather API only) |
| `scipy` | Statistical functions for fair value calculations |
