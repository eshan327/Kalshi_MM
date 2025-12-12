#!/usr/bin/env python3
"""
Kalshi Market Maker - CLI Test Script

A simple command-line script to verify SDK connectivity and scan for market
opportunities without starting the web server.

Usage:
    python cli.py
"""
import os
import sys
from pathlib import Path

# Load .env file if it exists
def load_dotenv():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

from config import config as app_config
from services.kalshi_client import kalshi_service


def main():
    """Quick test of Kalshi API connectivity and market scanning."""
    
    # Initialize the shared Kalshi service
    if not kalshi_service.initialize():
        print("Failed to initialize Kalshi service")
        sys.exit(1)
    
    # Get balance
    balance = kalshi_service.get_balance()
    if balance is not None:
        print(f"Balance: ${balance:.2f}")
    else:
        print("Balance: N/A")
    
    # Get series info
    series_ticker = app_config.strategy.target_series
    series = kalshi_service.get_series(series_ticker)
    if series:
        print(f"\nSeries: {series['title']}")
    else:
        print(f"\nSeries: {series_ticker}")
    
    # Get open markets
    markets = kalshi_service.get_markets(series_ticker=series_ticker, status="open")
    print(f"Found {len(markets)} open markets")
    
    # Analyze spreads
    DESIRABLE_SPREAD = app_config.strategy.min_spread
    profitable_markets = []
    
    print(f"\n--- Market Analysis (target spread >= {DESIRABLE_SPREAD}¢) ---\n")
    
    for market in markets:
        ticker = market['ticker']
        title = market['title']
        
        print(f"- {ticker}: {title}")
        
        # Get orderbook metrics using the shared service
        metrics = kalshi_service.get_market_metrics(ticker)
        
        bid_str = f"{metrics['bid']}¢" if metrics['bid'] is not None else "N/A"
        ask_str = f"{metrics['ask']}¢" if metrics['ask'] is not None else "N/A"
        spread_str = f"{metrics['spread']}¢" if metrics['spread'] is not None else "N/A"
        
        print(f"  Bid: {bid_str} | Ask: {ask_str} | Spread: {spread_str}\n")
        
        if metrics['spread'] is not None and metrics['spread'] >= DESIRABLE_SPREAD:
            profitable_markets.append({
                'ticker': ticker,
                'bid': metrics['bid'],
                'ask': metrics['ask'],
                'spread': metrics['spread']
            })
    
    # Summary
    print("-" * 40)
    print("--- Opportunities ---")
    if profitable_markets:
        print(f"\nFound {len(profitable_markets)} markets with spread >= {DESIRABLE_SPREAD}¢:")
        for m in profitable_markets:
            print(f"  - {m['ticker']}: Bid {m['bid']}¢ | Ask {m['ask']}¢ | Spread {m['spread']}¢")
    else:
        print(f"\nNo markets with spread >= {DESIRABLE_SPREAD}¢")


if __name__ == '__main__':
    main()
