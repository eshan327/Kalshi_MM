#!/usr/bin/env python3
"""
Quick test of websocket connection - runs for 10 seconds then exits
"""
import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Import using importlib to handle the websocket directory
import importlib.util
websocket_dir = os.path.join(project_root, "websocket")
spec = importlib.util.spec_from_file_location("market_streamer", os.path.join(websocket_dir, "market_streamer.py"))
market_streamer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market_streamer)
KalshiMarketStreamer = market_streamer.KalshiMarketStreamer

async def quick_test():
    """Test websocket connection for 10 seconds"""
    print("="*60)
    print("Testing Kalshi WebSocket Connection (10 second test)")
    print("="*60)
    
    # Use a test market ID
    market_id = "KXMLBGAME-25OCT31LADTOR-LAD"
    
    # Check if we have credentials
    try:
        streamer = KalshiMarketStreamer(market_ids=[market_id], demo=True)
        if not streamer.api_key_id or not streamer.private_key:
            print("⚠ WARNING: Demo credentials not configured!")
            print("   The WebSocket connection may fail with HTTP 401.")
            print("   To fix: Set up demo credentials in Setup/demo_config_template.py")
            print("="*60)
    except Exception as e:
        print(f"Error initializing streamer: {e}")
        return
    
    # Create a task that will cancel after 10 seconds
    async def run_with_timeout():
        try:
            await streamer.run()
        except asyncio.CancelledError:
            print("\n[TEST] Timeout reached, shutting down...")
            await streamer.close()
    
    # Start the streamer
    task = asyncio.create_task(run_with_timeout())
    
    # Wait 10 seconds then cancel
    try:
        await asyncio.wait_for(task, timeout=10.0)
    except asyncio.TimeoutError:
        print("\n[TEST] 10 second timeout reached")
        task.cancel()
        streamer.shutdown()
        await streamer.close()
        print("[TEST] Test completed")

if __name__ == "__main__":
    try:
        asyncio.run(quick_test())
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    except Exception as e:
        print(f"\n[TEST] Error: {e}")
        import traceback
        traceback.print_exc()

