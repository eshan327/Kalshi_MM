from kalshi_python import KalshiClient
from kalshi_python.configuration import Configuration
import requests
import sys

config = Configuration(
    host="https://api.elections.kalshi.com/trade-api/v2"
)

try:
    with open("private_key.pem", "r") as f:
        private_key = f.read()
except FileNotFoundError:
    print("private_key.pem not found.")
    sys.exit(1)

config.api_key_id = "5a4cf889-b4c4-4d5e-b855-e9d1218f3bf2"
config.private_key_pem = private_key
client = KalshiClient(config)

# Getting the balance
try:
    balance = client.get_balance()
    print(f"Balance: ${balance.balance / 100:.2f}")
except Exception as e:
    print(f"Error getting balance: {e}")
    sys.exit(1)

# Series information for KXHIGHNY
BASE_API_URL = "https://api.elections.kalshi.com/trade-api/v2" 
url = f"{BASE_API_URL}/series/KXHIGHNY"
response = requests.get(url)
series_data = response.json()
print(f"\nSeries Title: {series_data['series']['title']}")

# Gets all KXHIGHNY markets 
markets_url = f"{BASE_API_URL}/markets?series_ticker=KXHIGHNY&status=open"
markets_response = requests.get(markets_url)
markets_data = markets_response.json()
market_list = markets_data.get('markets', [])
print(f"Found {len(market_list)} open markets for this series.")


# Gets bid, ask, and spread for each market in a dict 
def get_market_metrics(orderbook_data):
    
    orderbook = orderbook_data.get('orderbook', {})
    yes_bids = orderbook.get('yes', [])
    no_bids = orderbook.get('no', [])
    metrics = {'bid': None, 'ask': None, 'spread': None}

    # Best YES Bid
    if yes_bids:
        metrics['bid'] = yes_bids[-1][0]  # Get price from [price, qty]

    # Best YES Ask
    if no_bids:
        best_no_bid = no_bids[-1][0]
        metrics['ask'] = 100 - best_no_bid

    # Spread
    if metrics['bid'] is not None and metrics['ask'] is not None:
        spread = metrics['ask'] - metrics['bid']
        if spread > 0:
            metrics['spread'] = spread
    
    return metrics

DESIRABLE_SPREAD = 5 # Set the minimum spread to market make on
profitable_markets = []

print(f"\n--- All Active {series_data['series']['title']} Markets ---")
print(f"(Analyzing spreads, target >= {DESIRABLE_SPREAD}¢)\n")

if market_list:
    for market in market_list:
        market_ticker = market['ticker']
        print(f"- {market_ticker}: {market['title']}")
        
        # Fetch the orderbook for this specific market
        orderbook_url = f"{BASE_API_URL}/markets/{market_ticker}/orderbook"
        try:
            orderbook_response = requests.get(orderbook_url)
            orderbook_data = orderbook_response.json()
            
            metrics = get_market_metrics(orderbook_data)
            
            bid_str = f"{metrics['bid']}¢" if metrics['bid'] is not None else "N/A"
            ask_str = f"{metrics['ask']}¢" if metrics['ask'] is not None else "N/A"
            spread_str = f"{metrics['spread']}¢" if metrics['spread'] is not None else "N/A"

            print(f"  Bid: {bid_str} | Ask: {ask_str} | Spread: {spread_str}")
            print()

            # Check profitability
            if metrics['spread'] is not None and metrics['spread'] >= DESIRABLE_SPREAD:
                profitable_markets.append({
                    'ticker': market_ticker,
                    'bid': metrics['bid'],
                    'ask': metrics['ask'],
                    'spread': metrics['spread']
                })
                
        except Exception as e:
            print(f"  Error fetching orderbook for market {e}\n")
            pass

    print("-" * 30)
    print("--- Desirable Markets ---")
    if profitable_markets:
        print(f"\nFound {len(profitable_markets)} markets with spread >= {DESIRABLE_SPREAD}¢:")
        for market in profitable_markets:
            print(f"  - {market['ticker']}")
            print(f"    Bid: {market['bid']}¢ | Ask: {market['ask']}¢ | Spread: {market['spread']}¢")
    else:
        print(f"\nNo markets have a spread >= {DESIRABLE_SPREAD}¢.")

else:
    print("No open markets.")