from apiSetup import KalshiAPI
from kalshi_python import Configuration, KalshiClient  
import datetime
import asyncio

class BasicMM:
    def __init__(self, reserve_limit = 10, demo=False):
        self.client = KalshiAPI().get_client(demo=demo)
        self.market_opportunities = []
        self.reserve_limit = reserve_limit # how much to keep in reserve
        self.demo = demo

    def get_markets(self, limit=1000):
        """Get markets with pagination to fetch more than 100 markets"""
        all_markets = []
        cursor = None
        
        while True:
            try:
                if cursor:
                    response = self.client.get_markets(cursor=cursor, limit=limit)
                else:
                    response = self.client.get_markets(limit=limit)
                
                if hasattr(response, 'markets'):
                    # Filter out markets with invalid status
                    valid_markets = []
                    for market in response.markets:
                        try:
                            # Try to access market properties to validate
                            _ = market.ticker
                            valid_markets.append(market)
                        except Exception:
                            # Skip invalid markets
                            continue
                    all_markets.extend(valid_markets)
                
                # Check if there are more pages
                if hasattr(response, 'cursor') and response.cursor:
                    cursor = response.cursor
                else:
                    break
                    
                # Safety check to prevent infinite loops
                if len(all_markets) >= limit:
                    break
                    
            except Exception as e:
                print(f"Error fetching markets: {e}")
                # Try to get markets without pagination as fallback
                try:
                    response = self.client.get_markets()
                    if hasattr(response, 'markets'):
                        all_markets.extend(response.markets)
                except Exception as fallback_error:
                    print(f"Fallback also failed: {fallback_error}")
                break
        
        print(f"Successfully fetched {len(all_markets)} valid markets")
        
        # Create a mock response object to maintain compatibility
        class MarketResponse:
            def __init__(self, markets):
                self.markets = markets
        
        return MarketResponse(all_markets)

    def get_market_trades(self, market_id):
        return self.client.get_market_trades(market_id)

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

    def identify_market_opportunities(self):
        markets_response = self.get_markets()
        markets = markets_response.markets if hasattr(markets_response, 'markets') else markets_response
        opportunities = []
        
        print(f"Analyzing {len(markets)} markets for opportunities...")
        
        for market in markets:
            # Calculate spread if not already available
            if not hasattr(market, 'spread'):
                # Calculate spread from bid/ask prices
                if hasattr(market, 'yes_bid') and hasattr(market, 'yes_ask'):
                    spread = market.yes_ask - market.yes_bid
                else:
                    spread = 0
            
            if spread > 0.03:
                opportunities.append(market)
        
        # Sort opportunities by spread (highest first)
        opportunities.sort(key=lambda x: getattr(x, 'spread', 0), reverse=True)
        self.market_opportunities = opportunities
        
        if len(opportunities) == 0:
            print("No opportunities found with spreads > 0.03")
            print("This is normal when markets have no active trading or tight spreads")
        else:
            print(f"Found {len(opportunities)} opportunities with spreads > 0.03")

    def trade(self, market_id_list, bankroll):
        # calculate price
        for i in range(len(market_id_list)):
            if bankroll > 0:
                market_id = market_id_list[i]
                buy_price = self.client.get_best_bid(market_id)-0.01
                sell_price = self.client.get_best_ask(market_id)+0.01
                # How to decide how much to buy/sell?
                buy_order = self.client.create_order(market_id, "buy", 1, 0.03)
                sell_order = self.client.create_order(market_id, "sell", 1, 0.03)

                # check both were created
                if not buy_order or not sell_order:
                    print(f"Failed to create buy or sell order for market {market_id}")

                    if buy_order:
                        self.client.cancel_order(buy_order.id)
                    if sell_order:
                        self.client.cancel_order(sell_order.id)

                # Log
                with open("tradeLimitOrders.log", "a") as f:
                    f.write(f"{market_id}, {buy_price}, {sell_price}\n, {datetime.now()}\n")
            
                
    async def run(self):
        bankroll = self.calculate_remaining_balance() - self.reserve_limit
        while bankroll > 0:
            self.identify_market_opportunities()
            if len(self.market_opportunities) > 0:
                self.trade(self.market_opportunities, bankroll)
            else:
                print("No trading opportunities available - waiting for next cycle")
            await asyncio.sleep(1) # runs every second

    def run(self): # non async version
        bankroll = self.calculate_remaining_balance() - self.reserve_limit
        if bankroll > 0:
            self.identify_market_opportunities()
            if len(self.market_opportunities) > 0:
                self.trade(self.market_opportunities, bankroll)
            else:
                print("No trading opportunities available - skipping trade execution")

