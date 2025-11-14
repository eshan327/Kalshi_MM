import os
import sys

# Add Setup directory to path for imports
SETUP_DIR = os.path.join(os.path.dirname(__file__), "Setup")
if SETUP_DIR not in sys.path:
    sys.path.insert(0, SETUP_DIR)

from Setup.apiSetup import KalshiAPI

# Use the KalshiAPI class for proper setup
api = KalshiAPI()
client = api.get_client(demo=False)  # Use demo=True for demo environment

# Make API calls
balance = client.get_balance()
print(f"Balance: ${balance.balance / 100:.2f}")
