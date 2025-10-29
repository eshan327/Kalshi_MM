import json
import argparse
from typing import List, Dict, Any, Optional


def load_markets(json_file: str) -> List[Dict[str, Any]]:
    """Load markets from a JSON file."""
    try:
        with open(json_file, 'r') as f:
            markets = json.load(f)
        print(f"Loaded {len(markets)} markets from {json_file}")
        return markets
    except FileNotFoundError:
        print(f"Error: File {json_file} not found.")
        return []
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_file}: {e}")
        return []


def detect_market_type(market: Dict[str, Any]) -> str:
    """Detect market type based on ticker, event_ticker, subtitle, or title."""
    title = market.get("title", "").lower()
    subtitle = market.get("subtitle", "").lower()
    ticker = market.get("ticker", "").upper()
    event_ticker = market.get("event_ticker", "").upper()
    
    # Combine all text fields for analysis
    combined_text = f"{title} {subtitle}".lower()
    combined_ticker = f"{ticker} {event_ticker}".upper()
    
    # NFL/Football markets - check event_ticker first for accuracy
    if "KXMVENFL" in event_ticker or "KXMVENFL" in ticker:
        return "sports_football_nfl"
    
    # NBA/Basketball
    if "KXMVENBA" in event_ticker or "KXMVENBA" in ticker or "nba" in combined_text:
        return "sports_basketball_nba"
    
    # MLB/Baseball
    if "KXMVEMLB" in event_ticker or "KXMVEMLB" in ticker or "mlb" in combined_text:
        return "sports_baseball_mlb"
    
    # NHL/Hockey
    if "KXMVE NHL" in event_ticker or "nhl" in combined_text:
        return "sports_hockey_nhl"
    
    # Sports categories (general detection from text)
    if any(term in combined_text for term in ["nfl", "football", "nba", "basketball", "mlb", "baseball", 
                                       "nhl", "hockey", "soccer", "tennis", "golf", "mma", "boxing",
                                       "buffalo", "baltimore", "dallas", "atlanta", "kansas city",
                                       "wins", "points", "yards", "touchdown", "field goal", "mahomes",
                                       "kelce", "quarterback", "touchdown"]):
        return "sports"
    
    # Climate/Weather
    if any(term in combined_text for term in ["temperature", "weather", "storm", "hurricane", 
                                        "precipitation", "rain", "snow", "climate", "degree",
                                        "weather", "temperature", "celsius", "fahrenheit"]):
        return "climate"
    
    # Politics
    if any(term in combined_text for term in ["election", "president", "congress", "senate", "house",
                                          "vote", "polling", "democrat", "republican", "candidate"]):
        return "politics"
    
    # Economics
    if any(term in combined_text for term in ["gdp", "inflation", "unemployment", "stock", "market",
                                        "interest rate", "economy", "recession", "cpi"]):
        return "economics"
    
    # Technology
    if any(term in combined_text for term in ["tech", "ai", "artificial intelligence", "apple", "google",
                                         "microsoft", "meta", "amazon", "tesla", "innovation"]):
        return "technology"
    
    # Entertainment
    if any(term in combined_text for term in ["movie", "film", "oscar", "grammy", "award", "celebrity",
                                        "box office", "streaming", "tv show", "series"]):
        return "entertainment"
    
    # General/Other
    return "general"


def filter_by_volume(markets: List[Dict[str, Any]], min_volume: Optional[int] = None, 
                     max_volume: Optional[int] = None, volume_24h: Optional[bool] = None) -> List[Dict[str, Any]]:
    """
    Filter markets by volume criteria.
    
    Args:
        markets: List of market dictionaries
        min_volume: Minimum volume threshold
        max_volume: Maximum volume threshold
        volume_24h: If True, filter by volume_24h instead of volume
    
    Returns:
        Filtered list of markets
    """
    filtered = []
    volume_key = "volume_24h" if volume_24h else "volume"
    
    for market in markets:
        volume = market.get(volume_key, 0)
        
        # Check minimum volume
        if min_volume is not None and volume < min_volume:
            continue
        
        # Check maximum volume
        if max_volume is not None and volume > max_volume:
            continue
        
        filtered.append(market)
    
    return filtered


def filter_by_market_type(markets: List[Dict[str, Any]], market_types: List[str]) -> List[Dict[str, Any]]:
    """
    Filter markets by market type/category.
    
    Args:
        markets: List of market dictionaries
        market_types: List of market types to include (sports, climate, politics, etc.)
    
    Returns:
        Filtered list of markets with added 'market_type' field
    """
    filtered = []
    
    for market in markets:
        market_type = detect_market_type(market)
        market["market_type"] = market_type
        
        if market_type in market_types:
            filtered.append(market)
    
    return filtered


