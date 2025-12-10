"""
Kalshi API Setup and Authentication.

This module provides the KalshiAPI class for connecting to Kalshi's trading API.
It handles authentication via RSA private keys and supports both demo and 
production environments.

Usage:
    from Setup.apiSetup import KalshiAPI
    
    # Production
    client = KalshiAPI().get_client(demo=False)
    
    # Demo (safe testing)
    client = KalshiAPI().get_client(demo=True)
    
    # Use the client
    balance = client.get_balance()
    markets = client.get_markets(limit=100)

Configuration:
    1. Create Setup/config.py from config_template.py
    2. Set PRODUCTION_API_KEY_ID and/or DEMO_API_KEY_ID
    3. Place private key files: private_key.pem, private_demo_key.pem
"""

from kalshi_python import KalshiClient
from kalshi_python.configuration import Configuration
import os
import sys

# Add Setup directory to path for local imports
SETUP_DIR = os.path.dirname(os.path.abspath(__file__))
if SETUP_DIR not in sys.path:
    sys.path.insert(0, SETUP_DIR)

# Try to import config, fallback if it doesn't exist
PRODUCTION_API_KEY_ID = None
DEMO_API_KEY_ID = None
try:
    from config import PRODUCTION_API_KEY_ID, DEMO_API_KEY_ID
except (ImportError, ModuleNotFoundError) as e:
    # Fallback: try to use environment variables
    PRODUCTION_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID", None)
    DEMO_API_KEY_ID = os.environ.get("KALSHI_DEMO_API_KEY_ID", None)
    if PRODUCTION_API_KEY_ID is None:
        print("Warning: config.py not found. Create it from config_template.py")
        print("Or set KALSHI_API_KEY_ID environment variable.")

# Private key file paths
PRODUCTION_PRIVATE_KEY_FILE = os.path.join(SETUP_DIR, "private_key.pem")
DEMO_PRIVATE_KEY_FILE = os.path.join(SETUP_DIR, "private_demo_key.pem")


class KalshiAPI:

    def get_client(self, demo=False):
        if demo:
            # Demo environment configuration
            config = Configuration(
                host="https://demo-api.kalshi.co/trade-api/v2"
            )
            print("Using Kalshi DEMO environment")
        else:
            # Production environment configuration
            config = Configuration(
                host="https://api.elections.kalshi.com/trade-api/v2"
            )
            print("Using Kalshi PRODUCTION environment")

        # For authenticated requests
        try:
            if demo:
                # Use demo private key from file
                with open(DEMO_PRIVATE_KEY_FILE, "r") as f:
                    private_key = f.read()
                config.api_key_id = DEMO_API_KEY_ID
                config.private_key_pem = private_key
            else:
                # Use production private key from file in Setup directory
                production_key_path = os.path.join(SETUP_DIR, "private_key.pem")
                with open(production_key_path, "r") as f:
                    private_key = f.read()
                
                # Get API key ID from config file or environment variable
                if PRODUCTION_API_KEY_ID is None:
                    raise ValueError(
                        "Production API key ID not found. "
                        "Create Setup/config.py from config_template.py "
                        "or set KALSHI_API_KEY_ID environment variable."
                    )
                
                config.api_key_id = PRODUCTION_API_KEY_ID
                config.private_key_pem = private_key
            
        except FileNotFoundError as e:
            print(f"Warning: Private key file not found: {e}")
            print("Using unauthenticated client. Some features may be limited.")

        # Initialize the client
        client = KalshiClient(config)
        return client