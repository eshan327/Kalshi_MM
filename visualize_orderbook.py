#!/usr/bin/env python3
"""
Visualize orderbook data to show price movement over time and identify market making opportunities.
"""

import json
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
from typing import List, Dict, Optional, Tuple

# Check if we have an interactive backend available
def has_interactive_backend():
    """Check if matplotlib has an interactive backend available."""
    try:
        backend = matplotlib.get_backend()
        # Non-interactive backends
        non_interactive = ['Agg', 'pdf', 'svg', 'ps']
        return backend.lower() not in [b.lower() for b in non_interactive]
    except:
        return False

def parse_price(price_value):
    """Convert price to float (handles both int cents and string decimals)."""
    if price_value is None:
        return None
    if isinstance(price_value, str):
        return float(price_value)
    return float(price_value) / 100.0  # Convert cents to probability

def get_best_bid_ask(orderbook_data: Dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract best bid and ask prices from orderbook.
    
    In Kalshi orderbook:
    - 'yes' array: buy orders for YES contracts [price_in_cents, volume]
    - 'yes_dollars' array: buy orders for YES contracts ["0.0100", volume]
    - 'no' array: buy orders for NO contracts [price_in_cents, volume]
    - 'no_dollars' array: buy orders for NO contracts ["0.0100", volume]
    
    Best bid YES = highest price someone will pay for YES (highest in YES array)
    Best ask YES = lowest price someone will sell YES for
        = 1.0 - (highest NO buy price) since buying NO at X is equivalent to selling YES at (1.0 - X)
    """
    if not orderbook_data or 'orderbook' not in orderbook_data:
        return None, None
    
    ob = orderbook_data['orderbook']
    
    # Try to use dollar format first (more precise), fall back to cents
    yes_orders = ob.get('yes_dollars', ob.get('yes', []))
    no_orders = ob.get('no_dollars', ob.get('no', []))
    
    best_bid = None
    best_ask = None
    
    # Best bid = highest price someone will pay for YES
    if yes_orders and len(yes_orders) > 0:
        yes_prices = []
        for order in yes_orders:
            if len(order) >= 2 and order[0] is not None:
                price = parse_price(order[0])
                if price is not None and 0 <= price <= 1.0:
                    yes_prices.append(price)
        
        if yes_prices:
            best_bid = max(yes_prices)
    
    # Best ask = lowest price someone will sell YES for
    # Buying NO at price X is equivalent to selling YES at (1.0 - X)
    if no_orders and len(no_orders) > 0:
        no_prices = []
        for order in no_orders:
            if len(order) >= 2 and order[0] is not None:
                price = parse_price(order[0])
                if price is not None and 0 <= price <= 1.0:
                    no_prices.append(price)
        
        if no_prices:
            # Highest NO buy price = lowest YES ask price
            max_no_price = max(no_prices)
            best_ask = 1.0 - max_no_price
    
    return best_bid, best_ask

def calculate_mid_price(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    """Calculate mid price from best bid and ask."""
    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / 2.0

def calculate_spread(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    """Calculate bid-ask spread."""
    if best_bid is None or best_ask is None:
        return None
    return best_ask - best_bid

def simulate_market_making(
    mid_prices: List[float],
    bids: List[float],
    asks: List[float],
    timestamps: List[datetime],
    order_offset: float = 0.01,
    min_spread: float = 0.005
) -> Dict:
    """
    Simulate market making strategy:
    - Place limit orders at mid_price ± order_offset
    - Track when orders would have been filled
    - Calculate potential profit from spread capture and round trips
    
    Strategy: At each snapshot, place:
    - Buy order at mid_price - order_offset (to buy YES below mid)
    - Sell order at mid_price + order_offset (to sell YES above mid)
    - Track positions and calculate round-trip profits
    
    Round Trip: A complete cycle where you:
    1. Place a buy limit order that gets filled
    2. Later place a sell limit order that gets filled
    3. Profit = sell_price - buy_price
    """
    opportunities = []
    open_positions = []  # Track open positions: [{'entry_price': float, 'entry_time': datetime, 'type': 'long'}]
    
    for i in range(len(mid_prices)):
        if mid_prices[i] is None or bids[i] is None or asks[i] is None:
            continue
        
        current_mid = mid_prices[i]
        current_bid = bids[i]
        current_ask = asks[i]
        current_spread = current_ask - current_bid
        
        # Only trade if spread is wide enough
        if current_spread < min_spread:
            continue
        
        # Market making strategy: Place limit orders and track if they would be filled
        # We place orders at the current bid/ask (or slightly inside the spread)
        
        # Place buy order at current bid (or slightly above for better fill probability)
        buy_order_price = current_bid + order_offset * 0.1  # Slightly above bid to improve fill chances
        # Place sell order at current ask (or slightly below for better fill probability)  
        sell_order_price = current_ask - order_offset * 0.1  # Slightly below ask to improve fill chances
        
        # Check if buy order would be filled immediately (if ask drops to our bid level)
        if buy_order_price >= current_ask:
            # Immediate fill - buy at current ask
            fill_price = current_ask
            potential_profit = current_mid - fill_price
            opportunities.append({
                'timestamp': timestamps[i],
                'type': 'buy_filled',
                'order_price': buy_order_price,
                'fill_price': fill_price,
                'mid_price': current_mid,
                'profit': potential_profit,
                'spread': current_spread
            })
            open_positions.append({
                'entry_price': fill_price,
                'entry_time': timestamps[i],
                'entry_mid': current_mid,
                'type': 'long'
            })
        else:
            # Order placed but not filled - track it for potential future fill
            # We'll check in future iterations if price crosses this level
            pass
        
        # Check if sell order would be filled immediately (if bid rises to our ask level)
        if sell_order_price <= current_bid:
            # Immediate fill - sell at current bid
            fill_price = current_bid
            potential_profit = fill_price - current_mid
            opportunities.append({
                'timestamp': timestamps[i],
                'type': 'sell_filled',
                'order_price': sell_order_price,
                'fill_price': fill_price,
                'mid_price': current_mid,
                'profit': potential_profit,
                'spread': current_spread
            })
            
            # Close matching long position if available
            if open_positions:
                position = open_positions.pop(0)
                round_trip_profit = fill_price - position['entry_price']
                if round_trip_profit > 0:  # Only record profitable round trips
                    opportunities.append({
                        'timestamp': timestamps[i],
                        'type': 'round_trip',
                        'buy_price': position['entry_price'],
                        'sell_price': fill_price,
                        'buy_time': position['entry_time'],
                        'sell_time': timestamps[i],
                        'profit': round_trip_profit,
                        'spread': current_spread,
                        'duration_minutes': (timestamps[i] - position['entry_time']).total_seconds() / 60.0
                    })
        
        # Check if existing positions can be closed profitably at current prices
        positions_to_close = []
        for j, position in enumerate(open_positions):
            # Close if we can sell for profit (current bid >= entry price)
            if current_bid >= position['entry_price']:
                positions_to_close.append(j)
        
        # Close profitable positions
        for j in reversed(positions_to_close):
            position = open_positions.pop(j)
            round_trip_profit = current_bid - position['entry_price']
            if round_trip_profit > 0:  # Only record profitable round trips
                opportunities.append({
                    'timestamp': timestamps[i],
                    'type': 'round_trip',
                    'buy_price': position['entry_price'],
                    'sell_price': current_bid,
                    'buy_time': position['entry_time'],
                    'sell_time': timestamps[i],
                    'profit': round_trip_profit,
                    'spread': current_spread,
                    'duration_minutes': (timestamps[i] - position['entry_time']).total_seconds() / 60.0
                })
        
        # Track pending orders from previous snapshots - check if they would fill now
        # This simulates orders staying on the book until filled
        if i > 0:
            # Check if a buy order placed at previous bid would fill now
            prev_bid = bids[i-1] if i > 0 and bids[i-1] is not None else None
            if prev_bid is not None:
                # If current ask dropped to or below previous bid, our buy order would fill
                if current_ask <= prev_bid + order_offset * 0.1:
                    fill_price = min(current_ask, prev_bid + order_offset * 0.1)
                    potential_profit = current_mid - fill_price
                    if potential_profit > 0:
                        opportunities.append({
                            'timestamp': timestamps[i],
                            'type': 'buy_filled',
                            'order_price': prev_bid + order_offset * 0.1,
                            'fill_price': fill_price,
                            'mid_price': current_mid,
                            'profit': potential_profit,
                            'spread': current_spread
                        })
                        open_positions.append({
                            'entry_price': fill_price,
                            'entry_time': timestamps[i],
                            'entry_mid': current_mid,
                            'type': 'long'
                        })
            
            # Check if a sell order placed at previous ask would fill now
            prev_ask = asks[i-1] if i > 0 and asks[i-1] is not None else None
            if prev_ask is not None:
                # If current bid rose to or above previous ask, our sell order would fill
                if current_bid >= prev_ask - order_offset * 0.1:
                    fill_price = max(current_bid, prev_ask - order_offset * 0.1)
                    potential_profit = fill_price - current_mid
                    if potential_profit > 0:
                        opportunities.append({
                            'timestamp': timestamps[i],
                            'type': 'sell_filled',
                            'order_price': prev_ask - order_offset * 0.1,
                            'fill_price': fill_price,
                            'mid_price': current_mid,
                            'profit': potential_profit,
                            'spread': current_spread
                        })
                        # Close matching position if available
                        if open_positions:
                            position = open_positions.pop(0)
                            round_trip_profit = fill_price - position['entry_price']
                            if round_trip_profit > 0:
                                opportunities.append({
                                    'timestamp': timestamps[i],
                                    'type': 'round_trip',
                                    'buy_price': position['entry_price'],
                                    'sell_price': fill_price,
                                    'buy_time': position['entry_time'],
                                    'sell_time': timestamps[i],
                                    'profit': round_trip_profit,
                                    'spread': current_spread,
                                    'duration_minutes': (timestamps[i] - position['entry_time']).total_seconds() / 60.0
                                })
    
    return {
        'opportunities': opportunities,
        'total_opportunities': len(opportunities),
        'round_trips': [opp for opp in opportunities if opp['type'] == 'round_trip'],
        'total_profit': sum([opp['profit'] for opp in opportunities]),
        'round_trip_profit': sum([opp['profit'] for opp in opportunities if opp['type'] == 'round_trip']),
        'avg_profit': np.mean([opp['profit'] for opp in opportunities]) if opportunities else 0,
        'avg_round_trip_profit': np.mean([opp['profit'] for opp in opportunities if opp['type'] == 'round_trip']) if any(opp['type'] == 'round_trip' for opp in opportunities) else 0
    }

def load_orderbook_data(filepath: str) -> List[Dict]:
    """Load orderbook data from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    filepath = '/Users/twilliams/Kalshi_MM/data/orderbookData/orderBook_KXMLBGAME-25OCT31LADTOR-LAD.json'
    
    print("Loading orderbook data...")
    data = load_orderbook_data(filepath)
    print(f"Loaded {len(data)} orderbook snapshots")
    
    timestamps = []
    mid_prices = []
    best_bids = []
    best_asks = []
    spreads = []
    
    print("Processing orderbook data...")
    for idx, entry in enumerate(data):
        if idx % 100 == 0:
            print(f"  Processed {idx}/{len(data)} snapshots...", end='\r')
        if idx == len(data) - 1:
            print(f"  Processed {len(data)}/{len(data)} snapshots...")
        timestamp_str = entry['timestamp']
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        timestamps.append(timestamp)
        
        orderbook = entry.get('order_book', {})
        best_bid, best_ask = get_best_bid_ask(orderbook)
        best_bids.append(best_bid)
        best_asks.append(best_ask)
        
        mid_price = calculate_mid_price(best_bid, best_ask)
        mid_prices.append(mid_price)
        
        spread = calculate_spread(best_bid, best_ask)
        spreads.append(spread)
    
    # Filter out None values for visualization
    valid_indices = [i for i, price in enumerate(mid_prices) if price is not None]
    
    if not valid_indices:
        print("No valid price data found in orderbook!")
        return
    
    valid_timestamps = [timestamps[i] for i in valid_indices]
    valid_mid_prices = [mid_prices[i] for i in valid_indices]
    valid_bids = [best_bids[i] for i in valid_indices]
    valid_asks = [best_asks[i] for i in valid_indices]
    valid_spreads = [spreads[i] for i in valid_indices if spreads[i] is not None]
    valid_spread_timestamps = [timestamps[i] for i in valid_indices if spreads[i] is not None]
    
    print(f"Found {len(valid_timestamps)} valid price points")
    print(f"Price range: {min(valid_mid_prices):.4f} - {max(valid_mid_prices):.4f}")
    print(f"Average spread: {np.mean(valid_spreads):.4f}")
    print(f"Sample bid/ask/mid: bid={valid_bids[0]:.4f}, ask={valid_asks[0]:.4f}, mid={valid_mid_prices[0]:.4f}" if valid_bids and valid_asks and valid_mid_prices else "No valid data")
    
    # Simulate market making opportunities
    print("\nAnalyzing market making opportunities...")
    mm_results = simulate_market_making(
        valid_mid_prices,
        valid_bids,
        valid_asks,
        valid_timestamps,
        order_offset=0.01,  # Place orders 1% away from mid (more realistic)
        min_spread=0.002  # Minimum spread of 0.2% to trade (less restrictive)
    )
    
    print(f"Found {mm_results['total_opportunities']} potential market making opportunities")
    print(f"  - Round trips: {len(mm_results['round_trips'])}")
    print(f"  - Total potential profit: ${mm_results['total_profit']:.4f}")
    print(f"  - Round trip profit: ${mm_results['round_trip_profit']:.4f}")
    print(f"  - Average round trip profit: ${mm_results['avg_round_trip_profit']:.4f}")
    
    # Create visualizations
    fig = plt.figure(figsize=(16, 12))
    
    # Plot 1: Price movement over time
    ax1 = plt.subplot(3, 1, 1)
    ax1.plot(valid_timestamps, valid_mid_prices, 'b-', linewidth=1.5, label='Mid Price', alpha=0.7)
    ax1.plot(valid_timestamps, valid_bids, 'g-', linewidth=0.8, label='Best Bid', alpha=0.5)
    ax1.plot(valid_timestamps, valid_asks, 'r-', linewidth=0.8, label='Best Ask', alpha=0.5)
    ax1.fill_between(valid_timestamps, valid_bids, valid_asks, alpha=0.2, color='gray', label='Bid-Ask Spread')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Price (Probability)')
    ax1.set_title('Price Movement Over Time - KXMLBGAME-25OCT31LADTOR-LAD')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    
    # Plot 2: Bid-Ask Spread over time
    ax2 = plt.subplot(3, 1, 2)
    ax2.plot(valid_spread_timestamps, valid_spreads, 'purple', linewidth=1.5, alpha=0.7)
    ax2.axhline(y=np.mean(valid_spreads), color='r', linestyle='--', label=f'Mean Spread: {np.mean(valid_spreads):.4f}')
    ax2.set_xlabel('Time')
    ax2.set_ylabel('Spread (Probability)')
    ax2.set_title('Bid-Ask Spread Over Time')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    # Plot 3: Market making opportunities
    ax3 = plt.subplot(3, 1, 3)
    if mm_results['opportunities']:
        buy_filled = [opp for opp in mm_results['opportunities'] if opp['type'] == 'buy_filled']
        sell_filled = [opp for opp in mm_results['opportunities'] if opp['type'] == 'sell_filled']
        round_trips = [opp for opp in mm_results['opportunities'] if opp['type'] == 'round_trip']
        
        if buy_filled:
            buy_times = [opp['timestamp'] for opp in buy_filled]
            buy_profits = [opp['profit'] for opp in buy_filled]
            ax3.scatter(buy_times, buy_profits, color='green', marker='^', s=60, label=f'Buy Filled ({len(buy_filled)})', alpha=0.5)
        
        if sell_filled:
            sell_times = [opp['timestamp'] for opp in sell_filled]
            sell_profits = [opp['profit'] for opp in sell_filled]
            ax3.scatter(sell_times, sell_profits, color='red', marker='v', s=60, label=f'Sell Filled ({len(sell_filled)})', alpha=0.5)
        
        if round_trips:
            rt_times = [opp['sell_time'] for opp in round_trips]
            rt_profits = [opp['profit'] for opp in round_trips]
            ax3.scatter(rt_times, rt_profits, color='blue', marker='o', s=100, label=f'Round Trips ({len(round_trips)})', alpha=0.7, edgecolors='darkblue', linewidths=1)
            
            # Draw lines connecting buy and sell for round trips (optional - can be cluttered)
            # for rt in round_trips:
            #     ax3.plot([rt['buy_time'], rt['sell_time']], 
            #             [0, rt['profit']], 
            #             'b-', alpha=0.1, linewidth=0.3)
        
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax3.set_xlabel('Time')
        ax3.set_ylabel('Profit per Contract')
        ax3.set_title(f'Market Making Opportunities - Round Trips: {len(round_trips)}, Total Profit: ${mm_results["round_trip_profit"]:.4f}, Avg: ${mm_results["avg_round_trip_profit"]:.4f}')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax3.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    else:
        ax3.text(0.5, 0.5, 'No market making opportunities found\nwith current parameters', 
                ha='center', va='center', transform=ax3.transAxes, fontsize=12)
        ax3.set_title('Market Making Opportunities')
    
    plt.tight_layout()
    
    # Save the plot
    output_path = '/Users/twilliams/Kalshi_MM/data/orderbookData/orderbook_visualization.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nVisualization saved to: {output_path}")
    plt.close()  # Close the figure to free memory
    
    # Also create a detailed opportunity report
    if mm_results['opportunities']:
        report_path = '/Users/twilliams/Kalshi_MM/data/orderbookData/market_making_opportunities.txt'
        with open(report_path, 'w') as f:
            f.write("Market Making Opportunities Report\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total Opportunities: {mm_results['total_opportunities']}\n")
            f.write(f"Round Trips: {len(mm_results['round_trips'])}\n")
            f.write(f"Total Potential Profit: ${mm_results['total_profit']:.4f}\n")
            f.write(f"Round Trip Profit: ${mm_results['round_trip_profit']:.4f}\n")
            f.write(f"Average Round Trip Profit: ${mm_results['avg_round_trip_profit']:.4f}\n\n")
            
            # Round trips section
            if mm_results['round_trips']:
                f.write("ROUND TRIPS (Buy then Sell - Most Profitable):\n")
                f.write("-" * 80 + "\n")
                sorted_round_trips = sorted(mm_results['round_trips'], key=lambda x: x['profit'], reverse=True)
                for i, rt in enumerate(sorted_round_trips[:30], 1):
                    f.write(f"\n{i}. Round Trip #{i} - Profit: ${rt['profit']:.4f}\n")
                    f.write(f"   Buy:  ${rt['buy_price']:.4f} at {rt['buy_time']}\n")
                    f.write(f"   Sell: ${rt['sell_price']:.4f} at {rt['sell_time']}\n")
                    f.write(f"   Duration: {rt['duration_minutes']:.1f} minutes\n")
                    f.write(f"   Spread at sell: {rt['spread']:.4f}\n")
            
            # All opportunities
            f.write("\n\nALL OPPORTUNITIES (Top 30 by Profit):\n")
            f.write("-" * 80 + "\n")
            sorted_opps = sorted(mm_results['opportunities'], key=lambda x: x['profit'], reverse=True)
            for i, opp in enumerate(sorted_opps[:30], 1):
                f.write(f"\n{i}. {opp['type'].upper()} at {opp['timestamp']}\n")
                if opp['type'] == 'round_trip':
                    f.write(f"   Buy Price: ${opp['buy_price']:.4f} at {opp['buy_time']}\n")
                    f.write(f"   Sell Price: ${opp['sell_price']:.4f} at {opp['sell_time']}\n")
                    f.write(f"   Duration: {opp['duration_minutes']:.1f} minutes\n")
                else:
                    f.write(f"   Order Price: ${opp['order_price']:.4f}\n")
                    f.write(f"   Fill Price: ${opp['fill_price']:.4f}\n")
                f.write(f"   Mid Price: ${opp['mid_price']:.4f}\n")
                f.write(f"   Profit: ${opp['profit']:.4f}\n")
                f.write(f"   Spread: {opp['spread']:.4f}\n")
        
        print(f"Detailed report saved to: {report_path}")
    
    # Show the plot in a window if interactive backend is available
    if has_interactive_backend():
        print("\nDisplaying visualization window...")
        plt.show()  # Display the visualization window
    else:
        print("\nNote: No interactive backend available. Opening saved PNG file instead...")
        # Try to open the saved file with the system default viewer
        import subprocess
        import platform
        try:
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', output_path])
            elif platform.system() == 'Windows':
                subprocess.run(['start', output_path], shell=True)
            else:  # Linux
                subprocess.run(['xdg-open', output_path])
        except Exception as e:
            print(f"Could not open file automatically: {e}")
            print(f"Please open manually: {output_path}")
    
    print("\nVisualization complete!")

if __name__ == '__main__':
    main()