def filter_by_spread(markets: List[Dict[str, Any]], min_spread: Optional[float] = None,
                     max_spread: Optional[float] = None, use_percentage: bool = True) -> List[Dict[str, Any]]:
    """
    Filter markets by spread (absolute or percentage).
    
    Args:
        markets: List of market dictionaries
        min_spread: Minimum spread threshold
        max_spread: Maximum spread threshold
        use_percentage: If True, use percentage_spread, else use absolute_spread
    
    Returns:
        Filtered list of markets
    """
    filtered = []
    spread_key = "percentage_spread" if use_percentage else "absolute_spread"
    
    for market in markets:
        spread = market.get(spread_key, 0)
        
        if min_spread is not None and spread < min_spread:
            continue
        
        if max_spread is not None and spread > max_spread:
            continue
        
        filtered.append(market)
    
    return filtered


def filter_by_multiple_criteria(markets: List[Dict[str, Any]], min_volume: Optional[int] = None,
                               max_volume: Optional[int] = None, market_types: Optional[List[str]] = None,
                               min_spread: Optional[float] = None, max_spread: Optional[float] = None,
                               use_percentage: bool = True, volume_24h: bool = False) -> List[Dict[str, Any]]:
    """
    Filter markets by multiple criteria.
    
    Args:
        markets: List of market dictionaries
        min_volume: Minimum volume threshold
        max_volume: Maximum volume threshold
        market_types: List of market types to include
        min_spread: Minimum spread threshold
        max_spread: Maximum spread threshold
        use_percentage: Use percentage or absolute spread
        volume_24h: Use 24h volume instead of total volume
    
    Returns:
        Filtered list of markets
    """
    filtered = markets
    
    # Filter by volume
    if min_volume is not None or max_volume is not None:
        filtered = filter_by_volume(filtered, min_volume, max_volume, volume_24h)
        print(f"After volume filtering: {len(filtered)} markets")
    
    # Filter by market type
    if market_types:
        filtered = filter_by_market_type(filtered, market_types)
        print(f"After type filtering: {len(filtered)} markets")
    
    # Filter by spread
    if min_spread is not None or max_spread is not None:
        filtered = filter_by_spread(filtered, min_spread, max_spread, use_percentage)
        print(f"After spread filtering: {len(filtered)} markets")
    
    return filtered


def save_filtered_markets(markets: List[Dict[str, Any]], output_file: str) -> None:
    """Save filtered markets to a JSON file."""
    try:
        with open(output_file, 'w') as f:
            json.dump(markets, f, indent=2)
        print(f"✓ Saved {len(markets)} filtered markets to {output_file}")
    except Exception as e:
        print(f"Error saving to {output_file}: {e}")


def get_market_type_stats(markets: List[Dict[str, Any]]) -> Dict[str, int]:
    """Get statistics about market types in the dataset."""
    stats = {}
    
    for market in markets:
        market_type = market.get("market_type", detect_market_type(market))
        stats[market_type] = stats.get(market_type, 0) + 1
    
    return stats


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(description="Filter Kalshi markets by volume and market type")
    
    # Input/Output
    parser.add_argument("input", help="Input JSON file with markets")
    parser.add_argument("--output", "-o", default="filtered_markets.json", 
                       help="Output JSON file (default: filtered_markets.json)")
    
    # Volume filtering
    parser.add_argument("--min-volume", type=int, help="Minimum volume threshold")
    parser.add_argument("--max-volume", type=int, help="Maximum volume threshold")
    parser.add_argument("--use-24h-volume", action="store_true", 
                       help="Use 24-hour volume instead of total volume")
    
    # Market type filtering
    parser.add_argument("--types", nargs="+", 
                       choices=["sports", "sports_football_nfl", "sports_basketball_nba", 
                               "sports_baseball_mlb", "sports_hockey_nhl", "climate", 
                               "politics", "economics", "technology", "entertainment", "general"],
                       help="Market types to include (can specify multiple)")
    
    # Spread filtering
    parser.add_argument("--min-spread", type=float, help="Minimum spread threshold")
    parser.add_argument("--max-spread", type=float, help="Maximum spread threshold")
    parser.add_argument("--absolute-spread", action="store_true", 
                       help="Use absolute spread instead of percentage")
    
    # Display options
    parser.add_argument("--stats", action="store_true", 
                       help="Display market type statistics")
    parser.add_argument("--top", type=int, help="Show only top N markets")
    
    args = parser.parse_args()
    
    # Load markets
    print(f"Loading markets from {args.input}...")
    markets = load_markets(args.input)
    
    if not markets:
        print("No markets loaded.")
        return
    
    # Display initial statistics
    if args.stats:
        stats = get_market_type_stats(markets)
        print("\nMarket Type Distribution:")
        for market_type, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {market_type}: {count:,}")
        print()
    
    # Apply filters
    print("\nApplying filters...")
    filtered = filter_by_multiple_criteria(
        markets,
        min_volume=args.min_volume,
        max_volume=args.max_volume,
        market_types=args.types,
        min_spread=args.min_spread,
        max_spread=args.max_spread,
        use_percentage=not args.absolute_spread,
        volume_24h=args.use_24h_volume
    )
    
    # Limit to top N if requested
    if args.top:
        filtered = filtered[:args.top]
        print(f"Showing top {args.top} markets")
    
    # Save results
    save_filtered_markets(filtered, args.output)
    
    print(f"\n✓ Filtered {len(markets)} markets down to {len(filtered)} markets")


if __name__ == "__main__":
    main()