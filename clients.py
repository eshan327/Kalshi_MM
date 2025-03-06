import requests
import base64
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum
import json

import pytz
import websockets
from requests.exceptions import HTTPError

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

class Environment(Enum):
    DEMO = "demo"
    PROD = "prod"

class KalshiBaseClient:
    """Base client class for interacting with the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.PROD,
    ):
        """Initializes the client with the provided API key and private key.

        Args:
            key_id (str): Your Kalshi API key ID.
            private_key (rsa.RSAPrivateKey): Your RSA private key.
            environment (Environment): The API environment to use (DEMO or PROD).
        """
        self.key_id = key_id
        self.private_key = private_key
        self.environment = environment
        self.last_api_call = datetime.now()

        if self.environment == Environment.DEMO:
            self.HTTP_BASE_URL = "https://demo-api.kalshi.co"
            self.WS_BASE_URL = "wss://demo-api.kalshi.co"
        elif self.environment == Environment.PROD:
            self.HTTP_BASE_URL = "https://api.elections.kalshi.com"
            self.WS_BASE_URL = "wss://api.elections.kalshi.com"
        else:
            raise ValueError("Invalid environment")

    def request_headers(self, method: str, path: str) -> Dict[str, Any]:
        """Generates the required authentication headers for API requests."""
        current_time_milliseconds = int(time.time() * 1000)
        timestamp_str = str(current_time_milliseconds)

        # Remove query parameters from path
        path_parts = path.split('?')

        msg_string = timestamp_str + method + path_parts[0]
        signature = self.sign_pss_text(msg_string)

        headers = {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
        }
        return headers

    def sign_pss_text(self, text: str) -> str:
        """Signs the text using RSA-PSS and returns the base64 encoded signature."""
        message = text.encode('utf-8')
        try:
            signature = self.private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except InvalidSignature as e:
            raise ValueError("RSA sign PSS failed") from e

class KalshiHttpClient(KalshiBaseClient):
    """Client for handling HTTP connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.PROD,
    ):
        super().__init__(key_id, private_key, environment)
        self.host = self.HTTP_BASE_URL
        self.exchange_url = "/trade-api/v2/exchange"
        self.markets_url = "/trade-api/v2/markets"
        self.portfolio_url = "/trade-api/v2/portfolio"
        self.orders_url = "/trade-api/v2/orders"

    def rate_limit(self) -> None:
        """Built-in rate limiter to prevent exceeding API rate limits."""
        THRESHOLD_IN_MILLISECONDS = 100
        now = datetime.now()
        threshold_in_microseconds = 1000 * THRESHOLD_IN_MILLISECONDS
        threshold_in_seconds = THRESHOLD_IN_MILLISECONDS / 1000
        if now - self.last_api_call < timedelta(microseconds=threshold_in_microseconds):
            time.sleep(threshold_in_seconds)
        self.last_api_call = datetime.now()

    def raise_if_bad_response(self, response: requests.Response) -> None:
        """Raises an HTTPError if the response status code indicates an error."""
        if response.status_code not in range(200, 299):
            response.raise_for_status()

    def post(self, path: str, body: dict) -> Any:
        """Performs an authenticated POST request to the Kalshi API."""
        self.rate_limit()
        response = requests.post(
            self.host + path,
            json=body,
            headers=self.request_headers("POST", path)
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated GET request to the Kalshi API."""
        self.rate_limit()
        response = requests.get(
            self.host + path,
            headers=self.request_headers("GET", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def delete(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated DELETE request to the Kalshi API."""
        self.rate_limit()
        response = requests.delete(
            self.host + path,
            headers=self.request_headers("DELETE", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get_balance(self) -> Dict[str, Any]:
        """Retrieves the account balance."""
        return self.get(self.portfolio_url + '/balance')

    def get_exchange_status(self) -> Dict[str, Any]:
        """Retrieves the exchange status."""
        return self.get(self.exchange_url + "/status")

    def get_trades(
        self,
        ticker: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        max_ts: Optional[int] = None,
        min_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieves trades based on provided filters."""
        params = {
            'ticker': ticker,
            'limit': limit,
            'cursor': cursor,
            'max_ts': max_ts,
            'min_ts': min_ts,
        }
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.markets_url + '/trades', params=params)

    def get_all_markets(self) -> Dict[str, Any]:
        """Retrieves all markets."""
        return self.get(self.markets_url)

    def place_order(self, market_id: str, side: str, price: int, size: int) -> Dict[str, Any]:
        """Places an order in the specified market."""
        order = {
            "market_id": market_id,
            "side": side,
            "price": price,
            "size": size
        }
        return self.post(self.orders_url, order)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancels an existing order."""
        return self.delete(f"{self.orders_url}/{order_id}")

    def get_orders(self) -> Dict[str, Any]:
        """Retrieves all open orders."""
        return self.get(self.orders_url)

class KalshiWebSocketClient(KalshiBaseClient):
    """Client for handling WebSocket connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.PROD,
    ):
        super().__init__(key_id, private_key, environment)
        self.ws = None
        self.url_suffix = "/trade-api/ws/v2"
        self.message_id = 1  # Counter for message IDs
        self.market_descriptions = {}

    async def connect(self):
        """Establishes a WebSocket connection using authentication."""
        host = self.WS_BASE_URL + self.url_suffix
        auth_headers = self.request_headers("GET", self.url_suffix)
        async with websockets.connect(host, additional_headers=auth_headers) as websocket:
            self.ws = websocket
            await self.on_open()
            await self.handler()

    async def on_open(self):
        """Callback when WebSocket connection is opened."""
        print("WebSocket connection opened.")
        await self.subscribe_to_climate_tickers()

    async def subscribe_to_climate_tickers(self):
        """Subscribe to ticker updates for climate-related markets."""
        subscription_message = {
            "id": self.message_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"],
                "market_ids": list(self.market_descriptions.keys())
            }
        }
        await self.ws.send(json.dumps(subscription_message))
        self.message_id += 1

    async def handler(self):
        """Handle incoming messages."""
        try:
            async for message in self.ws:
                await self.on_message(message)
        except websockets.ConnectionClosed as e:
            await self.on_close(e.code, e.reason)
        except Exception as e:
            await self.on_error(e)

    async def on_message(self, message):
        """Callback for handling incoming messages."""
        parsed_message = json.loads(message)
        market_id = parsed_message.get('msg', {}).get('market_id')
        description = self.market_descriptions.get(market_id, "Unknown market")
        
        # Convert POSIX time to something that's actually readable
        posix_time = parsed_message.get('msg', {}).get('ts')
        if posix_time:
            utc = datetime.fromtimestamp(posix_time, timezone.utc)
            est = utc.astimezone(pytz.timezone('US/Eastern'))
            readable_time = est.strftime('%m-%d-%Y %I:%M:%S %p')
            parsed_message['msg']['ts'] = readable_time
        
        # Formatting
        market_ticker = parsed_message.get('msg', {}).get('market_ticker')
        if market_ticker:
            parts = market_ticker.split('-')
            if len(parts) >= 3:
                formatted_ticker = f"{parts[0]} ({parts[1]}) {parts[2]}"
                if len(parts) > 3:
                    formatted_ticker += f" {parts[3]}"
                parsed_message['msg']['market_ticker'] = formatted_ticker
        
        price = parsed_message.get('msg', {}).get('price')
        if price is not None:
            parsed_message['msg']['price'] = f"${price:.2f}"
        
        volume = parsed_message.get('msg', {}).get('volume')
        if volume is not None:
            parsed_message['msg']['volume'] = f"{volume:,}"
        
        dollar_volume = parsed_message.get('msg', {}).get('dollar_volume')
        if dollar_volume is not None:
            parsed_message['msg']['dollar_volume'] = f"${dollar_volume:,}"
        
        dollar_open_interest = parsed_message.get('msg', {}).get('dollar_open_interest')
        if dollar_open_interest is not None:
            parsed_message['msg']['dollar_open_interest'] = f"${dollar_open_interest:,}"
        
        yes_bid = parsed_message.get('msg', {}).get('yes_bid')
        if yes_bid is not None:
            parsed_message['msg']['yes_bid'] = f"{yes_bid}¢"
        
        yes_ask = parsed_message.get('msg', {}).get('yes_ask')
        if yes_ask is not None:
            parsed_message['msg']['yes_ask'] = f"{yes_ask}¢"
        
        formatted_message = json.dumps(parsed_message, indent=4, ensure_ascii=False)
        print("Received message:\n", formatted_message)
        print(f"Market description: {description}")

    async def on_error(self, error):
        """Callback for handling errors."""
        print("WebSocket error:", error)

    async def on_close(self, close_status_code, close_msg):
        """Callback when WebSocket connection is closed."""
        print("WebSocket connection closed with code:", close_status_code, "and message:", close_msg)