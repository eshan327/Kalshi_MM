#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from Setup.apiSetup import KalshiAPI
import json

client = KalshiAPI().get_client()

# Check the market
market_id = "KXMLBGAME-25OCT31LADTOR-LAD"
print(f"Fetching orderbook for: {market_id}")
print("=" * 60)

try:
    response = client.get_market_orderbook(ticker=market_id)
    
    # Get full data
    if hasattr(response, 'model_dump'):
        data = response.model_dump()
    elif hasattr(response, 'dict'):
        data = response.dict()
    else:
        data = str(response)
    
    print("\nFull response structure:")
    print(json.dumps(data, indent=2, default=str))
    
    print("\n" + "=" * 60)
    print("Checking orderbook contents...")
    
    if 'orderbook' in data:
        orderbook = data['orderbook']
        print(f"Orderbook type: {type(orderbook)}")
        if isinstance(orderbook, dict):
            print(f"Orderbook keys: {list(orderbook.keys())}")
            for key, value in orderbook.items():
                print(f"  {key}: {value} (type: {type(value)})")
                if isinstance(value, dict):
                    print(f"    -> Keys: {list(value.keys())}")
        else:
            print(f"Orderbook value: {orderbook}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()


