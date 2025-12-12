import sys
import os
import csv
import requests
import json

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
        self.last_cursor = None  # Store the last cursor for pagination continuation

    def get_markets(self, max_total=100000, page_size=100, status="open", start_cursor=None):
        """Fetch markets with robust pagination.

        Args:
            max_total: Maximum number of markets to collect. If None, fetches all available markets.
            page_size: Number of markets per request (server typically caps at 100)
            status: Market status filter (e.g., "open", "active", "closed")
            start_cursor: Optional cursor to start from (for continuing pagination)
                          If None, starts from the beginning
        
        Returns:
            MarketResponse object with markets list
        """
        all_markets = []
        # Use provided cursor, or None to start from beginning
        cursor = start_cursor
        page_count = 0
        effective_page_size = min(page_size, 100)

        consecutive_errors = 0
        max_consecutive_errors = 10  # Allow more errors before giving up
        skipped_markets = 0
        
        # Get base URL for raw HTTP requests (fallback when SDK fails)
        config = self.client.api_client.configuration
        base_url = config.host

        while True:
            try:
                params = {"limit": effective_page_size}
                if status is not None:
                    params["status"] = status
                if cursor:
                    params["cursor"] = cursor

                # Try using SDK first
                try:
                    response = self.client.get_markets(**params)
                    consecutive_errors = 0  # Reset error counter on success

                    if hasattr(response, 'markets') and response.markets:
                        all_markets.extend(response.markets)
                        page_count += 1
                        # Print progress every 10 pages
                        if page_count % 10 == 0:
                            print(f"Fetched {len(all_markets)} markets so far (page {page_count}, {skipped_markets} markets skipped due to errors)...")
                    
                        # Get cursor for next page
                        if hasattr(response, 'cursor') and response.cursor:
                            cursor = response.cursor
                            self.last_cursor = cursor
                        else:
                            self.last_cursor = None
                            break
                    else:
                        # No more markets
                        self.last_cursor = None
                        break

                except Exception as api_error:
                    # Handle validation errors from API (e.g., invalid market statuses like 'inactive')
                    error_str = str(api_error)
                    if "validation error" in error_str.lower() or "must be one of enum values" in error_str.lower():
                        consecutive_errors += 1
                        print(f"Warning: Validation error on page {page_count + 1} (invalid market data). Using raw HTTP to extract cursor and continue...")
                        
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"Too many consecutive validation errors ({consecutive_errors}). Stopping pagination.")
                            break

                        # Use raw HTTP request to get JSON and extract cursor, then filter invalid markets
                        try:
                            # Build URL for raw HTTP request
                            url = f"{base_url}/markets"
                            headers = {}
                            
                            # Add authentication if available
                            if hasattr(config, 'api_key_id') and config.api_key_id:
                                # Kalshi API might need auth headers - check if needed
                                pass
                            
                            http_params = {"limit": effective_page_size}
                            if status is not None:
                                http_params["status"] = status
                            if cursor:
                                http_params["cursor"] = cursor
                            
                            # Make raw HTTP request
                            http_response = requests.get(url, params=http_params, headers=headers, timeout=30)
                            http_response.raise_for_status()
                            raw_data = http_response.json()
                            
                            # Extract cursor from raw response
                            if 'cursor' in raw_data and raw_data['cursor']:
                                cursor = raw_data['cursor']
                                self.last_cursor = cursor
                            else:
                                self.last_cursor = None
                                break

                            # Try to parse markets from raw data, filtering out invalid ones
                            if 'markets' in raw_data and raw_data['markets']:
                                valid_statuses = {'initialized', 'active', 'closed', 'settled', 'determined'}
                                valid_markets_count = 0
                                
                                for market_data in raw_data['markets']:
                                    # Check if market has valid status before trying to deserialize
                                    market_status = market_data.get('status', '')
                                    if market_status not in valid_statuses:
                                        skipped_markets += 1
                                        continue
                                    
                                    # Try to create market object from valid data
                                    try:
                                        # Use SDK to create market object from dict
                                        from kalshi_python.models.market import Market
                                        market = Market.from_dict(market_data)
                                        all_markets.append(market)
                                        valid_markets_count += 1
                                    except Exception as market_error:
                                        skipped_markets += 1
                                        continue
                                
                                if valid_markets_count > 0:
                                    page_count += 1
                                    if page_count % 10 == 0:
                                        print(f"Fetched {len(all_markets)} markets so far (page {page_count}, {skipped_markets} markets skipped due to errors)...")
                                
                                # Continue to next iteration with updated cursor
                                continue
                            else:
                                # No more markets
                                self.last_cursor = None
                                break

                        except Exception as http_error:
                            print(f"Raw HTTP request also failed: {http_error}")
                            # Can't continue without cursor
                            break
                    else:
                        # Re-raise if it's a different type of error
                        raise

                # Stop if we've reached the requested total (unless max_total is None, meaning fetch all)
                if max_total is not None and len(all_markets) >= max_total:
                    print(f"Reached requested limit of {max_total} markets")
                    break

            except Exception as e:
                print(f"Error fetching markets on page {page_count + 1}: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: single request without pagination
                try:
                    fallback_params = {"limit": min(page_size, 100)}
                    if status is not None:
                        fallback_params["status"] = status
                    if cursor:
                        fallback_params["cursor"] = cursor
                    response = self.client.get_markets(**fallback_params)
                    if hasattr(response, 'markets') and response.markets:
                        all_markets.extend(response.markets)
                        # Update cursor if available
                        if hasattr(response, 'cursor') and response.cursor:
                            self.last_cursor = response.cursor
                except Exception as fallback_error:
                    print(f"Fallback also failed: {fallback_error}")
                break

        if max_total is None:
            print(f"Successfully fetched ALL {len(all_markets)} available markets from Kalshi")
        else:
            print(f"Successfully fetched {len(all_markets)} valid markets")
        if self.last_cursor:
            print(f"Last cursor stored. Use get_next_markets() to continue from here.")

        class MarketResponse:
            def __init__(self, markets):
                self.markets = markets

        return MarketResponse(all_markets)
    
    def get_next_markets(self, max_total=10000, page_size=100, status="open"):
        """
        Get the next batch of markets continuing from the last cursor.
        This is useful when you've already fetched markets and want to continue.

        Args:
            max_total: Maximum number of markets to collect in this batch. If None, fetches all remaining markets.
            page_size: Number of markets per request
            status: Market status filter
        
        Returns:
            MarketResponse object with markets list
        """
        if self.last_cursor is None:
            print("No previous cursor found. Starting from the beginning.")
        else:
            print(f"Continuing from cursor: {self.last_cursor[:50]}..." if len(str(self.last_cursor)) > 50 else f"Continuing from cursor: {self.last_cursor}")
        
        return self.get_markets(max_total=max_total, page_size=page_size, status=status, start_cursor=self.last_cursor)
    
    def reset_cursor(self):
        """Reset the stored cursor to start from the beginning next time."""
        self.last_cursor = None
        print("Cursor reset. Next get_markets() call will start from the beginning.")

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

    def identify_market_opportunities(self, max_total=100000, continue_from_last=False):
        """
        Identify market opportunities from fetched markets.
        
        Args:
            max_total: Maximum number of markets to fetch and analyze. If None, fetches all available markets.
            continue_from_last: If True, continue from last cursor instead of starting from beginning
        """
        start_time = time.perf_counter()
        
        if continue_from_last:
            print("Continuing from last cursor position...")
            markets_response = self.get_next_markets(max_total=max_total, page_size=100, status="open")
        else:
            if max_total is None:
                print("Fetching ALL available markets from Kalshi (this may take a while)...")
        markets_response = self.get_markets(max_total=max_total, page_size=100, status="open")
        
        markets = markets_response.markets if hasattr(markets_response, 'markets') else markets_response
        opportunities = []  # Will store tuples of (market, spread)
        market_spreads = {}  # Dictionary to map market ticker to spread for easy access
        
        print(f"Analyzing {len(markets)} markets for opportunities...")
        
        for market in markets:
            # Calculate spread from bid/ask prices
            spread = 0
            if hasattr(market, 'yes_bid') and hasattr(market, 'yes_ask') and market.yes_bid is not None and market.yes_ask is not None:
                # Prices might be in cents (0-100) or probability (0-1)
                # Convert to probability format for consistency
                if market.yes_bid > 1 or market.yes_ask > 1:
                    # Prices are in cents, convert to probability
                    spread = (market.yes_ask - market.yes_bid) / 100.0
                else:
                    # Prices are already in probability format
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
            marketID: Market ticker ID string
            
        Returns:
            Tuple of (buy_price_cents, sell_price_cents) both in range 1-99, or (None, None) on error
        """
        try:
            # First, try to get the market from our cached opportunities if available
            # This ensures we use the same market object that has the data
            market = None
            if hasattr(self, 'market_opportunities') and self.market_opportunities:
                for m in self.market_opportunities:
                    market_ticker = getattr(m, 'ticker', None) or (m if isinstance(m, str) else None)
                    if market_ticker == marketID:
                        market = m
                        break
            
            # If not found in cache, fetch from API
            if market is None:
                market_response = self.client.get_market(marketID)
                if market_response is None:
                    print(f"Error: Failed to get market data for {marketID}")
                    return None, None
                
                # Handle GetMarketResponse object - extract the market from it
                if hasattr(market_response, 'market') and market_response.market is not None:
                    market = market_response.market
                elif hasattr(market_response, 'yes_bid'):  # If it's already a Market object
                    market = market_response
                else:
                    print(f"Error: Unexpected market response format for {marketID}")
                    return None, None
            
            # Debug: Print what we actually got
            print(f"DEBUG get_price for {marketID}:")
            print(f"  Market type: {type(market)}")
            print(f"  Has yes_bid attr: {hasattr(market, 'yes_bid')}")
            print(f"  Has yes_ask attr: {hasattr(market, 'yes_ask')}")
            if hasattr(market, 'yes_bid'):
                print(f"  yes_bid value: {market.yes_bid} (type: {type(market.yes_bid)})")
            if hasattr(market, 'yes_ask'):
                print(f"  yes_ask value: {market.yes_ask} (type: {type(market.yes_ask)})")
            
            # Try to get values - use the same pattern that works in identify_market_opportunities
            yes_bid = None
            yes_ask = None
            
            # Method 1: Direct attribute access (like in identify_market_opportunities line 179)
            if hasattr(market, 'yes_bid') and hasattr(market, 'yes_ask'):
                try:
                    yes_bid = market.yes_bid
                    yes_ask = market.yes_ask
                except AttributeError:
                    pass
            
            # Method 2: getattr fallback
            if yes_bid is None:
                yes_bid = getattr(market, 'yes_bid', None)
            if yes_ask is None:
                yes_ask = getattr(market, 'yes_ask', None)

            # Method 3: Try dictionary access if it's a dict
            if yes_bid is None and isinstance(market, dict):
                yes_bid = market.get('yes_bid')
            if yes_ask is None and isinstance(market, dict):
                yes_ask = market.get('yes_ask')
            
            print(f"  Final yes_bid: {yes_bid}, yes_ask: {yes_ask}")
            
            # Handle case where values might be 0 (falsy but not None)
            # 0 is not a valid price, so treat it as missing data
            if yes_bid is None or yes_ask is None or yes_bid == 0 or yes_ask == 0:
                print(f"Warning: No bid/ask prices available for market {marketID} (yes_bid={yes_bid}, yes_ask={yes_ask})")
                # Print all non-callable attributes for debugging
                print(f"  All market attributes:")
                for attr in dir(market):
                    if not attr.startswith('_') and not callable(getattr(market, attr, None)):
                        try:
                            value = getattr(market, attr)
                            print(f"    {attr} = {value}")
                        except:
                            pass
                return None, None

            # Convert to integers (prices are typically in cents, 0-100 range)
            try:
                base_buy_price = int(yes_bid)
                base_sell_price = int(yes_ask)
            except (ValueError, TypeError) as e:
                print(f"Error: Invalid price format for market {marketID} (yes_bid={yes_bid}, yes_ask={yes_ask}): {e}")
                return None, None
            
            # Validate price range
            if not (0 <= base_buy_price <= 100) or not (0 <= base_sell_price <= 100):
                print(f"Warning: Prices out of valid range for market {marketID} (bid={base_buy_price}, ask={base_sell_price})")
                return None, None
            
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
            
        except Exception as e:
            print(f"Error in get_price for market {marketID}: {e}")
            import traceback
            traceback.print_exc()
            return None, None

# executes market making trades for all markets in market_id_list.  Bankroll is the amount of money to be used.
    def trade(self, market_id_list, bankroll, stop_loss=0): 
        print("--- WARNING: trading with actual money ---")
        print(f"\n{'='*80}")
        print(f"TRADING SESSION STARTED")
        print(f"{'='*80}")
        print(f"Total markets to process: {len(market_id_list)}")
        print(f"Starting bankroll: ${bankroll/100:.2f}")
        
        # Print list of markets to be traded
        print(f"\nMarkets to trade:")
        for i, market in enumerate(market_id_list, 1):
            market_id = market.ticker if hasattr(market, 'ticker') else market
            print(f"  {i}. {market_id}")
        
        print(f"{'='*80}\n")
        
        # Track remaining bankroll as we place orders
        remaining_bankroll = bankroll
        successfully_traded_markets = []  # Track markets where both orders were placed
        failed_markets = []  # Track markets that failed
        
        for i in range(len(market_id_list)):
            # Check if we have enough bankroll before processing this market
            if remaining_bankroll <= 0:
                print(f"Insufficient bankroll. Stopping after {i} markets. Remaining: ${remaining_bankroll:.2f}")
                break
                
            market = market_id_list[i]
            # Handle both market objects and market ID strings
            market_id = market.ticker if hasattr(market, 'ticker') else market
            
            
            buy_price_cents, sell_price_cents = self.get_price(market_id)
            sell_price_cents = 100 - sell_price_cents
            
            # Check if get_price returned None values (error case)
            if buy_price_cents is None or sell_price_cents is None:
                print(f"Error: Could not get prices for market {market_id}. Skipping this market.")
                continue
            
            # Note: Prices are stored in probability format (0-1) for logging, but API uses cents (1-99)
            buy_price_prob = buy_price_cents / 100.0
            sell_price_prob = sell_price_cents / 100.0

            # Check if we have enough bankroll for both orders
            # Buy orders cost money (buying yes contracts)
            # Sell orders also cost money (selling yes = buying no contracts)
            buy_order = None
            sell_order = None
            
            # Calculate how many contracts we can afford with the available bankroll
            # Cost per contract pair = buy_price + sell_price (need both for market making)
            cost_per_contract_pair = buy_price_cents + sell_price_cents
            print(f"Buy price: {buy_price_cents}, Sell price: {sell_price_cents}")
            print(f"Cost per contract pair: {cost_per_contract_pair}")
            
            if cost_per_contract_pair <= 0:
                print(f"Error: Invalid prices for market {market_id} (buy: {buy_price_cents}¢, sell: {sell_price_cents}¢). Skipping.")
                continue
            
            # Calculate maximum number of contracts we can afford
            # Use floor division to ensure we don't exceed bankroll
            max_contracts = remaining_bankroll // cost_per_contract_pair
            
            if max_contracts <= 0:
                print(f"Insufficient bankroll for market {market_id}. Need at least ${cost_per_contract_pair/100:.2f} per contract pair (buy: {buy_price_cents}¢ + sell: {sell_price_cents}¢), have ${remaining_bankroll/100:.2f}")
                continue
            
            # Use the maximum number of contracts we can afford
            contracts_per_order = max_contracts
            
            # Calculate total cost: price per contract * number of contracts for both buy and sell
            buy_order_total_cost = buy_price_cents * contracts_per_order
            sell_order_total_cost = sell_price_cents * contracts_per_order
            total_cost = buy_order_total_cost + sell_order_total_cost
            
            print(f"Calculated contracts for {market_id}: {contracts_per_order} contracts (cost: ${total_cost/100:.2f}, remaining bankroll: ${remaining_bankroll/100:.2f})")
            
            # API expects yes_price in cents (1-99), not probability format
            # Keep prices in cents as returned by get_price
            
            # Place buy order (buying yes contracts)
            if remaining_bankroll >= buy_order_total_cost:
                try:
                    buy_order = self.client.create_order(
                        ticker=market_id,
                        side="yes",
                        action="buy",
                        count=contracts_per_order,
                        type="limit",
                        yes_price=buy_price_cents  # API expects cents (1-99), not probability
                    )
                    # Subtract from bankroll if order was successfully created
                    # Total cost = price per contract * number of contracts
                    if buy_order:
                        remaining_bankroll -= buy_order_total_cost
                        # Try to get order ID from various possible attributes
                        order_id = None
                        if hasattr(buy_order, 'order_id'):
                            order_id = buy_order.order_id
                        elif hasattr(buy_order, 'id'):
                            order_id = buy_order.id
                        elif hasattr(buy_order, 'orderId'):
                            order_id = buy_order.orderId
                        elif isinstance(buy_order, dict):
                            order_id = buy_order.get('order_id') or buy_order.get('id') or buy_order.get('orderId')
                        
                        print(f"✓ Buy order placed for {market_id}: {contracts_per_order} contracts @ {buy_price_cents}¢ each (total: ${buy_order_total_cost/100:.2f}). Remaining bankroll: ${remaining_bankroll/100:.2f}")
                        if order_id:
                            print(f"  Order ID: {order_id}")
                        else:
                            # Debug: print order object structure
                            print(f"  Order object type: {type(buy_order)}")
                            if hasattr(buy_order, '__dict__'):
                                print(f"  Order attributes: {list(buy_order.__dict__.keys())}")
                    else:
                        print(f"⚠ Buy order returned None for {market_id}")
                        buy_order = None
                except Exception as e:
                    print(f"✗ Error creating buy order for {market_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    buy_order = None
            else:
                print(f"Insufficient bankroll for buy order on {market_id}. Need ${buy_order_total_cost/100:.2f} ({contracts_per_order} contracts @ {buy_price_cents}¢ each), have ${remaining_bankroll/100:.2f}")
            
            # Place sell order (selling yes = buying no contracts, also costs money)
            if remaining_bankroll >= sell_order_total_cost:
                try:
                    sell_order = self.client.create_order(
                        ticker=market_id,
                        side="yes",
                        action="sell",
                        count=contracts_per_order,
                        type="limit",
                        yes_price=100-sell_price_cents  # API expects cents (1-99), not probability
                    )
                    # Subtract from bankroll if order was successfully created
                    # Total cost = price per contract * number of contracts
                    if sell_order:
                        remaining_bankroll -= sell_order_total_cost
                        # Try to get order ID from various possible attributes
                        order_id = None
                        if hasattr(sell_order, 'order_id'):
                            order_id = sell_order.order_id
                        elif hasattr(sell_order, 'id'):
                            order_id = sell_order.id
                        elif hasattr(sell_order, 'orderId'):
                            order_id = sell_order.orderId
                        elif isinstance(sell_order, dict):
                            order_id = sell_order.get('order_id') or sell_order.get('id') or sell_order.get('orderId')
                        
                        print(f"✓ Sell order placed for {market_id}: {contracts_per_order} contracts @ {sell_price_cents}¢ each (total: ${sell_order_total_cost/100:.2f}). Remaining bankroll: ${remaining_bankroll/100:.2f}")
                        if order_id:
                            print(f"  Order ID: {order_id}")
                        else:
                            # Debug: print order object structure
                            print(f"  Order object type: {type(sell_order)}")
                            if hasattr(sell_order, '__dict__'):
                                print(f"  Order attributes: {list(sell_order.__dict__.keys())}")
                    else:
                        print(f"⚠ Sell order returned None for {market_id}")
                        sell_order = None
                except Exception as e:
                    print(f"✗ Error creating sell order for {market_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    sell_order = None
            else:
                print(f"Insufficient bankroll for sell order on {market_id}. Need ${sell_order_total_cost/100:.2f} ({contracts_per_order} contracts @ {sell_price_cents}¢ each), have ${remaining_bankroll/100:.2f}")

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
            
            # Log order details (log prices in probability format for consistency with existing logs)
            buy_price_prob = buy_price_cents / 100.0
            sell_price_prob = sell_price_cents / 100.0
            with open(log_file, "a") as f:
                entry_timestamp = datetime.datetime.now().isoformat()
                if buy_order:
                    buy_order_id = getattr(buy_order, 'order_id', getattr(buy_order, 'id', 'N/A'))
                    f.write(f"{entry_timestamp}, {market_id}, BUY, {buy_price_prob}, {buy_order_id}\n")
                if sell_order:
                    sell_order_id = getattr(sell_order, 'order_id', getattr(sell_order, 'id', 'N/A'))
                    f.write(f"{entry_timestamp}, {market_id}, SELL, {sell_price_prob}, {sell_order_id}\n")
            
            # Check both were created
            if not buy_order or not sell_order:
                print(f"⚠ Failed to create buy or sell order for market {market_id}")
                failed_markets.append(market_id)

                # Cancel any partial orders if one failed
                try:
                    if buy_order:
                            order_id = (getattr(buy_order, 'order_id', None) or 
                                    getattr(buy_order, 'id', None) or 
                                    getattr(buy_order, 'orderId', None))
                            if order_id:
                                self.client.cancel_order(order_id)
                                print(f"  Cancelled buy order {order_id}")
                    if sell_order:
                            order_id = (getattr(sell_order, 'order_id', None) or 
                                    getattr(sell_order, 'id', None) or 
                                    getattr(sell_order, 'orderId', None))
                            if order_id:
                                self.client.cancel_order(order_id)
                                print(f"  Cancelled sell order {order_id}")
                except Exception as cancel_error:
                    print(f"  Warning: Could not cancel partial orders: {cancel_error}")
            else:
                # Both orders successfully placed
                successfully_traded_markets.append(market_id)
                buy_order_id = (getattr(buy_order, 'order_id', None) or 
                               getattr(buy_order, 'id', None) or 
                               getattr(buy_order, 'orderId', None) or 'N/A')
                sell_order_id = (getattr(sell_order, 'order_id', None) or 
                                getattr(sell_order, 'id', None) or 
                                getattr(sell_order, 'orderId', None) or 'N/A')
                print(f"✓ Successfully placed both orders for {market_id}")
                print(f"  Buy order @ {buy_price_cents}¢: {buy_order_id}")
                print(f"  Sell order @ {sell_price_cents}¢: {sell_order_id}")
                
                # Create stop loss file if stop_loss is specified
                if stop_loss > 0:
                    try:
                        # Create Stoploss directory
                        stoploss_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Stoploss")
                        os.makedirs(stoploss_dir, exist_ok=True)
                        
                        # Calculate stop loss prices
                        # Buy stop loss: if ask price exceeds (sell_price_cents + stop_loss), buy to cover
                        # Sell stop loss: if bid price drops below (buy_price_cents - stop_loss), sell to limit loss
                        buy_stop_loss_price = sell_price_cents + stop_loss
                        sell_stop_loss_price = buy_price_cents - stop_loss
                        
                        # Clamp prices to valid range (1-99)
                        buy_stop_loss_price = max(1, min(99, buy_stop_loss_price))
                        sell_stop_loss_price = max(1, min(99, sell_stop_loss_price))
                        
                        # Create stop loss data
                        stoploss_data = {
                            'market_id': market_id,
                            'stop_loss_cents': stop_loss,
                            'buy_price_cents': buy_price_cents,
                            'sell_price_cents': sell_price_cents,
                            'buy_stop_loss_price': buy_stop_loss_price,
                            'sell_stop_loss_price': sell_stop_loss_price,
                            'contracts': contracts_per_order,
                            'buy_order_id': buy_order_id if buy_order_id != 'N/A' else None,
                            'sell_order_id': sell_order_id if sell_order_id != 'N/A' else None,
                            'created_at': datetime.datetime.now().isoformat(),
                            'active': True
                        }
                        
                        # Write to file (market name as filename)
                        stoploss_file = os.path.join(stoploss_dir, f"{market_id}.json")
                        with open(stoploss_file, 'w') as f:
                            json.dump(stoploss_data, f, indent=2)
                        
                        print(f"✓ Stop loss file created for {market_id}")
                        print(f"  Buy stop loss trigger: {buy_stop_loss_price}¢ (if ask > {sell_price_cents + stop_loss}¢)")
                        print(f"  Sell stop loss trigger: {sell_stop_loss_price}¢ (if bid < {buy_price_cents - stop_loss}¢)")
                    except Exception as e:
                        print(f"⚠ Error creating stop loss file for {market_id}: {e}")
                        import traceback
                        traceback.print_exc()
        
        # Print summary of trading session
        print(f"\n{'='*80}")
        print(f"TRADING SESSION SUMMARY")
        print(f"{'='*80}")
        print(f"Successfully traded markets: {len(successfully_traded_markets)}")
        if successfully_traded_markets:
            print(f"\nMarkets with both orders placed:")
            for market_id in successfully_traded_markets:
                print(f"  ✓ {market_id}")
        
        if failed_markets:
            print(f"\nFailed markets: {len(failed_markets)}")
            for market_id in failed_markets:
                print(f"  ✗ {market_id}")
        
        print(f"\nRemaining bankroll: ${remaining_bankroll/100:.2f}")
        print(f"Total spent: ${(bankroll - remaining_bankroll)/100:.2f}")
        print(f"{'='*80}\n")
            
                
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
            self.market_opportunities = self.filter_market_opportunities()
            if len(self.market_opportunities) > 0:
                self.trade(self.market_opportunities, bankroll)
            else:
                print("No trading opportunities available - skipping trade execution")

    def run_test(self): # test one limit order placement
        if (len(self.market_opportunities) > 0):
            self.market_opportunities = self.filter_market_opportunities()
            self.trade(self.market_opportunities, 1000)
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
            # Get spread from market_spreads dict, or calculate it if not available
            spread = self.get_market_spread(market)
            volume = getattr(market, 'volume', 0) or 0
            yes_ask = getattr(market, 'yes_ask', None)
            yes_bid = getattr(market, 'yes_bid', None)
            
            # Skip if missing required data
            if yes_ask is None or yes_bid is None:
                continue
            
            # If spread not in dictionary, calculate it from bid/ask
            if spread == 0:
                # Calculate spread from bid/ask prices (convert from cents to probability if needed)
                # Prices might be in cents (0-100) or probability (0-1)
                if yes_bid > 1 or yes_ask > 1:
                    # Prices are in cents, convert to probability
                    spread = (yes_ask - yes_bid) / 100.0
                else:
                    # Prices are already in probability format
                    spread = yes_ask - yes_bid
            
            # Normalize prices for comparison (convert to probability if in cents)
            yes_bid_prob = yes_bid / 100.0 if (yes_bid > 1) else yes_bid
            yes_ask_prob = yes_ask / 100.0 if (yes_ask > 1) else yes_ask
            
            # Apply basic filters (all comparisons in probability format)
            if not (spread > min_spread and volume > min_volume and spread < max_spread and 
                   yes_ask_prob > min_price and yes_bid_prob > min_price):
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
        
        # Get buy and sell prices using the shared function (pass market_id, not yes_bid/yes_ask)
        buy_price_cents, sell_price_cents = self.get_price(market_id)
        
        # Check if get_price returned None values (error case)
        if buy_price_cents is None or sell_price_cents is None:
            print(f"Error: Could not get prices for market {market_id}. Cannot place orders.")
            return
        
        # API expects yes_price in cents (1-99), not probability format
        # Keep prices in cents as returned by get_price
        
        buy_order = self.client.create_order(
            ticker=market_id,
                        side="yes",
                        action="buy",
                        count=contracts,
                        type="limit",
            yes_price=buy_price_cents  # API expects cents (1-99), not probability
        )
        print(f"Buy order placed: {contracts} contracts @ {buy_price_cents}¢")
        if buy_order and hasattr(buy_order, 'order_id'):
            print(f"  Order ID: {buy_order.order_id}")
                        
        sell_order = self.client.create_order(
            ticker=market_id,
                        side="yes",
                        action="sell",
                        count=contracts,
                        type="limit",
            yes_price=sell_price_cents  # API expects cents (1-99), not probability
        )
        print(f"Sell order placed: {contracts} contracts @ {sell_price_cents}¢")
        if sell_order and hasattr(sell_order, 'order_id'):
            print(f"  Order ID: {sell_order.order_id}")

if __name__ == "__main__":
    mm = BasicMM(reserve_limit=10)
    
    # Identify market opportunities from ALL markets on Kalshi
    # Set max_total=None to fetch all available markets (uses pagination automatically)
    print("Identifying market opportunities from ALL markets on Kalshi...")
    print("This will use pagination to fetch all available markets (may take several minutes)...")
    mm.identify_market_opportunities(max_total=None)  # None = fetch all markets
    print(f"\nTotal markets analyzed: {len(mm.market_opportunities) if hasattr(mm, 'market_opportunities') else 0}")
    print(f"Total opportunities identified: {len(mm.market_opportunities)}")
        
    # Filter for markets with good volume and spread of at least 3 cents (0.03)
    print("\nFiltering for markets with good volume and spread >= 3 cents...")
    filtered = mm.filter_market_opportunities(
        min_spread=0.03,  # 3 cents spread minimum
        min_volume=1000,  # Good volume threshold
        max_spread=0.1,   # Maximum spread
        min_price=0.1     # Minimum price
    )
    
    print(f"\n{'='*100}")
    print(f"MARKET OPPORTUNITIES (Volume >= 1000, Spread >= 3 cents)")
    print(f"{'='*100}")
    print(f"Total filtered opportunities: {len(filtered)}\n")
    
    if filtered:
        # Print header
        print(f"{'Market ID':<50} {'Title':<40} {'Spread':<10} {'Volume':<12} {'Yes Bid':<10} {'Yes Ask':<10}")
        print("-" * 100)
        
        # Sort by spread (highest first) for better visibility
        sorted_opportunities = sorted(filtered, key=lambda m: mm.get_market_spread(m) or 0, reverse=True)
        
        for market in sorted_opportunities:
            market_id = getattr(market, 'ticker', None) or getattr(market, 'market_id', 'N/A')
            title = getattr(market, 'title', None) or getattr(market, 'question', 'N/A')
            
            # Get spread
            spread = mm.get_market_spread(market)
            if spread == 0:
                # Calculate from bid/ask
                yes_bid = getattr(market, 'yes_bid', None)
                yes_ask = getattr(market, 'yes_ask', None)
                if yes_bid is not None and yes_ask is not None:
                    if yes_bid > 1 or yes_ask > 1:
                        spread = (yes_ask - yes_bid) / 100.0
                    else:
                        spread = yes_ask - yes_bid
            
            volume = getattr(market, 'volume', 0) or 0
            yes_bid = getattr(market, 'yes_bid', None)
            yes_ask = getattr(market, 'yes_ask', None)
            
            # Format prices
            yes_bid_str = f"{yes_bid:.2f}¢" if yes_bid and yes_bid > 1 else f"{yes_bid*100:.2f}¢" if yes_bid else "N/A"
            yes_ask_str = f"{yes_ask:.2f}¢" if yes_ask and yes_ask > 1 else f"{yes_ask*100:.2f}¢" if yes_ask else "N/A"
            spread_str = f"{spread*100:.2f}¢" if spread else "N/A"
            
            # Truncate title if too long
            title_display = title[:37] + "..." if len(title) > 40 else title
            market_id_display = market_id[:47] + "..." if len(market_id) > 50 else market_id
            
            print(f"{market_id_display:<50} {title_display:<40} {spread_str:<10} {volume:<12,} {yes_bid_str:<10} {yes_ask_str:<10}")
        
        print(f"\n{'='*100}")
    else:
        print("No market opportunities found matching the criteria (Volume >= 1000, Spread >= 3 cents)")
        print(f"{'='*100}")