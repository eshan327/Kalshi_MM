"""
Test script for Kalshi WebSocket connection.
Tests connection, authentication, and message reception.
"""

import sys
import os
import asyncio
import json
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import directly from the market_streamer module
# Use importlib to avoid conflicts with Python's built-in websocket module
import importlib.util
websocket_dir = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("market_streamer", os.path.join(websocket_dir, "market_streamer.py"))
market_streamer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market_streamer)
KalshiMarketStreamer = market_streamer.KalshiMarketStreamer


async def test_connection(market_id: str, demo: bool = False, timeout: int = 30):
    """
    Test the websocket connection and print received messages.
    
    Args:
        market_id: Market ticker to subscribe to
        demo: Use demo environment
        timeout: Seconds to wait for messages before stopping
    """
    print(f"\n{'='*60}")
    print(f"Testing Kalshi WebSocket Connection")
    print(f"{'='*60}")
    print(f"Market ID: {market_id}")
    print(f"Environment: {'DEMO' if demo else 'PRODUCTION'}")
    print(f"Timeout: {timeout} seconds")
    print(f"{'='*60}\n")
    
    streamer = KalshiMarketStreamer(market_id=market_id, demo=demo)
    
    # Track test results
    test_results = {
        "connected": False,
        "authenticated": False,
        "subscribed": False,
        "messages_received": 0,
        "errors": []
    }
    
    try:
        # Test connection
        print(f"[{datetime.now().isoformat()}] Testing connection...")
        if await streamer.connect():
            test_results["connected"] = True
            print(f"[{datetime.now().isoformat()}] ✓ Connection successful")
        else:
            print(f"[{datetime.now().isoformat()}] ✗ Connection failed")
            return test_results
        
        # Override message handler to track messages
        original_handle_message = streamer.handle_message
        
        async def test_handle_message(message: str):
            """Track messages for testing."""
            test_results["messages_received"] += 1
            print(f"[{datetime.now().isoformat()}] 📨 Message #{test_results['messages_received']} received")
            
            # Try to parse and show message type
            try:
                data = json.loads(message)
                msg_type = data.get("type", "unknown")
                print(f"  └─ Type: {msg_type}")
                
                # Check for authentication success
                if msg_type == "auth_success" or "auth" in str(data).lower():
                    test_results["authenticated"] = True
                    print(f"  └─ ✓ Authentication confirmed")
                
                # Check for subscription success
                if msg_type in ["subscribe_success", "subscribed", "success"] or "subscribe" in str(data).lower():
                    test_results["subscribed"] = True
                    print(f"  └─ ✓ Subscription confirmed")
                
                # Show first few fields for debugging
                if test_results["messages_received"] <= 3:
                    print(f"  └─ Data preview: {json.dumps(data, indent=2)[:200]}...")
            except:
                pass
            
            # Call original handler
            await original_handle_message(message)
        
        streamer.handle_message = test_handle_message
        
        # Listen for messages with timeout
        print(f"\n[{datetime.now().isoformat()}] 👂 Listening for messages (timeout: {timeout}s)...")
        print(f"[{datetime.now().isoformat()}] Waiting for messages...\n")
        
        try:
            # Listen for messages with timeout
            end_time = asyncio.get_event_loop().time() + timeout
            message_count_before = test_results["messages_received"]
            
            while asyncio.get_event_loop().time() < end_time:
                try:
                    # Wait for message with remaining timeout
                    remaining = end_time - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    
                    message = await asyncio.wait_for(streamer.ws.recv(), timeout=min(remaining, 5.0))
                    await streamer.handle_message(message)
                    
                except asyncio.TimeoutError:
                    # Check if we received any messages
                    if test_results["messages_received"] > message_count_before:
                        message_count_before = test_results["messages_received"]
                        # Continue listening
                        continue
                    else:
                        # No messages yet, but continue
                        print(f"[{datetime.now().isoformat()}] ⏳ Still waiting for messages...")
                        continue
                        
        except Exception as e:
            test_results["errors"].append(str(e))
            print(f"[{datetime.now().isoformat()}] ✗ Error during message listening: {e}")
        
        # Close connection
        await streamer.close()
        
    except Exception as e:
        test_results["errors"].append(str(e))
        print(f"[{datetime.now().isoformat()}] ✗ Test error: {e}")
    
    # Print test summary
    print(f"\n{'='*60}")
    print(f"Test Summary")
    print(f"{'='*60}")
    print(f"Connection:     {'✓ PASS' if test_results['connected'] else '✗ FAIL'}")
    print(f"Authentication: {'✓ PASS' if test_results['authenticated'] else '? UNKNOWN'}")
    print(f"Subscription:   {'✓ PASS' if test_results['subscribed'] else '? UNKNOWN'}")
    print(f"Messages:       {test_results['messages_received']} received")
    
    if test_results["errors"]:
        print(f"\nErrors encountered:")
        for error in test_results["errors"]:
            print(f"  - {error}")
    
    print(f"{'='*60}\n")
    
    return test_results


async def quick_test(market_id: str, demo: bool = False):
    """Quick connection test - just verify we can connect."""
    print(f"\n[{datetime.now().isoformat()}] Quick Connection Test")
    print(f"Market: {market_id}, Demo: {demo}\n")
    
    streamer = KalshiMarketStreamer(market_id=market_id, demo=demo)
    
    try:
        if await streamer.connect():
            print(f"[{datetime.now().isoformat()}] ✓ Connection successful!")
            print(f"[{datetime.now().isoformat()}] Connection URL: {streamer.ws_url}")
            print(f"[{datetime.now().isoformat()}] WebSocket state: {streamer.ws.state if streamer.ws else 'None'}")
            
            # Wait a moment to see if we get any initial messages
            print(f"[{datetime.now().isoformat()}] Waiting 5 seconds for initial messages...")
            try:
                message = await asyncio.wait_for(streamer.ws.recv(), timeout=5.0)
                print(f"[{datetime.now().isoformat()}] ✓ Received message: {message[:100]}...")
            except asyncio.TimeoutError:
                print(f"[{datetime.now().isoformat()}] ⏳ No messages in first 5 seconds")
            
            await streamer.close()
            return True
        else:
            print(f"[{datetime.now().isoformat()}] ✗ Connection failed")
            return False
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ✗ Error: {e}")
        return False


async def main():
    """Main test entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test Kalshi WebSocket Connection"
    )
    parser.add_argument(
        "--market-id",
        type=str,
        required=True,
        help="Market ticker ID to test (e.g., KXMLBGAME-25OCT31LADTOR-LAD)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo environment"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick connection test only (5 seconds)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Seconds to wait for messages (default: 30)"
    )
    
    args = parser.parse_args()
    
    if args.quick:
        success = await quick_test(args.market_id, args.demo)
        sys.exit(0 if success else 1)
    else:
        results = await test_connection(args.market_id, args.demo, args.timeout)
        # Exit with error code if connection failed
        sys.exit(0 if results["connected"] else 1)


if __name__ == "__main__":
    asyncio.run(main())

