import os
import asyncio
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization

from clients import KalshiHttpClient, KalshiWebSocketClient, Environment
from market_maker import market_making  # Import the market making function

# Load environment variables
load_dotenv()
env = Environment.PROD # Toggle environment
KEYID = os.getenv('DEMO_KEYID') if env == Environment.DEMO else os.getenv('PROD_KEYID')
KEYFILE = os.getenv('DEMO_KEYFILE') if env == Environment.DEMO else os.getenv('PROD_KEYFILE')

try:
    with open(KEYFILE, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password = None  # Add password if key is encrypted
        )
except FileNotFoundError:
    raise FileNotFoundError(f"Private key file not found at {KEYFILE}")
except Exception as e:
    raise Exception(f"Error loading private key: {str(e)}")

# Initialize an instance of the HTTP client
client = KalshiHttpClient(
    key_id=KEYID,
    private_key=private_key,
    environment=env
)

# Get account balance
balance = client.get_balance()
print("Balance:", balance)

# Fetch all markets
markets_response = client.get_all_markets()
all_markets = markets_response.get('markets', [])

# Example filter: find only the “High Denver” ticker
climate_markets = [
    m for m in all_markets
    if "HIGHDEN" in m.get('market_ticker', '')
]

# Collect IDs for subscription
climate_market_ids = [m['market_id'] for m in climate_markets]

# Initialize the WebSocket client
ws_client = KalshiWebSocketClient(
    key_id=KEYID,
    private_key=private_key,
    environment=env
)
ws_client.climate_market_ids = climate_market_ids  # store for later use

async def main():
    # Run WebSocket connection and market making concurrently
    await asyncio.gather(
        ws_client.connect(),
        market_making(client, climate_markets)
    )

# Run the main function
asyncio.run(main())