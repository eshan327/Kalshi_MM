import sys
import os

# Add project root to path BEFORE imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from Setup.apiSetup import KalshiAPI
import datetime
import time
import json
import argparse
import requests

# Force unbuffered output for log files
sys.stdout = sys.__stdout__  # Ensure we're using real stdout

class OrderBookListener:
    def __init__(self, marketId, demo=False):
        self.client = KalshiAPI().get_client(demo=demo)
        self.marketId = marketId
        self.demo = demo

    def get_order_book(self):
        """Fetch the current orderbook for the market using direct HTTP request."""
        # Use direct HTTP request since SDK has incorrect field mappings (expects true/false but API returns yes/no)
        config = self.client.api_client.configuration
        base_url = config.host
        
        # Build URL - API returns yes/no instead of true/false
        url = f"{base_url}/markets/{self.marketId}/orderbook"
        
        # Make direct HTTP request to get raw JSON
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for bad status codes
        
        # Return raw JSON data which has correct yes/no fields
        return response.json()

    def save_order_book(self, order_book_response, filename=None):
        """Append orderbook to JSON file with timestamp in data/orderbookData directory."""
        # Create data/orderbookData directory if it doesn't exist
        # Get project root directory (parent of Getdata)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        orderbook_dir = os.path.join(project_root, "data", "orderbookData")
        os.makedirs(orderbook_dir, exist_ok=True)
        
        # Default filename includes market ID to avoid conflicts
        if filename is None:
            # Sanitize market ID for filename (remove special chars)
            safe_market_id = self.marketId.replace('/', '_').replace('\\', '_')
            filename = f"orderBook_{safe_market_id}.json"
        
        # Always use just the basename (strip any path that might be provided)
        # This ensures files are ALWAYS saved to data/orderbookData directory
        filename_basename = os.path.basename(filename)
        filepath = os.path.join(orderbook_dir, filename_basename)
        
        # order_book_response is already a dict from direct HTTP request
        if isinstance(order_book_response, dict):
            orderbook_data = order_book_response
        else:
            # Fallback: convert to dict if it's not already
            if hasattr(order_book_response, 'model_dump'):
                orderbook_data = order_book_response.model_dump()
            elif hasattr(order_book_response, 'dict'):
                orderbook_data = order_book_response.dict()
            else:
                orderbook_data = str(order_book_response)
        
        # Prepare new snapshot
        new_snapshot = {
            "timestamp": datetime.datetime.now().isoformat(),
            "market_id": self.marketId,
            "order_book": orderbook_data
        }
        
        # Load existing data if file exists, otherwise start with empty list
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    existing_data = json.load(f)
                # Handle both old format (single object) and new format (array)
                if isinstance(existing_data, list):
                    # Already in array format, append to it
                    existing_data.append(new_snapshot)
                    all_data = existing_data
                else:
                    # Old format (single object), convert to array with old + new
                    all_data = [existing_data, new_snapshot]
            except (json.JSONDecodeError, IOError) as e:
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Warning: Could not read existing file, starting fresh: {e}")
                all_data = [new_snapshot]
        else:
            # File doesn't exist, start with new snapshot
            all_data = [new_snapshot]
        
        # Save all data (appending new snapshot to array)
        with open(filepath, "w") as f:
            json.dump(all_data, f, indent=2, default=str)
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        snapshot_count = len(all_data)
        print(f"[{timestamp}] Orderbook snapshot #{snapshot_count} saved for {self.marketId} to {filepath} (total snapshots: {snapshot_count})")
        sys.stdout.flush()

    def run(self, interval_minutes=5):
        """Continuously fetch and save orderbook at specified interval."""
        interval_seconds = interval_minutes * 60
        print(f"Starting orderbook listener for market: {self.marketId}")
        print(f"Fetching orderbook every {interval_minutes} minutes...")
        
        fetch_count = 0
        try:
            while True:
                fetch_count += 1
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"[{current_time}] === Fetch #{fetch_count} - Starting orderbook fetch for {self.marketId} ===")
                sys.stdout.flush()  # Force immediate write to log file
                
                try:
                    order_book = self.get_order_book()
                    self.save_order_book(order_book)
                    print(f"[{current_time}] ✓ Successfully fetched and saved orderbook (fetch #{fetch_count})")
                    sys.stdout.flush()
                except Exception as e:
                    print(f"[{current_time}] ✗ Error fetching orderbook (fetch #{fetch_count}): {e}")
                    sys.stdout.flush()
                
                # Wait for the specified interval before next fetch
                wait_start_time = datetime.datetime.now()
                next_fetch_time = (wait_start_time + datetime.timedelta(minutes=interval_minutes)).strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{wait_start_time.strftime('%Y-%m-%d %H:%M:%S')}] Waiting {interval_minutes} minutes until next fetch (next: {next_fetch_time})...")
                print(f"[{wait_start_time.strftime('%Y-%m-%d %H:%M:%S')}] Listener is active and will continue running...")
                sys.stdout.flush()
                
                # Sleep for the full interval
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\nOrderbook listener stopped by user")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OrderBook Listener - Monitor market orderbooks")
    parser.add_argument(
        "--market-id",
        type=str,
        required=True,
        help="Market ticker ID to monitor (e.g., KXNHLSPREAD-25NOV01CARBOS-BOS1)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Interval in minutes between orderbook fetches (default: 5)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo environment instead of production"
    )
    
    args = parser.parse_args()
    
    orderBookListener = OrderBookListener(marketId=args.market_id, demo=args.demo)
    orderBookListener.run(interval_minutes=args.interval)
