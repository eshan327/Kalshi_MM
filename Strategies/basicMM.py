import sys
import os
import csv

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from Setup.apiSetup import KalshiAPI
import datetime
import asyncio
import time

''' This file:
get markets
identify market opportunities
get price
trade
trade single
run
'''
class BasicMM:
    def __init__(self, reserve_limit = 10, demo=False):
        self.client = KalshiAPI().get_client(demo=demo)
        self.market_opportunities = []
        self.market_spreads = {}  # Dictionary mapping market ticker to spread
        self.reserve_limit = reserve_limit # how much to keep in reserve
        self.demo = demo

    def get_markets(self, max_total=100000, page_size=100, status="open"):
        """Fetch markets with robust pagination.

        max_total controls the total number of markets to collect.
        page_size controls the per-request limit (server typically caps at 100).
        status can be forwarded to the API (e.g., "open", "active", "closed").
        """
        all_markets = []
        cursor = None

        while True:
            try:
                params = {"limit": min(page_size, 100)}
                if status is not None:
                    params["status"] = status
                if cursor:
                    params["cursor"] = cursor

                response = self.client.get_markets(**params)

                if hasattr(response, 'markets') and response.markets:
                    all_markets.extend(response.markets)
                else:
                    break

                # Continue pagination if a cursor is provided
                if hasattr(response, 'cursor') and response.cursor:
                    cursor = response.cursor
                else:
                    break

                # Stop if we've reached the requested total
                if len(all_markets) >= max_total:
                    break

            except Exception as e:
                print(f"Error fetching markets: {e}")
                # Fallback: single request without pagination
                try:
                    fallback_params = {"limit": min(page_size, 100)}
                    if status is not None:
                        fallback_params["status"] = status
                    response = self.client.get_markets(**fallback_params)
                    if hasattr(response, 'markets') and response.markets:
                        all_markets.extend(response.markets)
                except Exception as fallback_error:
                    print(f"Fallback also failed: {fallback_error}")
                break

        print(f"Successfully fetched {len(all_markets)} valid markets")

        class MarketResponse:
            def __init__(self, markets):
                self.markets = markets

        return MarketResponse(all_markets)

    def get_market_trades(self, market_id):
        return self.client.get_market_trades(market_id)
    
    def get_market_spread(self, market):
        """Get the spread for a market object. Returns 0 if not found."""
        if isinstance(market, str):
            # If market is a ticker string
            return self.market_spreads.get(market, 0)
        else:
            # If market is a market object
            return self.market_spreads.get(market.ticker, 0)

    def calculate_remaining_balance(self):
        try:
            balance = self.client.get_balance()
            try:
                resting_orders = self.client.get_total_resting_order_value()
                return balance.balance - resting_orders
            except Exception as e:
                print(f"Warning: Could not get resting order value: {e}")
                return balance.balance  # Return just the balance if we can't get resting orders
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0  # Return 0 if we can't get balance

    def identify_market_opportunities(self, max_total=100000):
        start_time = time.perf_counter()
        markets_response = self.get_markets(max_total=max_total, page_size=100, status="open")
        markets = markets_response.markets if hasattr(markets_response, 'markets') else markets_response
        opportunities = []  # Will store tuples of (market, spread)
        market_spreads = {}  # Dictionary to map market ticker to spread for easy access
        
        print(f"Analyzing {len(markets)} markets for opportunities...")
        
        for market in markets:
            # Calculate spread from bid/ask prices
            spread = 0
            if hasattr(market, 'yes_bid') and hasattr(market, 'yes_ask') and market.yes_bid is not None and market.yes_ask is not None:
                spread = market.yes_ask - market.yes_bid
            
            volume = getattr(market, 'volume', 0) or 0
            if spread > 0.03 and volume > 1000:
                opportunities.append((market, spread))
                market_spreads[market.ticker] = spread
        
        # Sort opportunities by spread (highest first)
        opportunities.sort(key=lambda x: x[1], reverse=True)
        # Store as list of markets (spread is accessible via market_spreads dict)
        self.market_opportunities = [market for market, _ in opportunities]
        self.market_spreads = market_spreads  # Store spreads for later access
        
        if len(opportunities) == 0:
            print("No opportunities found with spreads > 0.03")
            print("This is normal when markets have no active trading or tight spreads")
        else:
            print(f"Found {len(opportunities)} opportunities with spreads > 0.03")

        elapsed = time.perf_counter() - start_time
        print(f"identify_market_opportunities completed in {elapsed:.3f} seconds")
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "marketData")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = os.path.join(log_dir, f"marketData_{timestamp}.csv")
        
        # Write CSV file with headers
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            
            writer.writerow([
                "timestamp",
                "ticker",
                "title",
                "spread",
                "yes_bid",
                "yes_ask",
                "no_bid",
                "no_ask",
                "volume",
                "volume_24h",
                "last_price",
                "status",
                "close_time",
                "event_ticker"
            ])
            
            # Write data rows
            current_timestamp = datetime.datetime.now().isoformat()
            for market, spread in opportunities:
                writer.writerow([
                    current_timestamp,
                    market.ticker,
                    getattr(market, 'title', ''),
                    spread,
                    getattr(market, 'yes_bid', None) or '',
                    getattr(market, 'yes_ask', None) or '',
                    getattr(market, 'no_bid', None) or '',
                    getattr(market, 'no_ask', None) or '',
                    getattr(market, 'volume', 0) or 0,
                    getattr(market, 'volume_24h', 0) or 0,
                    getattr(market, 'last_price', None) or '',
                    getattr(market, 'status', ''),
                    str(getattr(market, 'close_time', '')) if hasattr(market, 'close_time') else '',
                    getattr(market, 'event_ticker', '') or ''
                ])
        
        print(f"Market opportunities saved to: {csv_file}")

    # get buy and sell prices for a market
    def get_price(self, marketID):
        """
        Calculate buy and sell prices for market making orders.
        Places orders slightly inside the spread to get filled first.
        
        Args:
            yes_bid: Best bid price in cents (0-100)
            yes_ask: Best ask price in cents (0-100)
            
        Returns:
            Tuple of (buy_price_cents, sell_price_cents) both in range 1-99
        """

        market = self.client.get_market(marketID)
        yes_bid = getattr(market, 'yes_bid', None)
        yes_ask = getattr(market, 'yes_ask', None)

        if yes_bid is None or yes_ask is None:
            print(f"Warning: No bid/ask prices available for market {marketID}")
            return None, None

        # Convert to integers
        base_buy_price = int(yes_bid)
        base_sell_price = int(yes_ask)
        
        # For market making: place orders slightly inside the spread to get filled first
        # Buy at bid + 1 cent (to outbid others and get filled first)
        # Sell at ask - 1 cent (to undercut others and get filled first)
        buy_price_cents = base_buy_price + 1
        sell_price_cents = base_sell_price - 1
        
        # Ensure prices are within valid range (1-99 cents) for the API
        buy_price_cents = max(1, min(99, buy_price_cents))
        sell_price_cents = max(1, min(99, sell_price_cents))
        
        # Ensure we don't cross the spread (buy price should be < sell price)
        if buy_price_cents >= sell_price_cents:
            # If prices would cross, use the mid-price approach
            mid_price = (base_buy_price + base_sell_price) // 2
            buy_price_cents = max(1, min(99, mid_price - 1))
            sell_price_cents = max(1, min(99, mid_price + 1))
            # Ensure buy < sell
            if buy_price_cents >= sell_price_cents:
                buy_price_cents = max(1, sell_price_cents - 1)
        
        return buy_price_cents, sell_price_cents

