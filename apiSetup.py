from kalshi_python import Configuration, KalshiClient
import os
from demo_config_template import DEMO_PRIVATE_KEY_FILE, DEMO_API_KEY_ID


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
                # Use production private key from file
                with open("your_api_password_file", "r") as f:
                    private_key = f.read()
                config.api_key_id = "c117c03d-22f9-4826-bdf9-42cfdc2cf436"
                config.private_key_pem = private_key
            
        except FileNotFoundError as e:
            print(f"Warning: Private key file not found: {e}")
            print("Using unauthenticated client. Some features may be limited.")

        # Initialize the client
        client = KalshiClient(config)
        return client