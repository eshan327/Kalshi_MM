"""
Example script showing how to use the websocket streamer with dynamic subscriptions.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import importlib.util
websocket_dir = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("market_streamer", os.path.join(websocket_dir, "market_streamer.py"))
market_streamer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market_streamer)
KalshiMarketStreamer = market_streamer.KalshiMarketStreamer


async def example_dynamic_subscriptions():
    """
    Example: Start with one market, then add more markets dynamically.
    """
    print("=== Example: Dynamic Subscriptions ===\n")
    
    # Start with one market
    initial_markets = ["KXMLBGAME-25OCT31LADTOR-LAD"]
    streamer = KalshiMarketStreamer(market_ids=initial_markets)
    
    # Connect and start listening in background
    async def run_streamer():
        await streamer.run()
    
    # Start the streamer in background
    streamer_task = asyncio.create_task(run_streamer())
    
    # Wait a bit for connection
    await asyncio.sleep(2)
    
    # Now add more markets dynamically
    additional_markets = [
        "KXNHLSPREAD-25NOV01CARBOS-BOS1",
        # Add more markets here
    ]
    
    print(f"\nAdding {len(additional_markets)} more markets...")
    for market in additional_markets:
        await streamer.subscribe_to_market(market)
        await asyncio.sleep(0.5)  # Small delay between subscriptions
    
    print(f"\nNow subscribed to {len(streamer.subscribed_markets)} markets total")
    print("Streamer is running. Press Ctrl+C to stop.")
    
    # Wait for streamer to run
    try:
        await streamer_task
    except KeyboardInterrupt:
        await streamer.close()


async def example_multiple_markets_from_start():
    """
    Example: Subscribe to multiple markets from the beginning.
    """
    print("=== Example: Multiple Markets from Start ===\n")
    
    # List of markets you want to monitor
    markets_to_monitor = [
        "KXMLBGAME-25OCT31LADTOR-LAD",
        "KXNHLSPREAD-25NOV01CARBOS-BOS1",
        # Add your markets here
    ]
    
    # Create streamer with all markets
    streamer = KalshiMarketStreamer(market_ids=markets_to_monitor)
    
    # Run it
    try:
        await streamer.run()
    except KeyboardInterrupt:
        await streamer.close()


async def example_from_external_script():
    """
    Example: How you would use this from another script.
    You can import and control the streamer programmatically.
    """
    print("=== Example: External Script Control ===\n")
    
    # Your list of markets (could come from a file, database, etc.)
    my_market_list = [
        "KXMLBGAME-25OCT31LADTOR-LAD",
        "KXNHLSPREAD-25NOV01CARBOS-BOS1",
    ]
    
    # Create streamer
    streamer = KalshiMarketStreamer(market_ids=my_market_list)
    
    # Connect
    if await streamer.connect():
        print("Connected! Now you can add more markets...")
        
        # Add markets dynamically
        new_markets = ["MARKET3", "MARKET4"]
        await streamer.subscribe_to_multiple_markets(new_markets)
        
        # Or add one at a time
        await streamer.subscribe_to_market("MARKET5")
        
        # Start listening
        await streamer.listen()
    else:
        print("Failed to connect")


async def example_trading_with_streamer():
    """
    Example: Using the streamer to trade based on real-time market data.
    
    IMPORTANT: WebSocket is READ-ONLY. Trading must be done via REST API.
    This example shows how to:
    1. Use WebSocket to receive real-time market updates
    2. Use callbacks to trigger trading logic
    3. Execute trades via REST API (streamer.api_client)
    """
    print("=== Example: Trading with WebSocket Streamer ===\n")
    print("⚠ NOTE: WebSocket is READ-ONLY. Trading uses REST API.\n")
    
    # Single market to trade
    market_id = "KXMLBGAME-25OCT31LADTOR-LAD"
    streamer = KalshiMarketStreamer(market_ids=[market_id], demo=True)  # Use demo=True for testing
    
    # Define trading callback that uses REST API
    async def on_orderbook_update_callback(orderbook_data, market_id):
        """
        This callback is triggered when orderbook updates arrive via WebSocket.
        Trading logic executes here using REST API.
        """
        # Extract orderbook data
        spread = None
        if 'yes_bid' in orderbook_data and 'yes_ask' in orderbook_data:
            spread = orderbook_data['yes_ask'] - orderbook_data['yes_bid']
        
        # Example: Place market making orders if spread is wide enough
        if spread and spread > 0.05:  # 5 cent spread threshold
            print(f"  → Wide spread detected: ${spread:.2f}, placing market making orders...")
            
            # Use REST API to place orders (NOT WebSocket!)
            result = streamer.place_market_making_orders(
                market_id,
                count=1,
                bid_offset=0.01,
                ask_offset=0.01
            )
            
            if result['buy_order'] and result['sell_order']:
                print(f"  ✓ Market making orders placed via REST API")
    
    # Set the callback
    streamer.on_orderbook_update = on_orderbook_update_callback
    
    # Connect
    if await streamer.connect():
        print(f"Connected! Monitoring {market_id}\n")
        
        # Check balance (via REST API)
        balance = streamer.get_balance()
        if balance:
            print(f"Current balance: ${balance / 100:.2f}\n")
        
        # Get current market prices (via REST API)
        best_bid = streamer.get_best_bid(market_id)
        best_ask = streamer.get_best_ask(market_id)
        spread = streamer.get_market_spread(market_id)
        
        if best_bid and best_ask:
            print(f"Market: {market_id}")
            print(f"Best Bid: ${best_bid:.2f}")
            print(f"Best Ask: ${best_ask:.2f}")
            print(f"Spread: ${spread:.2f}\n")
            
            # Example 1: Place a simple limit order (via REST API)
            print("Example 1: Placing a simple buy order via REST API...")
            buy_price = best_bid - 0.01  # Buy 1 cent below best bid
            buy_order = streamer.create_order(market_id, "buy", 1, buy_price)
            if buy_order:
                print(f"✓ Buy order placed: {buy_order.order_id if hasattr(buy_order, 'order_id') else 'N/A'}\n")
            
            # Example 2: Place market making orders (via REST API)
            print("Example 2: Placing market making orders via REST API...")
            mm_result = streamer.place_market_making_orders(
                market_id, 
                count=1, 
                bid_offset=0.01, 
                ask_offset=0.01
            )
            if mm_result['buy_order'] and mm_result['sell_order']:
                print(f"✓ Market making orders placed:")
                print(f"  Buy: ${mm_result['buy_price']:.2f}")
                print(f"  Sell: ${mm_result['sell_price']:.2f}\n")
            
            # Example 3: Check active orders
            print("Example 3: Checking active orders...")
            active_orders = streamer.get_active_orders(market_id)
            print(f"Active orders for {market_id}: {len(active_orders)}")
            for order_id, order_info in active_orders.items():
                print(f"  - {order_info['side'].upper()}: {order_info['count']} @ ${order_info['price']:.2f}")
        
        # Start listening for market updates (WebSocket receives, callbacks trigger REST API trades)
        print("\n" + "="*60)
        print("Streamer is now listening for market updates via WebSocket...")
        print("Trading callbacks will execute via REST API when conditions are met.")
        print("Press Ctrl+C to stop.")
        print("="*60 + "\n")
        
        try:
            await streamer.listen()
        except KeyboardInterrupt:
            print("\nShutting down...")
            # Cancel all orders before exiting (via REST API)
            cancelled = streamer.cancel_all_orders()
            print(f"Cancelled {cancelled} active orders")
            await streamer.close()
    else:
        print("Failed to connect")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket usage examples")
    parser.add_argument(
        "--example",
        type=str,
        choices=["dynamic", "multiple", "external", "trading"],
        default="multiple",
        help="Which example to run"
    )
    
    args = parser.parse_args()
    
    if args.example == "dynamic":
        asyncio.run(example_dynamic_subscriptions())
    elif args.example == "multiple":
        asyncio.run(example_multiple_markets_from_start())
    elif args.example == "external":
        asyncio.run(example_from_external_script())
    elif args.example == "trading":
        asyncio.run(example_trading_with_streamer())


