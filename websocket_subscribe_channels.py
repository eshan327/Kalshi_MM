#!/usr/bin/env python3
"""
Script to subscribe to additional channels on an already running websocket.
This connects to the websocket and adds more channels to existing subscriptions.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__))))

from Websocket.market_streamer import KalshiMarketStreamer


async def subscribe_to_channels(market_id: str, channels: list, demo: bool = False):
    """
    Connect to websocket and subscribe to additional channels.
    
    Args:
        market_id: Market ticker ID
        channels: List of channels to subscribe to (e.g., ["fill", "position"])
        demo: Whether to use demo environment
    """
    print(f"Connecting to websocket for market: {market_id}")
    print(f"Channels to subscribe: {channels}")
    
    # Create streamer (don't pass market_ids to avoid auto-subscribing)
    streamer = KalshiMarketStreamer(market_ids=[market_id], demo=demo)
    
    try:
        # Connect
        if await streamer.connect():
            print(f"\n✓ Connected! Now subscribing to additional channels...")
            
            # Subscribe to the additional channels
            await streamer.subscribe_to_market(market_id, channels=channels)
            
            print(f"\n✓ Subscribed to channels: {channels}")
            print(f"Now listening for updates. Press Ctrl+C to stop.\n")
            
            # Start listening
            await streamer.listen()
        else:
            print("Failed to connect")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await streamer.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Subscribe to additional websocket channels"
    )
    parser.add_argument(
        "--market-id",
        type=str,
        required=True,
        help="Market ticker ID (e.g., KXMLBGAME-25OCT31LADTOR-LAD)"
    )
    parser.add_argument(
        "--channels",
        type=str,
        nargs="+",
        required=True,
        help="Channels to subscribe to (e.g., fill position)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo environment"
    )
    
    args = parser.parse_args()
    
    # Available channels
    valid_channels = ["ticker", "orderbook_delta", "trade", "fill", "position"]
    
    # Validate channels
    invalid_channels = [ch for ch in args.channels if ch not in valid_channels]
    if invalid_channels:
        print(f"Error: Invalid channels: {invalid_channels}")
        print(f"Valid channels are: {valid_channels}")
        sys.exit(1)
    
    asyncio.run(subscribe_to_channels(args.market_id, args.channels, args.demo))

