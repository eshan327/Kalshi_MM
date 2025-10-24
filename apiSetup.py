from kalshi_python import Configuration, KalshiClient

class KalshiAPI:

    def get_client(self):
        # Configure the client
        config = Configuration(
            host="https://api.elections.kalshi.com/trade-api/v2"
        )

        # For authenticated requests
        # Read private key from file
        with open("your_private_key.pem", "r") as f:
            private_key = f.read()

        config.api_key_id = "c117c03d-22f9-4826-bdf9-42cfdc2cf436"
        config.private_key_pem = private_key

        # Initialize the client
        client = KalshiClient(config)
        return client