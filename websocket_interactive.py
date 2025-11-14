#!/usr/bin/env python3
"""
Interactive WebSocket streamer with dynamic channel subscription/unsubscription.
Allows you to subscribe/unsubscribe to channels while the websocket is running.
"""

import asyncio
import sys
import os
from datetime import datetime
from collections import deque

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__))))

from Websocket.market_streamer import KalshiMarketStreamer


class InteractiveWebSocket:
    """Interactive websocket controller with command interface."""
    
    def __init__(self, market_ids: list, demo: bool = False, channels: list = None):
        self.streamer = KalshiMarketStreamer(market_ids=market_ids, demo=demo, channels=channels)
        self.running = True
        self.streamer_task = None
        self.message_queue = deque(maxlen=100)  # Store recent messages
        self.print_lock = asyncio.Lock()  # Lock for printing to avoid conflicts
        self.silent_mode = False  # Option to silence message printing
        
    async def start(self):
        """Start the websocket connection."""
        print(f"[{datetime.now().isoformat()}] Connecting to websocket...")
        if await self.streamer.connect():
            print(f"[{datetime.now().isoformat()}] ✓ Connected!")
            
            # Override the message handler to use our queue
            original_handle = self.streamer.handle_message
            async def wrapped_handle(message):
                await original_handle(message)
                # Store message for later display if needed
                self.message_queue.append((datetime.now(), message))
            
            self.streamer.handle_message = wrapped_handle
            
            # Start listening in background task
            self.streamer_task = asyncio.create_task(self.streamer.listen())
            return True
        else:
            print(f"[{datetime.now().isoformat()}] ✗ Connection failed")
            return False
    
    async def handle_command(self, command: str):
        """Handle user commands."""
        parts = command.strip().split()
        if not parts:
            return
        
        cmd = parts[0].lower()
        
        # Use lock to prevent message printing conflicts
        async with self.print_lock:
            if cmd == "help" or cmd == "?":
                self.print_help()
            elif cmd == "subscribe" or cmd == "sub":
                if len(parts) < 3:
                    print("Usage: subscribe <market_id> <channel1> [channel2] ...")
                    print("Example: subscribe KXMLBGAME-25OCT31LADTOR-LAD fill position")
                    return
                market_id = parts[1]
                channels = parts[2:]
                await self.subscribe_channels(market_id, channels)
            elif cmd == "unsubscribe" or cmd == "unsub":
                if len(parts) < 2:
                    print("Usage: unsubscribe <market_id> [channel1] [channel2] ...")
                    print("Example: unsubscribe KXMLBGAME-25OCT31LADTOR-LAD fill")
                    print("Or: unsubscribe KXMLBGAME-25OCT31LADTOR-LAD  (unsubscribes from all channels)")
                    return
                market_id = parts[1]
                channels = parts[2:] if len(parts) > 2 else None
                await self.unsubscribe_channels(market_id, channels)
            elif cmd == "list" or cmd == "ls":
                await self.list_subscriptions()
            elif cmd == "markets" or cmd == "m":
                self.list_markets()
            elif cmd == "channels" or cmd == "ch":
                self.list_available_channels()
            elif cmd == "quit" or cmd == "exit" or cmd == "q":
                self.running = False
            else:
                print(f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    async def subscribe_channels(self, market_id: str, channels: list):
        """Subscribe to channels for a market."""
        # Validate channels
        valid_channels = ["ticker", "orderbook_delta", "trade", "fill", "position"]
        invalid_channels = [ch for ch in channels if ch not in valid_channels]
        if invalid_channels:
            print(f"Error: Invalid channels: {invalid_channels}")
            print(f"Valid channels are: {valid_channels}")
            return
        
        print(f"[{datetime.now().isoformat()}] Subscribing to {market_id} channels: {channels}")
        await self.streamer.subscribe_to_market(market_id, channels=channels)
        print(f"[{datetime.now().isoformat()}] ✓ Subscription sent")
    
    async def unsubscribe_channels(self, market_id: str, channels: list = None):
        """Unsubscribe from channels for a market."""
        # First, list subscriptions to get current SIDs
        # Note: SID tracking might not be complete, so we'll use list_subscriptions
        # For now, we'll send unsubscribe command and let the server handle it
        # The proper way would be to track SIDs from "subscribed" responses
        
        if channels is None:
            # Unsubscribe from all channels for this market
            print(f"[{datetime.now().isoformat()}] Unsubscribing from all channels for {market_id}")
            # Try to get SIDs from subscribed_markets
            sids = []
            if market_id in self.streamer.subscribed_markets:
                for channel, sid in self.streamer.subscribed_markets[market_id].items():
                    if sid:
                        sids.append(sid)
            
            if sids:
                await self.streamer.unsubscribe(sids)
                # Clear from tracking
                self.streamer.subscribed_markets[market_id] = {}
                print(f"[{datetime.now().isoformat()}] ✓ Unsubscribed from {len(sids)} channel(s)")
            else:
                print(f"[{datetime.now().isoformat()}] ⚠ No SIDs found. You may need to use 'list' command first to see active subscriptions.")
                print(f"[{datetime.now().isoformat()}] Note: SID tracking requires 'subscribed' responses from server.")
        else:
            # Unsubscribe from specific channels
            print(f"[{datetime.now().isoformat()}] Unsubscribing from {market_id} channels: {channels}")
            # Get SIDs for specific channels
            sids = []
            if market_id in self.streamer.subscribed_markets:
                for channel in channels:
                    if channel in self.streamer.subscribed_markets[market_id]:
                        sid = self.streamer.subscribed_markets[market_id][channel]
                        if sid:
                            sids.append(sid)
                        # Remove from tracking
                        del self.streamer.subscribed_markets[market_id][channel]
            
            if sids:
                await self.streamer.unsubscribe(sids)
                print(f"[{datetime.now().isoformat()}] ✓ Unsubscribed from {len(sids)} channel(s)")
            else:
                print(f"[{datetime.now().isoformat()}] ⚠ No matching subscriptions found with SIDs.")
                print(f"[{datetime.now().isoformat()}] Note: SID tracking may not be complete. Try 'list' command first.")
    
    async def list_subscriptions(self):
        """List all current subscriptions."""
        print(f"\n[{datetime.now().isoformat()}] Current Subscriptions:")
        print("=" * 60)
        if self.streamer.subscribed_markets:
            for market_id, channels in self.streamer.subscribed_markets.items():
                if channels:
                    channel_list = ", ".join(channels.keys())
                    print(f"  {market_id}:")
                    print(f"    Channels: {channel_list}")
                else:
                    print(f"  {market_id}: (no active channels)")
        else:
            print("  No active subscriptions")
        print("=" * 60 + "\n")
        
        # Also request list from server
        await self.streamer.list_subscriptions()
    
    def list_markets(self):
        """List all markets being monitored."""
        print(f"\n[{datetime.now().isoformat()}] Monitored Markets:")
        print("=" * 60)
        for i, market_id in enumerate(self.streamer.market_ids, 1):
            print(f"  {i}. {market_id}")
        print("=" * 60 + "\n")
    
    def list_available_channels(self):
        """List available channels."""
        print(f"\n[{datetime.now().isoformat()}] Available Channels:")
        print("=" * 60)
        channels = {
            "ticker": "Real-time ticker updates (last price, volume, etc.)",
            "orderbook_delta": "Orderbook updates (bid/ask changes)",
            "trade": "Public trade executions",
            "fill": "Your fill notifications (requires authentication)",
            "position": "Position updates (requires authentication)"
        }
        for channel, description in channels.items():
            print(f"  {channel:20} - {description}")
        print("=" * 60 + "\n")
    
    def print_help(self):
        """Print help message."""
        print("\n" + "=" * 60)
        print("Interactive WebSocket Commands:")
        print("=" * 60)
        print("  subscribe <market_id> <channel1> [channel2] ...")
        print("    Subscribe to channels for a market")
        print("    Example: subscribe KXMLBGAME-25OCT31LADTOR-LAD fill position")
        print()
        print("  unsubscribe <market_id> [channel1] [channel2] ...")
        print("    Unsubscribe from channels (or all if no channels specified)")
        print("    Example: unsubscribe KXMLBGAME-25OCT31LADTOR-LAD fill")
        print("    Example: unsubscribe KXMLBGAME-25OCT31LADTOR-LAD  (all channels)")
        print()
        print("  list (or ls)")
        print("    List all current subscriptions")
        print()
        print("  markets (or m)")
        print("    List all markets being monitored")
        print()
        print("  channels (or ch)")
        print("    List available channels")
        print()
        print("  help (or ?)")
        print("    Show this help message")
        print()
        print("  quit (or exit, q)")
        print("    Exit the interactive session")
        print("=" * 60 + "\n")
    
    async def read_input(self):
        """Read input from stdin asynchronously."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                # Read a line from stdin (this blocks, but in executor)
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                return line.strip()
            except Exception as e:
                if self.running:
                    print(f"Input error: {e}")
                break
        return None
    
    async def run_interactive(self):
        """Run the interactive command loop."""
        print("\n" + "=" * 60)
        print("Interactive WebSocket Streamer")
        print("=" * 60)
        print("Type 'help' for available commands")
        print("Type 'quit' to exit")
        print("Messages will appear above the prompt")
        print("=" * 60 + "\n")
        
        # Start input reading task
        input_task = None
        
        while self.running:
            try:
                # Print prompt on a new line to avoid conflicts with message printing
                async with self.print_lock:
                    print("\n> ", end="", flush=True)
                
                # Read command (this will block until input is received)
                command = await self.read_input()
                if not command:
                    break
                    
                if command:
                    async with self.print_lock:
                        await self.handle_command(command)
                    
            except KeyboardInterrupt:
                print("\nReceived interrupt signal")
                self.running = False
                break
            except EOFError:
                break
            except Exception as e:
                async with self.print_lock:
                    print(f"Error: {e}")
        
        # Cleanup
        print(f"\n[{datetime.now().isoformat()}] Shutting down...")
        self.streamer.shutdown()
        if self.streamer_task:
            self.streamer_task.cancel()
            try:
                await self.streamer_task
            except asyncio.CancelledError:
                pass
        await self.streamer.close()


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Interactive WebSocket Streamer - Subscribe/unsubscribe to channels dynamically"
    )
    parser.add_argument(
        "--market-id",
        type=str,
        help="Single market ticker ID to stream"
    )
    parser.add_argument(
        "--market-ids",
        type=str,
        nargs="+",
        help="Multiple market ticker IDs to stream"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo environment instead of production"
    )
    parser.add_argument(
        "--channels",
        type=str,
        nargs="+",
        help="Initial channels to subscribe to (default: ticker orderbook_delta trade)"
    )
    
    args = parser.parse_args()
    
    # Determine which markets to use
    if args.market_ids:
        market_ids = args.market_ids
    elif args.market_id:
        market_ids = [args.market_id]
    else:
        parser.error("Either --market-id or --market-ids must be provided")
    
    # Validate channels if provided
    if args.channels:
        valid_channels = ["ticker", "orderbook_delta", "trade", "fill", "position"]
        invalid_channels = [ch for ch in args.channels if ch not in valid_channels]
        if invalid_channels:
            parser.error(f"Invalid channels: {invalid_channels}. Valid channels are: {valid_channels}")
    
    # Create interactive controller
    controller = InteractiveWebSocket(market_ids=market_ids, demo=args.demo, channels=args.channels)
    
    # Start websocket
    if await controller.start():
        # Run interactive loop
        await controller.run_interactive()
    else:
        print("Failed to start websocket")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")

