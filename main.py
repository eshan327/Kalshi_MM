from kalshi_python import KalshiClient
from kalshi_python.configuration import Configuration

# Configure the client
config = Configuration(
    host="https://api.elections.kalshi.com/trade-api/v2"
)

# For authenticated requests
# Read private key from file
with open("private_key.pem", "r") as f:
    private_key = f.read()

config.api_key_id = "5a4cf889-b4c4-4d5e-b855-e9d1218f3bf2"
config.private_key_pem = private_key

# Initialize the client
client = KalshiClient(config)

# Make API calls
balance = client.get_balance()
print(f"Balance: ${balance.balance / 100:.2f}")