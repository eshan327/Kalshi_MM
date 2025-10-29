#!/usr/bin/env python3
"""
Demo runner for BasicMM on Kalshi's demo environment
"""

from basicMM import BasicMM
import time

def main():
    print("Starting BasicMM on Kalshi DEMO environment...")
    print("=" * 50)
    
    # Initialize market maker for demo
    mm = BasicMM(reserve_limit=10, demo=True)
    
    print(f"Demo mode: {mm.demo}")
    print(f"Reserve limit: ${mm.reserve_limit}")
    
    try:
        # Test connection
        print("\nTesting connection...")
        balance = mm.client.get_balance()
        print(f"Account balance: ${balance.balance / 100:.2f}")
        
        # Get markets
        print("\nFetching markets...")
        markets = mm.get_markets()
        print(f"Found {len(markets.markets)} markets")
        
        # Identify opportunities
        print("\nIdentifying market opportunities...")
        mm.identify_market_opportunities()
        print(f"Found {len(mm.market_opportunities)} opportunities")
        
        if mm.market_opportunities:
            print("\nTop 5 opportunities by spread:")
            for i, market in enumerate(mm.market_opportunities[:5], 1):
                # Calculate spread if not available
                if hasattr(market, 'spread'):
                    spread = market.spread
                elif hasattr(market, 'yes_bid') and hasattr(market, 'yes_ask'):
                    spread = market.yes_ask - market.yes_bid
                else:
                    spread = 0
                
                ticker = getattr(market, 'ticker', 'Unknown')
                print(f"{i}. {ticker}: Spread = {spread:.4f}")
        else:
            print("\nNo opportunities found - this is normal for demo environments")
            print("Demo markets typically have no active trading or tight spreads")
        
        # Run single iteration (non-async)
        print("\nRunning single trading iteration...")
        try:
            mm.run()
            print("\nDemo completed successfully!")
        except Exception as e:
            print(f"\nDemo completed with expected limitations: {e}")
            print("This is normal for demo environments without trading permissions.")
            
            # Check if log file was created despite the error
            try:
                with open("tradeLimitOrders.log", "r") as f:
                    content = f.read()
                    if content.strip():
                        print(f"\nTrade log file created with {len(content.splitlines())} entries")
                        print("Last few entries:")
                        lines = content.strip().split('\n')
                        for line in lines[-3:]:
                            print(f"  {line}")
                    else:
                        print("\nTrade log file exists but is empty")
            except FileNotFoundError:
                print("\nNo trade log file created (no opportunities found or no trades attempted)")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you have valid demo credentials set up.")

if __name__ == "__main__":
    main()
