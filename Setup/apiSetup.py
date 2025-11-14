from kalshi_python import Configuration, KalshiClient
import os
import sys

# Add Setup directory to path for local imports
SETUP_DIR = os.path.dirname(os.path.abspath(__file__))
if SETUP_DIR not in sys.path:
    sys.path.insert(0, SETUP_DIR)

from demo_config_template import DEMO_PRIVATE_KEY_FILE, DEMO_API_KEY_ID

# Try to import production config, fallback if it doesn't exist
PRODUCTION_API_KEY_ID = None
try:
    # Ensure Setup directory is in path for import
    if SETUP_DIR not in sys.path:
        sys.path.insert(0, SETUP_DIR)
    from config import PRODUCTION_API_KEY_ID
except (ImportError, ModuleNotFoundError) as e:
    # Fallback: try to use environment variable
    PRODUCTION_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID", None)
    if PRODUCTION_API_KEY_ID is None:
        print("Warning: config.py not found. Create it from config_template.py")
        print("Or set KALSHI_API_KEY_ID environment variable.")


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
                        "Create Setup/production_config.py from production_config_template.py "
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