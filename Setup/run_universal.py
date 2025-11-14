#!/usr/bin/env python3
"""
Universal runner for BasicMM - choose between demo and production environments
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from Strategies.basicMM import BasicMM
import time

def main():
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1].lower() in ['demo', 'd', '--demo']:
            demo_mode = True
            env_name = "DEMO"
        elif sys.argv[1].lower() in ['production', 'prod', 'p', '--production', '--prod']:
            demo_mode = False
            env_name = "PRODUCTION"
        else:
            print("Usage: python run_universal.py [demo|production]")
            print("  demo, d, --demo        : Run in demo environment")
            print("  production, prod, p, --production, --prod : Run in production environment")
            return
    else:
        # Interactive mode
        print("Choose environment:")
        print("1. Demo (safe testing)")
        print("2. Production (real trading)")
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            demo_mode = True
            env_name = "DEMO"
        elif choice == "2":
            demo_mode = False
            env_name = "PRODUCTION"
        else:
            print("Invalid choice. Exiting.")
            return

    print(f"Starting BasicMM on Kalshi {env_name} environment...")
    print("=" * 50)
    
    # Initialize market maker
    mm = BasicMM(reserve_limit=10, demo=demo_mode)
    
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
            if demo_mode:
                print("\nNo opportunities found - this is normal for demo environments")
                print("Demo markets typically have no active trading or tight spreads")
            else:
                print("\nNo opportunities found - markets may have tight spreads")
                print("This is normal when markets are efficient or during low volatility")
        
        # Ask for confirmation before trading in production
        if not demo_mode and len(mm.market_opportunities) > 0:
            print(f"\n⚠️  PRODUCTION MODE: {len(mm.market_opportunities)} opportunities found")
            print("This will place REAL trades with REAL money!")
            confirm = input("Do you want to proceed with trading? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                print("Trading cancelled by user.")
                return
        
        # Run single iteration (non-async)
        print("\nRunning single trading iteration...")
        try:
            mm.run()
            print(f"\n{env_name} run completed successfully!")
            
            # Check if log file was created
            try:
                log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "tradeLimitOrders.log")
                with open(log_file, "r") as f:
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
            print(f"\nTrading iteration completed with issues: {e}")
            if demo_mode:
                print("This is normal for demo environments without trading permissions.")
            else:
                print("This may be due to insufficient balance, permissions, or market conditions.")
            
    except Exception as e:
        print(f"Error: {e}")
        if demo_mode:
            print("Make sure you have valid demo credentials set up.")
        else:
            print("Make sure you have valid production credentials set up.")
            print("Check that your private key file exists and API key is correct.")

if __name__ == "__main__":
    main()