# executes market making trades for all markets in market_id_list.  Bankroll is the amount of money to be used.
    def trade(self, market_id_list, bankroll): 
        print("--- WARNING: trading with actual money ---")
        # Track remaining bankroll as we place orders
        remaining_bankroll = bankroll
        
        for i in range(len(market_id_list)):
            # Check if we have enough bankroll before processing this market
            if remaining_bankroll <= 0:
                print(f"Insufficient bankroll. Stopping after {i} markets. Remaining: ${remaining_bankroll/100:.2f}")
                break
                
            market = market_id_list[i]
            # Handle both market objects and market ID strings
            market_id = market.ticker if hasattr(market, 'ticker') else market
            
            
            buy_price_cents, sell_price_cents = self.get_price(market_id)
            
            # Note: Prices are stored in probability format (0-1) for logging, but API uses cents (1-99)
            buy_price_prob = buy_price_cents / 100.0
            sell_price_prob = sell_price_cents / 100.0

            # Check if we have enough bankroll for both orders
            # Buy orders cost money (buying yes contracts)
            # Sell orders also cost money (selling yes = buying no contracts)
            buy_order = None
            sell_order = None
            
            total_cost = buy_price_cents + sell_price_cents
            
            # Check if we have enough for both orders
            if remaining_bankroll < total_cost:
                print(f"Insufficient bankroll for market {market_id}. Need ${total_cost/100:.2f} (buy: ${buy_price_cents/100:.2f} + sell: ${sell_price_cents/100:.2f}), have ${remaining_bankroll/100:.2f}")
                continue
            
            # Place buy order (buying yes contracts)
            if remaining_bankroll >= buy_price_cents:
                try:
                    buy_order = self.client.create_order(
                        ticker=market_id,
                        side="yes",
                        action="buy",
                        count=1,
                        type="limit",
                        yes_price=buy_price_cents
                    )
                    # Subtract from bankroll if order was successfully created
                    if buy_order:
                        remaining_bankroll -= buy_price_cents
                        print(f"Buy order placed for {market_id} @ {buy_price_cents} cents. Remaining bankroll: ${remaining_bankroll/100:.2f}")
                except Exception as e:
                    print(f"Error creating buy order for {market_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    buy_order = None
            else:
                print(f"Insufficient bankroll for buy order on {market_id}. Need ${buy_price_cents/100:.2f}, have ${remaining_bankroll/100:.2f}")
            
            # Place sell order (selling yes = buying no contracts, also costs money)
            if remaining_bankroll >= sell_price_cents:
                try:
                    sell_order = self.client.create_order(
                        ticker=market_id,
                        side="yes",
                        action="sell",
                        count=1,
                        type="limit",
                        yes_price=sell_price_cents
                    )
                    # Subtract from bankroll if order was successfully created
                    if sell_order:
                        remaining_bankroll -= sell_price_cents
                        print(f"Sell order placed for {market_id} @ {sell_price_cents} cents. Remaining bankroll: ${remaining_bankroll/100:.2f}")
                except Exception as e:
                    print(f"Error creating sell order for {market_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    sell_order = None
            else:
                print(f"Insufficient bankroll for sell order on {market_id}. Need ${sell_price_cents/100:.2f}, have ${remaining_bankroll/100:.2f}")

            # Log orders
            # Ensure logs/trade_logs directory exists
            base_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
            trade_logs_dir = os.path.join(base_log_dir, "trade_logs")
            os.makedirs(trade_logs_dir, exist_ok=True)
            
            # Create timestamped log file name (use session start time if available, otherwise current time)
            if not hasattr(self, '_session_start_time'):
                self._session_start_time = datetime.datetime.now()
            file_timestamp = self._session_start_time.strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(trade_logs_dir, f"tradeLimitOrders_{file_timestamp}.log")
            
            # Log order details
            with open(log_file, "a") as f:
                entry_timestamp = datetime.datetime.now().isoformat()
                if buy_order:
                    buy_order_id = getattr(buy_order, 'order_id', getattr(buy_order, 'id', 'N/A'))
                    f.write(f"{entry_timestamp}, {market_id}, BUY, {buy_price_prob}, {buy_order_id}\n")
                if sell_order:
                    sell_order_id = getattr(sell_order, 'order_id', getattr(sell_order, 'id', 'N/A'))
                    f.write(f"{entry_timestamp}, {market_id}, SELL, {sell_price_prob}, {sell_order_id}\n")
            
            # check both were created
            if not buy_order or not sell_order:
                print(f"Failed to create buy or sell order for market {market_id}")

                if buy_order:
                    self.client.cancel_order(buy_order.id)
                if sell_order:
                    self.client.cancel_order(sell_order.id)
            
                
    async def run(self):
        bankroll = self.calculate_remaining_balance() - self.reserve_limit
        while bankroll > 0:
            self.identify_market_opportunities()
            if len(self.market_opportunities) > 0:
                self.trade(self.market_opportunities, bankroll)
            else:
                print("No trading opportunities available - waiting for next cycle")
            await asyncio.sleep(1) # runs every second

    def run(self, bankroll): # non async version
        if bankroll > 0:
            self.identify_market_opportunities()
            if len(self.market_opportunities) > 0:
                self.trade(self.market_opportunities, bankroll)
            else:
                print("No trading opportunities available - skipping trade execution")

    def run_test(self): # test one limit order placement
        if (len(self.market_opportunities) > 0):
            self.trade(self.market_opportunities, 10)
        else:
            print("No trading opportunities available - skipping trade execution")

# further filter the market opportunities
    def filter_market_opportunities(self, min_spread=0.03, min_volume=1000, max_spread=0.1, min_price=0.1, 
                                   min_days_until_resolution=None, max_days_until_resolution=None):
        """
        Filter market opportunities by various criteria including resolution date.
        
        Args:
            min_spread: Minimum spread threshold
            min_volume: Minimum volume threshold
            max_spread: Maximum spread threshold
            min_price: Minimum bid/ask price
            min_days_until_resolution: Minimum days until market closes/resolves (filters out markets closing too soon)
            max_days_until_resolution: Maximum days until market closes/resolves (filters out markets closing too far away)
        
        Returns:
            Filtered list of market opportunities
        """
        filtered_opportunities = []
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        for market in self.market_opportunities:
            # Basic filters
            spread = self.get_market_spread(market)  # Get spread from market_spreads dict
            volume = getattr(market, 'volume', 0) or 0
            yes_ask = getattr(market, 'yes_ask', None)
            yes_bid = getattr(market, 'yes_bid', None)
            
            # Skip if missing required data
            if yes_ask is None or yes_bid is None:
                continue
            
            # Apply basic filters
            if not (spread > min_spread and volume > min_volume and spread < max_spread and 
                   yes_ask > min_price and yes_bid > min_price):
                continue
            
            # Filter by resolution date if specified
            if min_days_until_resolution is not None or max_days_until_resolution is not None:
                close_time = getattr(market, 'close_time', None)
                if close_time:
                    # Handle both datetime objects and string formats
                    if isinstance(close_time, str):
                        try:
                            # Try parsing ISO format
                            if close_time.endswith('Z'):
                                close_time = datetime.datetime.fromisoformat(close_time.replace('Z', '+00:00'))
                            else:
                                close_time = datetime.datetime.fromisoformat(close_time)
                        except:
                            continue
                    
                    # Calculate days until resolution
                    if isinstance(close_time, datetime.datetime):
                        if close_time.tzinfo is None:
                            # Assume UTC if no timezone info
                            close_time = close_time.replace(tzinfo=datetime.timezone.utc)
                        
                        days_until_resolution = (close_time - current_time).total_seconds() / 86400.0
                        
                        # Apply date filters
                        if min_days_until_resolution is not None and days_until_resolution < min_days_until_resolution:
                            continue
                        if max_days_until_resolution is not None and days_until_resolution > max_days_until_resolution:
                            continue
            
            filtered_opportunities.append(market)
        
        return filtered_opportunities

# execute a single market making trade for the market in market_id_list.  Contracts is the number of contracts to trade
    def trade_single(self, market_id, contracts):
        print("--- WARNING: trading with actual money ---")
        market = self.client.get_market(market_id)
        yes_bid = getattr(market, 'yes_bid', None)
        yes_ask = getattr(market, 'yes_ask', None)
        
        if yes_bid is None or yes_ask is None:
            print(f"Warning: No bid/ask prices available for market {market_id}")
            return
        
        # Get buy and sell prices using the shared function
        buy_price_cents, sell_price_cents = self.get_price(yes_bid, yes_ask)
        
        self.client.create_order(ticker=market_id,
                        side="yes",
                        action="buy",
                        count=contracts,
                        type="limit",
                        yes_price=buy_price_cents)
                        
        self.client.create_order(ticker=market_id,
                        side="yes",
                        action="sell",
                        count=contracts,
                        type="limit",
                        yes_price=sell_price_cents)

if __name__ == "__main__":
    mm = BasicMM(reserve_limit=10)
    mm.identify_market_opportunities(max_total=10000)
    print(f"\nTotal opportunities found: {len(mm.market_opportunities)}")
    if mm.market_opportunities:
        print("Trading...")
        mm.run_test()
        
        # Read and display orders that were placed
        # Find the most recent trade log file in logs/trade_logs directory
        log_dir = os.path.join(os.path.dirname(__file__), "..", "logs", "trade_logs")
        log_file = None
        
        if os.path.exists(log_dir):
            # Find the most recent trade log file
            log_files = [f for f in os.listdir(log_dir) if f.startswith("tradeLimitOrders_") and f.endswith(".log")]
            if log_files:
                # Sort by modification time, most recent first
                log_files.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
                log_file = os.path.join(log_dir, log_files[0])
                print(f"\nUsing most recent trade log: {log_files[0]}")
        
        if log_file and os.path.exists(log_file):
            print("\n" + "="*80)
            print("ORDERS PLACED:")
            print("="*80)
            
            # Read the last few lines (recent orders)
            with open(log_file, "r") as f:
                lines = f.readlines()
                # Get the last 20 lines (or all if less than 20)
                recent_lines = lines[-20:] if len(lines) > 20 else lines
                
                if recent_lines:
                    print(f"\nShowing last {len(recent_lines)} order(s):\n")
                    for line in recent_lines:
                        line = line.strip()
                        if line:
                            # Parse the log line: timestamp, market_id, side, price, order_id
                            parts = line.split(", ")
                            if len(parts) >= 4:
                                timestamp = parts[0]
                                market_id = parts[1]
                                side = parts[2]
                                price = parts[3]
                                order_id = parts[4] if len(parts) > 4 else "N/A"
                                print(f"  {side:4s} | Market: {market_id[:50]:50s} | Price: {price:6s} | Order ID: {order_id}")
                            else:
                                print(f"  {line}")
                else:
                    print("No orders found in log file.")
            print("="*80)
        else:
            print(f"\nNo order log file found at: {log_file}")
        