from kalshi_python import KalshiClient

def get_liquidity_rewards(client: KalshiClient):
    """Get liquidity rewards for a given market."""
    return client.get_liquidity_rewards()

if __name__ == "__main__":
    client = KalshiClient()
    print(get_liquidity_rewards(client))