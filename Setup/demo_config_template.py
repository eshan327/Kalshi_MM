# Demo Configuration for Kalshi
# Copy this file to demo_config.py and fill in your demo credentials

import os
import config

# Get the Setup directory path
SETUP_DIR = os.path.dirname(os.path.abspath(__file__))

# Demo API credentials (get these from Kalshi demo environment)
DEMO_API_KEY_ID = config.DEMO_API_KEY_ID
DEMO_PRIVATE_KEY_FILE = os.path.join(SETUP_DIR, "private_demo_key.pem")

# Demo environment settings
DEMO_HOST = "https://demo-api.kalshi.co/trade-api/v2"

# Trading parameters for demo
DEMO_RESERVE_LIMIT = 10  # Keep $10 in reserve
DEMO_MIN_SPREAD = 0.03   # Minimum spread threshold
DEMO_ORDER_SIZE = 1      # Number of contracts per order