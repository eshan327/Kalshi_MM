#!/usr/bin/env python3
"""
Orderbook Visualization Tool.

Visualize orderbook data for price movement analysis and market making opportunities.
Loads orderbook snapshots saved by orderBookListener.py and creates visualizations.

Usage:
    python visualize_orderbook.py <orderbook_file.json>
    python visualize_orderbook.py --list  # List available orderbook files
    python visualize_orderbook.py data/orderbookData/orderBook_KXBTC-25JAN03.json -o plots/
"""

import json
import os
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
from typing import List, Dict, Optional, Tuple


def has_interactive_backend():
    """Check if matplotlib has an interactive backend available."""
    try:
        backend = matplotlib.get_backend()
        return backend.lower() not in ['agg', 'pdf', 'svg', 'ps']
    except:
        return False


def parse_price(price_value):
    """Convert price to float (handles both int cents and string decimals)."""
    if price_value is None:
        return None
    return float(price_value) / 100.0 if isinstance(price_value, int) else float(price_value)


def get_best_bid_ask(orderbook_data: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Extract best bid/ask from orderbook. YES bids from 'yes', asks from (1 - NO price)."""
    if not orderbook_data or 'orderbook' not in orderbook_data:
        return None, None
    
    ob = orderbook_data['orderbook']
    yes_orders = ob.get('yes_dollars', ob.get('yes', []))
    no_orders = ob.get('no_dollars', ob.get('no', []))
    
    # Filter out None values before calling max()
    yes_prices = [p for o in yes_orders if len(o) >= 2 and o[0] is not None 
                  for p in [parse_price(o[0])] if p is not None]
    best_bid = max(yes_prices) if yes_prices else None
    
    best_ask = None
    if no_orders:
        no_prices = [p for o in no_orders if len(o) >= 2 and o[0] is not None 
                     for p in [parse_price(o[0])] if p is not None and 0 <= p <= 1.0]
        if no_prices:
            best_ask = 1.0 - max(no_prices)
    
    return best_bid, best_ask


def calculate_mid_price(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    return (best_bid + best_ask) / 2.0 if best_bid and best_ask else None


def calculate_spread(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    return best_ask - best_bid if best_bid and best_ask else None


def simulate_market_making(mid_prices: List[float], bids: List[float], asks: List[float], 
                           timestamps: List[datetime], order_offset: float = 0.01, min_spread: float = 0.005) -> Dict:
    """Simulate MM strategy: place orders at mid ± offset, track fills and round trips."""
    opportunities = []
    open_positions = []
    
    for i in range(len(mid_prices)):
        if mid_prices[i] is None or bids[i] is None or asks[i] is None:
            continue
        
        current_mid, current_bid, current_ask = mid_prices[i], bids[i], asks[i]
        current_spread = current_ask - current_bid
        
        if current_spread < min_spread:
            continue
        
        buy_order_price = current_bid + order_offset * 0.1
        sell_order_price = current_ask - order_offset * 0.1
        
        # Check buy fill
        if buy_order_price >= current_ask:
            fill_price = current_ask
            opportunities.append({'timestamp': timestamps[i], 'type': 'buy_filled', 'fill_price': fill_price, 
                                'mid_price': current_mid, 'profit': current_mid - fill_price, 'spread': current_spread})
            open_positions.append({'entry_price': fill_price, 'entry_time': timestamps[i]})
        
        # Check sell fill
        if sell_order_price <= current_bid:
            fill_price = current_bid
            opportunities.append({'timestamp': timestamps[i], 'type': 'sell_filled', 'fill_price': fill_price,
                                'mid_price': current_mid, 'profit': fill_price - current_mid, 'spread': current_spread})
            if open_positions:
                pos = open_positions.pop(0)
                profit = fill_price - pos['entry_price']
                if profit > 0:
                    opportunities.append({'timestamp': timestamps[i], 'type': 'round_trip', 'buy_price': pos['entry_price'],
                                        'sell_price': fill_price, 'buy_time': pos['entry_time'], 'sell_time': timestamps[i],
                                        'profit': profit, 'spread': current_spread,
                                        'duration_minutes': (timestamps[i] - pos['entry_time']).total_seconds() / 60.0})
    
    round_trips = [o for o in opportunities if o['type'] == 'round_trip']
    return {
        'opportunities': opportunities, 'total_opportunities': len(opportunities), 'round_trips': round_trips,
        'total_profit': sum(o['profit'] for o in opportunities),
        'round_trip_profit': sum(o['profit'] for o in round_trips),
        'avg_round_trip_profit': np.mean([o['profit'] for o in round_trips]) if round_trips else 0
    }


def load_orderbook_data(filepath: str) -> List[Dict]:
    with open(filepath, 'r') as f:
        return json.load(f)


def main(filepath: Optional[str] = None, output_dir: Optional[str] = None):
    """Main function to visualize orderbook data.
    
    Args:
        filepath: Path to orderbook JSON file. If None, uses CLI args or shows usage.
        output_dir: Directory to save visualization. Defaults to same directory as input.
    """
    import argparse
    
    # Parse CLI args if not called programmatically
    if filepath is None:
        parser = argparse.ArgumentParser(description='Visualize orderbook data for price movement analysis.')
        parser.add_argument('filepath', nargs='?', help='Path to orderbook JSON file')
        parser.add_argument('--output', '-o', help='Output directory for visualization (default: same as input)')
        parser.add_argument('--list', '-l', action='store_true', help='List available orderbook files')
        args = parser.parse_args()
        
        # Get project root
        project_root = os.path.dirname(os.path.abspath(__file__))
        orderbook_dir = os.path.join(project_root, 'data', 'orderbookData')
        
        if args.list:
            if os.path.exists(orderbook_dir):
                files = [f for f in os.listdir(orderbook_dir) if f.endswith('.json')]
                if files:
                    print(f"Available orderbook files in {orderbook_dir}:")
                    for f in sorted(files):
                        print(f"  {f}")
                else:
                    print(f"No orderbook files found in {orderbook_dir}")
            else:
                print(f"Orderbook directory not found: {orderbook_dir}")
            return
        
        if not args.filepath:
            print("Usage: python visualize_orderbook.py <orderbook_file.json>")
            print("       python visualize_orderbook.py --list  # List available files")
            print("\nExample: python visualize_orderbook.py data/orderbookData/orderBook_KXBTC-25JAN03.json")
            return
        
        filepath = args.filepath
        output_dir = args.output
    
    # Resolve filepath
    if not os.path.isabs(filepath):
        project_root = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(project_root, filepath)
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return
    
    print(f"Loading orderbook data from {filepath}...")
    data = load_orderbook_data(filepath)
    print(f"Loaded {len(data)} snapshots")
    
    timestamps, mid_prices, best_bids, best_asks, spreads = [], [], [], [], []
    
    for entry in data:
        ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
        timestamps.append(ts)
        bid, ask = get_best_bid_ask(entry.get('order_book', {}))
        best_bids.append(bid)
        best_asks.append(ask)
        mid_prices.append(calculate_mid_price(bid, ask))
        spreads.append(calculate_spread(bid, ask))
    
    valid_idx = [i for i, p in enumerate(mid_prices) if p is not None]
    if not valid_idx:
        print("No valid price data!")
        return
    
    v_ts = [timestamps[i] for i in valid_idx]
    v_mid = [mid_prices[i] for i in valid_idx]
    v_bids = [best_bids[i] for i in valid_idx]
    v_asks = [best_asks[i] for i in valid_idx]
    v_spreads = [spreads[i] for i in valid_idx if spreads[i]]
    
    avg_spread = float(np.mean(v_spreads)) if v_spreads else 0
    print(f"Found {len(v_ts)} valid points. Price range: {min(v_mid):.4f}-{max(v_mid):.4f}, Avg spread: {avg_spread:.4f}")
    
    # Simulate MM
    mm = simulate_market_making(v_mid, v_bids, v_asks, v_ts, order_offset=0.01, min_spread=0.002)
    print(f"MM opportunities: {mm['total_opportunities']}, Round trips: {len(mm['round_trips'])}, "
          f"RT profit: ${mm['round_trip_profit']:.4f}")
    
    # Plot
    fig = plt.figure(figsize=(16, 12))
    
    ax1 = plt.subplot(3, 1, 1)
    ax1.plot(v_ts, v_mid, 'b-', lw=1.5, label='Mid', alpha=0.7)
    ax1.fill_between(v_ts, v_bids, v_asks, alpha=0.2, color='gray', label='Spread')
    ax1.set_title('Price Movement')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    
    ax2 = plt.subplot(3, 1, 2)
    ax2.plot([timestamps[i] for i in valid_idx if spreads[i]], v_spreads, 'purple', lw=1.5)
    ax2.axhline(avg_spread, color='r', ls='--', label=f'Mean: {avg_spread:.4f}')
    ax2.set_title('Bid-Ask Spread')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    ax3 = plt.subplot(3, 1, 3)
    rt = mm['round_trips']
    if rt:
        ax3.scatter([o['sell_time'] for o in rt], [o['profit'] for o in rt], c='blue', s=100, label=f'Round Trips ({len(rt)})')
    ax3.set_title(f"MM Opportunities - RT Profit: ${mm['round_trip_profit']:.4f}")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Determine output path
    if output_dir is None:
        output_dir = os.path.dirname(filepath)
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_path = os.path.join(output_dir, f"{base_name}_visualization.png")
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved visualization: {output_path}")
    
    if has_interactive_backend():
        plt.show()


if __name__ == '__main__':
    main()

