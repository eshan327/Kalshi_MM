# WebSocket Subscription Commands

This document shows the WebSocket commands for subscribing to Kalshi markets.

## 1. Subscribe to Market

Subscribe to one or more channels for a specific market.

### WebSocket JSON Command:
```json
{
  "id": 1,
  "cmd": "subscribe",
  "params": {
    "channels": ["ticker", "orderbook_delta", "trade"],
    "market_ticker": "KXMLBGAME-25OCT31LADTOR-LAD"
  }
}
```

### Python API Usage:
```python
# Subscribe to a single market with default channels
await streamer.subscribe_to_market("KXMLBGAME-25OCT31LADTOR-LAD")

# Subscribe with specific channels
await streamer.subscribe_to_market(
    "KXMLBGAME-25OCT31LADTOR-LAD",
    channels=["ticker", "orderbook_delta", "trade"]
)

# Subscribe to multiple markets
await streamer.subscribe_to_multiple_markets(
    ["MARKET1", "MARKET2", "MARKET3"],
    channels=["ticker", "orderbook_delta"]
)
```

### Available Channels:
- `"ticker"` - Real-time ticker updates (last price, volume, etc.)
- `"orderbook_delta"` - Orderbook updates (bid/ask changes)
- `"trade"` - Public trade executions
- `"fill"` - Your fill notifications (requires authentication)
- `"position"` - Position updates (requires authentication)

### Terminal Command:
```bash
# Start websocket with initial markets
./run_websocket.sh --market-id KXMLBGAME-25OCT31LADTOR-LAD

# Or multiple markets
./run_websocket.sh --market-ids MARKET1 MARKET2 MARKET3
```

---

## 2. Unsubscribe from Market

Unsubscribe from one or more subscriptions using their Subscription IDs (SIDs).

### WebSocket JSON Command:
```json
{
  "id": 2,
  "cmd": "unsubscribe",
  "params": {
    "sids": [1, 2, 3]
  }
}
```

### Python API Usage:
```python
# Unsubscribe using SIDs (received in "subscribed" response)
await streamer.unsubscribe([1, 2, 3])
```

---

## 3. Update Subscription

Add or remove markets from an existing subscription.

### WebSocket JSON Command:
```json
{
  "id": 3,
  "cmd": "update_subscription",
  "params": {
    "sids": [1],
    "market_tickers": ["MARKET4", "MARKET5"],
    "action": "add_markets"
  }
}
```

Or to remove markets:
```json
{
  "id": 4,
  "cmd": "update_subscription",
  "params": {
    "sids": [1],
    "market_tickers": ["MARKET1"],
    "action": "delete_markets"
  }
}
```

### Python API Usage:
```python
# Add markets to existing subscription
await streamer.update_subscription(
    sids=[1],
    market_tickers=["MARKET4", "MARKET5"],
    action="add_markets"
)

# Remove markets from existing subscription
await streamer.update_subscription(
    sids=[1],
    market_tickers=["MARKET1"],
    action="delete_markets"
)
```

---

## 4. List Subscriptions

List all active subscriptions.

### WebSocket JSON Command:
```json
{
  "id": 5,
  "cmd": "list_subscriptions"
}
```

### Python API Usage:
```python
await streamer.list_subscriptions()
```

---

## Response Messages

### Subscription Confirmation:
```json
{
  "id": 1,
  "type": "subscribed",
  "msg": {
    "channel": "orderbook_delta",
    "sid": 1
  }
}
```

### Unsubscription Confirmation:
```json
{
  "sid": 1,
  "type": "unsubscribed"
}
```

### Error Response:
```json
{
  "id": 123,
  "type": "error",
  "msg": {
    "code": 6,
    "msg": "Already subscribed"
  }
}
```

### List Subscriptions Response:
```json
{
  "id": 5,
  "type": "ok",
  "subscriptions": [
    {
      "channel": "orderbook_delta",
      "sid": 1
    },
    {
      "channel": "ticker",
      "sid": 2
    }
  ]
}
```

---

## Example: Complete Subscription Flow

```python
import asyncio
from Websocket.market_streamer import KalshiMarketStreamer

async def example():
    # Create streamer with initial markets
    streamer = KalshiMarketStreamer(
        market_ids=["KXMLBGAME-25OCT31LADTOR-LAD"]
    )
    
    # Connect
    if await streamer.connect():
        # Already subscribed to initial markets, but you can add more:
        
        # Add another market
        await streamer.subscribe_to_market("KXNHLSPREAD-25NOV01CARBOS-BOS1")
        
        # List current subscriptions
        await streamer.list_subscriptions()
        
        # Start listening for updates
        await streamer.listen()
    else:
        print("Failed to connect")

asyncio.run(example())
```

---

## Quick Reference

| Command | WebSocket `cmd` | Python Method |
|---------|----------------|---------------|
| Subscribe | `"subscribe"` | `subscribe_to_market()` |
| Unsubscribe | `"unsubscribe"` | `unsubscribe()` |
| Update | `"update_subscription"` | `update_subscription()` |
| List | `"list_subscriptions"` | `list_subscriptions()` |

---

## Notes

- **Subscription IDs (SIDs)**: Each subscription receives a unique SID in the "subscribed" response
- **Command IDs**: Each command you send has a unique `id` field for tracking responses
- **Channels**: Default channels are `["ticker", "orderbook_delta", "trade"]`
- **Authentication**: Channels like `"fill"` and `"position"` require authenticated WebSocket connection
- **Dynamic Subscriptions**: You can subscribe to new markets after connection without reconnecting

