import json
import argparse
from typing import List, Dict, Any, Optional
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from Setup.apiSetup import KalshiAPI

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

def setup_client():
    """Setup and return a Kalshi client using apiSetup."""
    api = KalshiAPI()
    return api.get_client()

def get_markets(client, limit: Optional[int] = None, status: Optional[str] = None, max_markets: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get markets from Kalshi API with pagination support.
    
    Note: status parameter is ignored due to SDK validation issues.
    All markets are fetched and can be filtered client-side.
    """
    try:
        all_markets = []
        cursor = None
        batch_size = 1000  # Maximum per request
        
        print(f"Fetching markets from Kalshi...")
        
        while True:
            # Prepare parameters - don't pass status due to SDK enum validation issues
            params = {
                "limit": min(batch_size, limit) if limit else batch_size
            }
            
            if cursor:
                params["cursor"] = cursor
            
            # Get markets batch
            response = client.get_markets(**params)
            
            if not response.markets:
                break
            
            # Convert market objects to dictionaries
            for market in response.markets:
                market_dict = {
                    "ticker": market.ticker,
                    "title": market.title,
                    "status": market.status,
                    "close_time": market.close_time,
                    "open_time": market.open_time,
                    "yes_bid": market.yes_bid,
                    "yes_ask": market.yes_ask,
                    "no_bid": market.no_bid,
                    "no_ask": market.no_ask,
                    "volume": market.volume,
                    "volume_24h": market.volume_24h,
                    "last_price": market.last_price
                }
                
                # Add optional fields if they exist and are not empty
                event_ticker = getattr(market, 'event_ticker', '')
                if event_ticker:
                    market_dict["event_ticker"] = event_ticker
                    
                subtitle = getattr(market, 'subtitle', '')
                if subtitle:
                    market_dict["subtitle"] = subtitle
                    
                series_ticker = getattr(market, 'series_ticker', '')
                if series_ticker:
                    market_dict["series_ticker"] = series_ticker
                all_markets.append(market_dict)
            
            print(f"Fetched {len(all_markets)} markets so far...")
            
            # Check if we have a cursor for next page
            if hasattr(response, 'cursor') and response.cursor:
                cursor = response.cursor
            else:
                break
            
            # Check if we've reached the desired limit
            if limit and len(all_markets) >= limit:
                all_markets = all_markets[:limit]
                break
            
            # Check if we've reached the max_markets limit
            if max_markets and len(all_markets) >= max_markets:
                all_markets = all_markets[:max_markets]
                break
        
        print(f"Total markets fetched: {len(all_markets)}")
        return all_markets
        
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def calculate_spread(market: Dict[str, Any]) -> Dict[str, float]:
    """Calculate the spread for a market using bid/ask prices."""
    try:
        # Get bid and ask prices (in cents)
        yes_bid = market.get("yes_bid", 0)
        yes_ask = market.get("yes_ask", 0)
        no_bid = market.get("no_bid", 0)
        no_ask = market.get("no_ask", 0)
        
        # Calculate spreads for both yes and no contracts
        yes_spread = yes_ask - yes_bid if yes_ask and yes_bid else 0
        no_spread = no_ask - no_bid if no_ask and no_bid else 0
        
        # Use the larger spread as the market spread
        absolute_spread = max(yes_spread, no_spread)
        
        # Calculate percentage spread based on the contract with the larger spread
        if yes_spread >= no_spread and yes_bid and yes_ask:
            mid_price = (yes_bid + yes_ask) / 2
            percentage_spread = (yes_spread / mid_price * 100) if mid_price > 0 else 0
        elif no_bid and no_ask:
            mid_price = (no_bid + no_ask) / 2
            percentage_spread = (no_spread / mid_price * 100) if mid_price > 0 else 0
        else:
            percentage_spread = 0
        
        return {
            "absolute_spread": absolute_spread,
            "percentage_spread": percentage_spread,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "yes_spread": yes_spread,
            "no_spread": no_spread
        }
    except Exception as e:
        print(f"Error calculating spread for market {market.get('ticker', 'unknown')}: {e}")
        return {
            "absolute_spread": 0,
            "percentage_spread": 0,
            "yes_bid": 0,
            "yes_ask": 0,
            "no_bid": 0,
            "no_ask": 0,
            "yes_spread": 0,
            "no_spread": 0
        }

def sort_markets_by_spread(markets: List[Dict[str, Any]], sort_by: str = "percentage") -> List[Dict[str, Any]]:
    """Sort markets by spread (highest first)."""
    markets_with_spread = []
    
    for market in markets:
        spread_data = calculate_spread(market)
        
        # Add spread information to market data
        market_with_spread = {
            **market,
            "spread_data": spread_data
        }
        markets_with_spread.append(market_with_spread)
    
    # Sort by specified spread type (default: percentage)
    if sort_by == "percentage":
        markets_with_spread.sort(key=lambda x: x["spread_data"]["percentage_spread"], reverse=True)
    else:  # absolute
        markets_with_spread.sort(key=lambda x: x["spread_data"]["absolute_spread"], reverse=True)
    
    return markets_with_spread

def format_market_data(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format market data for JSON output."""
    formatted_markets = []
    
    for market in markets:
        formatted_market = {
            "ticker": market.get("ticker", ""),
            "title": market.get("title", ""),
            "status": market.get("status", ""),
            "close_time": market.get("close_time", ""),
            "open_time": market.get("open_time", ""),
            "yes_bid": market.get("spread_data", {}).get("yes_bid", 0),
            "yes_ask": market.get("spread_data", {}).get("yes_ask", 0),
            "no_bid": market.get("spread_data", {}).get("no_bid", 0),
            "no_ask": market.get("spread_data", {}).get("no_ask", 0),
            "yes_spread": market.get("spread_data", {}).get("yes_spread", 0),
            "no_spread": market.get("spread_data", {}).get("no_spread", 0),
            "absolute_spread": market.get("spread_data", {}).get("absolute_spread", 0),
            "percentage_spread": market.get("spread_data", {}).get("percentage_spread", 0),
            "volume": market.get("volume", 0),
            "volume_24h": market.get("volume_24h", 0),
            "last_price": market.get("last_price", 0)
        }
        
        # Add optional fields if they exist in the original market
        if "event_ticker" in market:
            formatted_market["event_ticker"] = market.get("event_ticker")
        if "subtitle" in market:
            formatted_market["subtitle"] = market.get("subtitle")
        if "series_ticker" in market:
            formatted_market["series_ticker"] = market.get("series_ticker")
            
        formatted_markets.append(formatted_market)
    
    return formatted_markets

def save_to_json(data: List[Dict[str, Any]], filename: str = "markets_by_spread.json") -> None:
    """Save market data to JSON file in data directory."""
    try:
        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # If filename doesn't have path, save to data directory
        if os.path.dirname(filename) == '':
            filepath = os.path.join(DATA_DIR, filename)
        else:
            filepath = filename
        
        # Convert datetime objects to strings for JSON serialization
        def convert_datetime(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return obj
        
        # Recursively convert datetime objects
        def clean_data(data):
            if isinstance(data, dict):
                return {k: clean_data(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [clean_data(item) for item in data]
            else:
                return convert_datetime(data)
        
        cleaned_data = clean_data(data)
        
        with open(filepath, 'w') as f:
            json.dump(cleaned_data, f, indent=2)
        print(f"Data saved to {filepath}")
    except Exception as e:
        print(f"Error saving to JSON: {e}")

def main():
    """Main function to get markets and sort by spread."""
    parser = argparse.ArgumentParser(description="Get Kalshi markets sorted by highest spread")
    parser.add_argument("--limit", type=int, help="Number of markets to fetch (default: all active markets)")
    parser.add_argument("--sort-by", choices=["percentage", "absolute"], default="percentage", 
                       help="Sort by percentage or absolute spread in cents (default: percentage)")
    parser.add_argument("--output", type=str, default="markets_by_spread.json", 
                       help="Output JSON filename (default: markets_by_spread.json)")
    parser.add_argument("--top", type=int, help="Show only top N markets by spread")
    parser.add_argument("--all", action="store_true", help="Fetch all active markets (same as no limit)")
    
    args = parser.parse_args()
    
    # Determine the limit
    if args.all or args.limit is None:
        limit = None
        print("Fetching ALL active markets from Kalshi...")
    else:
        limit = args.limit
        print(f"Fetching {args.limit} markets from Kalshi...")
    
    # Setup client
    try:
        client = setup_client()
    except Exception as e:
        print(f"Error setting up client: {e}")
        return
    
    # Get markets (status filter removed due to SDK issues)
    markets = get_markets(client, limit=limit)
    
    if not markets:
        print("No markets found or error occurred.")
        return
    
    print(f"Found {len(markets)} markets")
    
    # Sort by spread
    sorted_markets = sort_markets_by_spread(markets, args.sort_by)
    
    # Limit to top N if specified
    if args.top:
        sorted_markets = sorted_markets[:args.top]
        print(f"Showing top {args.top} markets by {args.sort_by} spread")
    
    # Format data
    formatted_markets = format_market_data(sorted_markets)
    
    # Save to JSON
    save_to_json(formatted_markets, args.output)
    
    # Print summary
    print(f"\nTop 5 markets by {args.sort_by} spread:")
    for i, market in enumerate(formatted_markets[:5], 1):
        spread_value = market["percentage_spread"] if args.sort_by == "percentage" else market["absolute_spread"]
        print(f"{i}. {market['ticker']}: {market['title']}")
        print(f"   Spread: {spread_value:.2f}{'%' if args.sort_by == 'percentage' else '¢'}")
        print(f"   Yes: {market['yes_bid']}¢-{market['yes_ask']}¢, No: {market['no_bid']}¢-{market['no_ask']}¢")
        print()

if __name__ == "__main__":
    main()