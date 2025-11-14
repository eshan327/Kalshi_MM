# Write header row with column descriptions
# Column descriptions:
# timestamp: When this market data was captured
# ticker: Unique market identifier (e.g., KXMVENFL...)
# title: Human-readable description of the market
# spread: Calculated bid-ask spread (yes_ask - yes_bid), in cents (0-100 range)
# yes_bid: Best bid price for "yes" contract, in cents (0-100 range)
# yes_ask: Best ask price for "yes" contract, in cents (0-100 range)
# no_bid: Best bid price for "no" contract, in cents (0-100 range)
# no_ask: Best ask price for "no" contract, in cents (0-100 range)
# volume: Total trading volume for this market
# volume_24h: Trading volume in the last 24 hours
# last_price: Last traded price, in cents (0-100 range)
# status: Market status (e.g., "open", "active", "closed")
# close_time: When the market closes (ISO format)
# event_ticker: Event identifier this market belongs to (if available)