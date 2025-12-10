"""
WebSocket streamer for Kalshi market data.
Connects to Kalshi's WebSocket API and streams real-time market data for a given market ID.
"""

import sys
import os
import json
import asyncio
import signal
import time
import hashlib
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Setup.apiSetup import KalshiAPI
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.backends import default_backend


class KalshiMarketStreamer:
    """WebSocket client for streaming Kalshi market data."""
    
    # WebSocket endpoints (based on Kalshi docs: https://docs.kalshi.com/websockets/)
    PROD_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    
    def __init__(self, market_ids: Optional[List[str]] = None, market_id: Optional[str] = None, demo: bool = False, channels: Optional[List[str]] = None):
        """
        Initialize the market streamer.
        
        Args:
            market_ids: List of market ticker IDs to subscribe to (e.g., ['MARKET1', 'MARKET2'])
            market_id: Single market ticker ID (for backward compatibility)
            demo: Whether to use demo environment (default: False for production)
            channels: List of channels to subscribe to (default: ["ticker", "orderbook_delta", "trade"])
        """
        # Handle both single market_id (backward compat) and list of market_ids
        if market_ids is None:
            if market_id is None:
                raise ValueError("Either market_ids or market_id must be provided")
            self.market_ids = [market_id]
        else:
            self.market_ids = market_ids if isinstance(market_ids, list) else [market_ids]
        
        # Keep backward compatibility
        self.market_id = self.market_ids[0] if self.market_ids else None
        
        self.demo = demo
        self.ws_url = self.DEMO_WS_URL if demo else self.PROD_WS_URL
        self.default_channels = channels if channels else ["ticker", "orderbook_delta", "trade"]
        self.ws: Optional[Any] = None  # websockets.WebSocketClientProtocol
        self.running = False
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60  # seconds
        
        # Track subscribed markets and subscription IDs (SIDs)
        # Maps: market_id -> {channel -> sid}
        self.subscribed_markets = {}  # {market_id: {channel: sid}}
        self.subscription_id_counter = 1  # Incrementing ID for each subscription command
        self.sid_to_market = {}  # {sid: (market_id, channel)} for reverse lookup
        
        # Setup API client for authentication and trading
        # NOTE: WebSocket is READ-ONLY. Trading must be done via REST API.
        self.api_client = KalshiAPI().get_client(demo=demo)
        
        # Get credentials from API client configuration
        config = self.api_client.api_client.configuration
        self.api_key_id = getattr(config, 'api_key_id', None)
        self.private_key = getattr(config, 'private_key_pem', None)
        
        # Track active orders for trading functionality (via REST API)
        self.active_orders: Dict[str, Dict[str, Any]] = {}  # {order_id: order_info}
        
        # Callbacks for trading integration
        # These are called when WebSocket receives market updates
        # Trading logic executes via REST API (self.api_client)
        self.on_orderbook_update: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]] = None
        self.on_ticker_update: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]] = None
        self.on_trade_update: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]] = None
        self.on_fill_update: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]] = None
        self.on_position_update: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]] = None
    
    def _is_connected(self) -> bool:
        """
        Check if WebSocket is connected and open.
        
        Returns:
            True if connected and open, False otherwise
        """
        if not self.ws:
            return False
        # Check if websocket is closed by checking close_code
        # close_code is None when open, set to a code when closed
        if hasattr(self.ws, 'close_code') and self.ws.close_code is not None:
            return False
        return True
        
    def _generate_signature(self, timestamp: str) -> str:
        """
        Generate RSA-PSS signature for authentication.
        Based on Kalshi SDK authentication pattern (RSA-PSS with SHA256).
        For websocket, we sign: timestamp + endpoint path
        """
        try:
            if self.private_key is None:
                print(f"[{datetime.now().isoformat()}] ⚠ No private key available for signing")
                return ""
            
            # Load private key
            loaded_key = serialization.load_pem_private_key(
                self.private_key.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            
            # Cast to RSAPrivateKey - Kalshi uses RSA keys
            if not isinstance(loaded_key, RSAPrivateKey):
                raise TypeError("Private key must be an RSA key")
            private_key_obj: RSAPrivateKey = loaded_key
            
            # Create message to sign: timestamp + endpoint path
            # For websocket connection, use the endpoint path
            endpoint_path = "/trade-api/ws/v2"
            message = timestamp + "GET" + endpoint_path  # GET method for websocket handshake
            
            # Sign the message using RSA-PSS (as per Kalshi SDK)
            signature = private_key_obj.sign(
                message.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Encode signature as base64
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Signature generation error: {e}")
            return ""
    
    async def connect(self) -> bool:
        """
        Connect to the WebSocket server with authentication headers.
        Based on Kalshi documentation: https://docs.kalshi.com/websockets/
        """
        try:
            print(f"[{datetime.now().isoformat()}] Connecting to {self.ws_url}...")
            
            # Prepare authentication headers if credentials are available
            additional_headers = None
            if self.api_key_id and self.private_key:
                # Generate timestamp (in seconds as string, not milliseconds)
                timestamp = str(int(time.time()))
                signature = self._generate_signature(timestamp)
                
                # Add authentication headers using Kalshi SDK format
                additional_headers = [
                    ("KALSHI-ACCESS-KEY", self.api_key_id),
                    ("KALSHI-ACCESS-TIMESTAMP", timestamp),
                    ("KALSHI-ACCESS-SIGNATURE", signature),
                ]
                print(f"[{datetime.now().isoformat()}] Adding authentication headers...")
            
            # Create WebSocket connection with authentication headers
            self.ws = await websockets.connect(
                self.ws_url,
                additional_headers=additional_headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            print(f"[{datetime.now().isoformat()}] ✓ Connected to WebSocket")
            
            # Re-subscribe to all markets (both initial and dynamically added)
            # If this is a reconnect, subscribed_markets will have market info
            # If this is initial connection, subscribed_markets will be empty, so use market_ids
            if self.subscribed_markets:
                # Re-subscribe to all previously subscribed markets and channels
                markets_to_resubscribe = {}
                for market_id, channels in self.subscribed_markets.items():
                    markets_to_resubscribe[market_id] = list(channels.keys())
                # Clear SID tracking but keep market info for resubscription
                self.sid_to_market.clear()
            else:
                # Initial connection - subscribe to default channels
                markets_to_resubscribe = {market_id: self.default_channels for market_id in self.market_ids}
            
            # Subscribe to all markets
            print(f"[{datetime.now().isoformat()}] Re-subscribing to {len(markets_to_resubscribe)} markets...")
            for market_id, channels in markets_to_resubscribe.items():
                await self.subscribe_to_market(market_id, channels)
                await asyncio.sleep(0.1)  # Small delay between subscriptions
            
            return True
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Connection failed: {e}")
            return False
    
    async def authenticate(self):
        """
        Authenticate with the WebSocket server (if needed).
        Note: Authentication is typically done via headers during connection,
        but some websocket implementations require an auth message after connection.
        """
        # Authentication is done via headers during connection handshake
        # If additional auth message is needed, it would go here
        # For now, we skip this since header-based auth seems to be working
        pass
    
    async def subscribe_to_market(self, market_id: Optional[str] = None, channels: Optional[List[str]] = None):
        """
        Subscribe to market data for a specific market ID.
        Can be called after connection to add more markets dynamically.
        Based on Kalshi docs: https://docs.kalshi.com/websockets/
        
        Args:
            market_id: Market ticker ID to subscribe to (defaults to first market if not provided)
            channels: List of channels to subscribe to (default: ["ticker", "orderbook_delta", "trade"])
                     Valid channels: "orderbook_delta", "ticker", "trade", "fill", "position", etc.
        Returns:
            Subscription ID (command ID), or None if failed
        """
        if market_id is None:
            market_id = self.market_id
        
        if channels is None:
            channels = ["ticker", "orderbook_delta", "trade"]
        
        if not self._is_connected():
            print(f"[{datetime.now().isoformat()}] ⚠ Cannot subscribe: WebSocket not connected")
            return None
        
        try:
            # Check if already subscribed to all requested channels
            if market_id in self.subscribed_markets:
                existing_channels = set(self.subscribed_markets[market_id].keys())
                requested_channels = set(channels)
                if requested_channels.issubset(existing_channels):
                    print(f"[{datetime.now().isoformat()}] ℹ Already subscribed to {market_id} for channels: {existing_channels}")
                    return None
            
            # Per Kalshi docs: {"id": 1, "cmd": "subscribe", "params": {"channels": [...], "market_ticker": "..."}}
            subscription_id = self.subscription_id_counter
            self.subscription_id_counter += 1
            
            subscription_message = {
                "id": subscription_id,
                "cmd": "subscribe",
                "params": {
                    "channels": channels,
                    "market_ticker": market_id
                }
            }
            
            # Send subscription message
            if self.ws is None:
                print(f"[{datetime.now().isoformat()}] ⚠ WebSocket not connected")
                return None
            await self.ws.send(json.dumps(subscription_message))
            print(f"[{datetime.now().isoformat()}] ✓ Sent subscribe command (id={subscription_id}) for {market_id}, channels: {channels}")
            
            # Initialize market tracking (SID will be set when we get "subscribed" response)
            if market_id not in self.subscribed_markets:
                self.subscribed_markets[market_id] = {}
            
            return subscription_id
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Subscription error for {market_id}: {e}")
            return None
    
    async def unsubscribe(self, sids: list):
        """
        Unsubscribe from one or more subscriptions using their SIDs.
        Based on Kalshi docs: https://docs.kalshi.com/websockets/
        
        Args:
            sids: List of subscription IDs (SIDs) to unsubscribe from
        """
        if not self._is_connected():
            print(f"[{datetime.now().isoformat()}] ⚠ Cannot unsubscribe: WebSocket not connected")
            return
        
        try:
            unsubscribe_id = self.subscription_id_counter
            self.subscription_id_counter += 1
            
            unsubscribe_message = {
                "id": unsubscribe_id,
                "cmd": "unsubscribe",
                "params": {
                    "sids": sids
                }
            }
            
            if self.ws is None:
                return
            await self.ws.send(json.dumps(unsubscribe_message))
            print(f"[{datetime.now().isoformat()}] ✓ Sent unsubscribe command (id={unsubscribe_id}) for SIDs: {sids}")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Unsubscribe error: {e}")
    
    async def update_subscription(self, sids: list, market_tickers: list, action: str):
        """
        Update an existing subscription by adding or removing markets.
        Based on Kalshi docs: https://docs.kalshi.com/websockets/
        
        Args:
            sids: List of subscription IDs to update
            market_tickers: List of market ticker IDs to add/remove
            action: "add_markets" or "delete_markets"
        """
        if not self._is_connected():
            print(f"[{datetime.now().isoformat()}] ⚠ Cannot update subscription: WebSocket not connected")
            return
        
        if action not in ["add_markets", "delete_markets"]:
            raise ValueError(f"Action must be 'add_markets' or 'delete_markets', got '{action}'")
        
        try:
            update_id = self.subscription_id_counter
            self.subscription_id_counter += 1
            
            update_message = {
                "id": update_id,
                "cmd": "update_subscription",
                "params": {
                    "sids": sids,
                    "market_tickers": market_tickers,
                    "action": action
                }
            }
            
            if self.ws is None:
                return
            await self.ws.send(json.dumps(update_message))
            print(f"[{datetime.now().isoformat()}] ✓ Sent update_subscription command (id={update_id}): {action} for {market_tickers}")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Update subscription error: {e}")
    
    async def list_subscriptions(self):
        """
        List all active subscriptions.
        Based on Kalshi docs: https://docs.kalshi.com/websockets/
        """
        if not self._is_connected():
            print(f"[{datetime.now().isoformat()}] ⚠ Cannot list subscriptions: WebSocket not connected")
            return
        
        try:
            list_id = self.subscription_id_counter
            self.subscription_id_counter += 1
            
            list_message = {
                "id": list_id,
                "cmd": "list_subscriptions"
            }
            
            if self.ws is None:
                return
            await self.ws.send(json.dumps(list_message))
            print(f"[{datetime.now().isoformat()}] ✓ Sent list_subscriptions command (id={list_id})")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ List subscriptions error: {e}")
    
    async def subscribe_to_multiple_markets(self, market_ids: List[str], channels: Optional[List[str]] = None):
        """
        Subscribe to multiple markets at once.
        
        Args:
            market_ids: List of market ticker IDs
            channels: List of channels to subscribe to (default: ["ticker", "orderbook_delta", "trade"])
        """
        for market_id in market_ids:
            await self.subscribe_to_market(market_id, channels)
            # Small delay between subscriptions to avoid rate limiting
            await asyncio.sleep(0.1)
    
    async def handle_message(self, message: str):
        """
        Handle incoming WebSocket messages.
        Based on Kalshi docs: https://docs.kalshi.com/websockets/
        """
        try:
            data = json.loads(message)
            timestamp = datetime.now().isoformat()
            
            # Print formatted message
            print(f"\n[{timestamp}] === Received Message ===")
            print(json.dumps(data, indent=2))
            print(f"[{timestamp}] === End Message ===\n")
            
            # Handle different message types per Kalshi docs
            msg_type = data.get("type", "unknown")
            
            if msg_type == "subscribed":
                # Handle subscription confirmation
                # Format: {"id": 1, "type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 1}}
                await self.handle_subscribed_response(data)
            elif msg_type == "unsubscribed":
                # Handle unsubscription confirmation
                # Format: {"sid": 2, "type": "unsubscribed"}
                await self.handle_unsubscribed_response(data)
            elif msg_type == "ok":
                # Handle OK responses (update_subscription, list_subscriptions)
                await self.handle_ok_response(data)
            elif msg_type == "error":
                # Handle error responses
                # Format: {"id": 123, "type": "error", "msg": {"code": 6, "msg": "Already subscribed"}}
                await self.handle_error_response(data)
            elif msg_type == "orderbook_delta" or msg_type == "orderbook":
                # Orderbook update messages
                await self.handle_orderbook(data)
            elif msg_type == "ticker":
                # Ticker update messages
                await self.handle_ticker(data)
            elif msg_type == "trade" or msg_type == "trades":
                # Trade execution messages
                await self.handle_trade(data)
            elif msg_type == "fill":
                # User fill messages (requires authentication)
                await self.handle_fill(data)
            elif msg_type == "position":
                # Position update messages (requires authentication)
                await self.handle_position(data)
            elif msg_type == "heartbeat" or msg_type == "ping":
                # Respond to heartbeat - some servers may not require a response
                # Only respond if the message explicitly asks for it
                try:
                    # Some websocket implementations expect pong, others don't need a response
                    # Kalshi may not require a pong response, so we'll skip it to avoid "Unknown command" errors
                    pass
                except:
                    pass
            else:
                # Generic message handler
                print(f"[{timestamp}] Received {msg_type} message (unhandled)")
                
        except json.JSONDecodeError:
            print(f"[{datetime.now().isoformat()}] Received non-JSON message: {message}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling message: {e}")
    
    async def handle_subscribed_response(self, data: Dict[str, Any]):
        """Handle 'subscribed' response and track SID."""
        try:
            msg = data.get("msg", {})
            channel = msg.get("channel")
            sid = msg.get("sid")
            cmd_id = data.get("id")
            
            if sid and channel:
                # Find which market this subscription is for
                # We need to track this when we send the subscribe command
                # For now, we'll store it and try to match by command ID
                print(f"[{datetime.now().isoformat()}] ✓ Subscribed to {channel} channel (SID: {sid}, command ID: {cmd_id})")
                # Note: Full market tracking would require storing cmd_id -> market_id mapping
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling subscribed response: {e}")
    
    async def handle_unsubscribed_response(self, data: Dict[str, Any]):
        """Handle 'unsubscribed' response."""
        try:
            sid = data.get("sid")
            print(f"[{datetime.now().isoformat()}] ✓ Unsubscribed from SID: {sid}")
            # Remove from tracking
            if sid in self.sid_to_market:
                market_id, channel = self.sid_to_market.pop(sid)
                if market_id in self.subscribed_markets and channel in self.subscribed_markets[market_id]:
                    del self.subscribed_markets[market_id][channel]
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling unsubscribed response: {e}")
    
    async def handle_ok_response(self, data: Dict[str, Any]):
        """Handle 'ok' response (update_subscription, list_subscriptions)."""
        try:
            cmd_id = data.get("id")
            if "subscriptions" in data:
                # List subscriptions response
                subscriptions = data.get("subscriptions", [])
                print(f"[{datetime.now().isoformat()}] ✓ Active subscriptions: {len(subscriptions)}")
                for sub in subscriptions:
                    print(f"  - Channel: {sub.get('channel')}, SID: {sub.get('sid')}")
            elif "market_tickers" in data:
                # Update subscription response
                market_tickers = data.get("market_tickers", [])
                print(f"[{datetime.now().isoformat()}] ✓ Update subscription successful for markets: {market_tickers}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling ok response: {e}")
    
    async def handle_error_response(self, data: Dict[str, Any]):
        """Handle error responses."""
        try:
            msg = data.get("msg", {})
            code = msg.get("code", "unknown")
            error_msg = msg.get("msg", "Unknown error")
            print(f"[{datetime.now().isoformat()}] ⚠ Error from server (code {code}): {error_msg}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling error response: {e}")
    
    async def handle_orderbook(self, data: Dict[str, Any]):
        """
        Handle orderbook update messages.
        Can trigger trading callbacks that use REST API to place orders.
        """
        try:
            market_id = data.get("market_ticker") or data.get("market_id")
            print(f"[{datetime.now().isoformat()}] 📊 Orderbook update received for {market_id}")
            
            # Call callback if set (for trading integration)
            if self.on_orderbook_update:
                try:
                    await self.on_orderbook_update(data, market_id)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ Error in orderbook callback: {e}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling orderbook: {e}")
    
    async def handle_ticker(self, data: Dict[str, Any]):
        """
        Handle ticker update messages.
        Can trigger trading callbacks that use REST API to place orders.
        """
        try:
            market_id = data.get("market_ticker") or data.get("market_id")
            print(f"[{datetime.now().isoformat()}] 📈 Ticker update received for {market_id}")
            
            # Call callback if set (for trading integration)
            if self.on_ticker_update:
                try:
                    await self.on_ticker_update(data, market_id)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ Error in ticker callback: {e}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling ticker: {e}")
    
    async def handle_trade(self, data: Dict[str, Any]):
        """
        Handle trade execution messages (public trades).
        Can trigger trading callbacks that use REST API to place orders.
        """
        try:
            market_id = data.get("market_ticker") or data.get("market_id")
            print(f"[{datetime.now().isoformat()}] 💰 Trade update received for {market_id}")
            
            # Note: This is for public trades, not user fills
            # User fills come through "fill" channel
            if self.on_trade_update:
                try:
                    await self.on_trade_update(data, market_id)
                except Exception as cb_e:
                    print(f"[{datetime.now().isoformat()}] Error in trade callback: {cb_e}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling trade: {e}")
    
    async def handle_fill(self, data: Dict[str, Any]):
        """
        Handle user fill messages (requires authentication).
        Can trigger trading callbacks that use REST API to place orders.
        """
        try:
            market_id = data.get("market_ticker") or data.get("market_id")
            print(f"[{datetime.now().isoformat()}] ✅ Fill update received for {market_id}")
            
            # Call callback if set (for trading integration)
            if self.on_fill_update:
                try:
                    await self.on_fill_update(data, market_id)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ Error in fill callback: {e}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling fill: {e}")
    
    async def handle_position(self, data: Dict[str, Any]):
        """
        Handle position update messages (requires authentication).
        Can trigger trading callbacks that use REST API to place orders.
        """
        try:
            market_id = data.get("market_ticker") or data.get("market_id")
            print(f"[{datetime.now().isoformat()}] 📊 Position update received for {market_id}")
            
            # Call callback if set (for trading integration)
            if self.on_position_update:
                try:
                    await self.on_position_update(data, market_id)
                except Exception as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ Error in position callback: {e}")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error handling position: {e}")
    
    # ==================== TRADING METHODS ====================
    # IMPORTANT: These methods use REST API (self.api_client), NOT WebSocket!
    # WebSocket is READ-ONLY for receiving market data.
    # Trading (order placement, cancellation) must be done via REST API.
    # Architecture: WebSocket receives updates → Callbacks trigger → REST API executes trades
    # Based on Kalshi docs: https://docs.kalshi.com/websockets/
    
    def get_best_bid(self, market_id: str) -> Optional[float]:
        """
        Get the best bid price for a market.
        
        Args:
            market_id: Market ticker ID
            
        Returns:
            Best bid price as float (0-1 range), or None if error
        """
        try:
            return self.api_client.getMarket(market_id).yes_bid
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error getting best bid for {market_id}: {e}")
            return None
    
    def get_best_ask(self, market_id: str) -> Optional[float]:
        """
        Get the best ask price for a market.
        
        Args:
            market_id: Market ticker ID
            
        Returns:
            Best ask price as float (0-1 range), or None if error
        """
        try:
            return self.api_client.getMarket(market_id).yes_ask
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error getting best ask for {market_id}: {e}")
            return None
    
    def get_market_spread(self, market_id: str) -> Optional[float]:
        """
        Calculate the spread (ask - bid) for a market.
        
        Args:
            market_id: Market ticker ID
            
        Returns:
            Spread as float, or None if unable to calculate
        """
        try:
            bid = self.get_best_bid(market_id)
            ask = self.get_best_ask(market_id)
            if bid is not None and ask is not None:
                return ask - bid
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error calculating spread for {market_id}: {e}")
            return None
    
    def create_order(self, market_id: str, side: str, count: int, price: float) -> Optional[Any]:
        """
        Create a limit order.
        
        Args:
            market_id: Market ticker ID
            side: "buy" or "sell"
            count: Number of contracts (must be >= 1)
            price: Limit price (0-1 range)
            
        Returns:
            Order object if successful, None otherwise
        """
        try:
            if side.lower() not in ["buy", "sell"]:
                raise ValueError(f"Side must be 'buy' or 'sell', got '{side}'")
            
            if count < 1:
                raise ValueError(f"Count must be >= 1, got {count}")
            
            if not (0 <= price <= 1):
                raise ValueError(f"Price must be between 0 and 1, got {price}")
            
            order = self.api_client.create_order(market_id, side.lower(), count, price)
            
            if order and hasattr(order, 'order_id'):
                # Track active order
                self.active_orders[order.order_id] = {
                    'market_id': market_id,
                    'side': side.lower(),
                    'count': count,
                    'price': price,
                    'created_at': datetime.now(),
                    'order': order
                }
                print(f"[{datetime.now().isoformat()}] ✓ Created {side} order: {count} contracts @ ${price:.2f} for {market_id}")
            else:
                print(f"[{datetime.now().isoformat()}] ⚠ Order created but no order_id returned")
            
            return order
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Error creating {side} order for {market_id}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an active order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.api_client.cancel_order(order_id)
            
            # Remove from active orders tracking
            if order_id in self.active_orders:
                order_info = self.active_orders.pop(order_id)
                print(f"[{datetime.now().isoformat()}] ✓ Cancelled order {order_id} ({order_info['side']} {order_info['count']} @ ${order_info['price']:.2f})")
            else:
                print(f"[{datetime.now().isoformat()}] ✓ Cancelled order {order_id}")
            
            return True
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self, market_id: Optional[str] = None) -> int:
        """
        Cancel all active orders, optionally filtered by market.
        
        Args:
            market_id: If provided, only cancel orders for this market
            
        Returns:
            Number of orders cancelled
        """
        cancelled_count = 0
        orders_to_cancel = list(self.active_orders.keys())
        
        for order_id in orders_to_cancel:
            order_info = self.active_orders.get(order_id)
            if order_info:
                if market_id is None or order_info['market_id'] == market_id:
                    if self.cancel_order(order_id):
                        cancelled_count += 1
        
        return cancelled_count
    
    def get_balance(self) -> Optional[float]:
        """
        Get account balance.
        
        Returns:
            Balance as float (in cents), or None if error
        """
        try:
            balance = self.api_client.get_balance()
            if balance and hasattr(balance, 'balance'):
                return balance.balance
            return None
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error getting balance: {e}")
            return None
    
    def get_positions(self) -> Optional[Any]:
        """
        Get all current positions (via REST API).
        
        Returns:
            GetPositionsResponse object with:
            - positions: List[Position] - List of position objects
            - cursor: Optional[str] - Pagination cursor for next page
            
            Each Position object contains:
            - ticker: str - Market ticker identifier
            - event_ticker: Optional[str] - Event ticker this market belongs to
            - market_result: Optional[str] - Market resolution result (if resolved)
            - position: int - Current net position (positive = long, negative = short)
            - realized_pnl: int - Realized profit/loss in cents
            - resting_order_count: int - Number of resting (unfilled) orders
            - fees_paid: int - Total fees paid in cents
            - total_cost: int - Total cost of position in cents
            
            Returns None if error.
        """
        try:
            positions = self.api_client.get_positions()
            return positions
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error getting positions: {e}")
            return None
    
    def get_positions_list(self) -> list:
        """
        Get all current positions as a list (via REST API).
        
        Returns:
            List of Position objects, or empty list if error.
            
            Each Position object has:
            - ticker: Market identifier
            - position: Net position (positive = long, negative = short)
            - realized_pnl: Realized P&L in cents
            - resting_order_count: Number of unfilled orders
            - fees_paid: Total fees in cents
            - total_cost: Total cost in cents
            - event_ticker: Event identifier (if applicable)
            - market_result: Resolution result (if market is resolved)
        """
        try:
            positions_response = self.api_client.get_positions()
            if positions_response and hasattr(positions_response, 'positions'):
                return positions_response.positions
            elif isinstance(positions_response, list):
                return positions_response
            return []
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠ Error getting positions list: {e}")
            return []
    
    def place_market_making_orders(self, market_id: str, count: int = 1, 
                                   bid_offset: float = 0.01, ask_offset: float = 0.01) -> Dict[str, Any]:
        """
        Place market making orders (buy below best bid, sell above best ask).
        
        Args:
            market_id: Market ticker ID
            count: Number of contracts per side
            bid_offset: Amount to subtract from best bid for buy order (default: 0.01)
            ask_offset: Amount to add to best ask for sell order (default: 0.01)
            
        Returns:
            Dictionary with 'buy_order' and 'sell_order' keys, or None values if failed
        """
        try:
            best_bid = self.get_best_bid(market_id)
            best_ask = self.get_best_ask(market_id)
            
            if best_bid is None or best_ask is None:
                print(f"[{datetime.now().isoformat()}] ⚠ Cannot get bid/ask prices for {market_id}")
                return {'buy_order': None, 'sell_order': None}
            
            # Calculate prices
            buy_price = max(0.01, best_bid - bid_offset)  # Ensure price is at least 0.01
            sell_price = min(0.99, best_ask + ask_offset)  # Ensure price is at most 0.99
            
            # Place orders
            buy_order = self.create_order(market_id, "buy", count, buy_price)
            sell_order = self.create_order(market_id, "sell", count, sell_price)
            
            return {
                'buy_order': buy_order,
                'sell_order': sell_order,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spread': best_ask - best_bid
            }
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Error placing market making orders for {market_id}: {e}")
            return {'buy_order': None, 'sell_order': None}
    
    def get_active_orders(self, market_id: Optional[str] = None) -> Dict[str, Dict]:
        """
        Get all active orders, optionally filtered by market.
        
        Args:
            market_id: If provided, only return orders for this market
            
        Returns:
            Dictionary of {order_id: order_info}
        """
        if market_id is None:
            return self.active_orders.copy()
        
        return {
            order_id: order_info 
            for order_id, order_info in self.active_orders.items()
            if order_info.get('market_id') == market_id
        }
    
    async def listen(self):
        """Listen for incoming messages."""
        markets_str = ", ".join(self.market_ids) if len(self.market_ids) > 0 else "markets"
        print(f"[{datetime.now().isoformat()}] 👂 Listening for market data on: {markets_str}")
        print(f"[{datetime.now().isoformat()}] Subscribed markets: {len(self.subscribed_markets)}")
        print(f"[{datetime.now().isoformat()}] ⚠ NOTE: WebSocket is READ-ONLY. Trading uses REST API (self.api_client).")
        print(f"[{datetime.now().isoformat()}] Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                if self.ws is None:
                    print(f"[{datetime.now().isoformat()}] ⚠ WebSocket not connected, stopping listen")
                    break
                try:
                    # Use a shorter timeout so we can check self.running more frequently
                    message = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    # Check if we should still be running
                    if not self.running:
                        break
                    # Send heartbeat to keep connection alive
                    try:
                        if self.ws and not (hasattr(self.ws, 'close_code') and self.ws.close_code is not None):
                            await self.ws.send(json.dumps({"type": "ping"}))
                    except:
                        pass
                except ConnectionClosed as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ Connection closed: {e}")
                    # Break to trigger reconnection in run() method
                    break
                except WebSocketException as e:
                    print(f"[{datetime.now().isoformat()}] ⚠ WebSocket error: {e}")
                    break
                    
        except KeyboardInterrupt:
            print(f"\n[{datetime.now().isoformat()}] Received KeyboardInterrupt in listen()")
            self.shutdown()
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Listen error: {e}")
            if self.running:
                raise
    
    async def reconnect(self):
        """
        Reconnect to the WebSocket with exponential backoff.
        Uses websockets package (as recommended by Kalshi docs) with custom reconnection logic
        since websockets doesn't have built-in reconnection.
        """
        delay = self.reconnect_delay
        while self.running:
            print(f"[{datetime.now().isoformat()}] Attempting to reconnect in {delay} seconds...")
            await asyncio.sleep(delay)
            
            try:
                # Close existing connection if it exists
                if self.ws:
                    try:
                        await self.ws.close()
                    except:
                        pass
                    self.ws = None
                
                if await self.connect():
                    delay = self.reconnect_delay  # Reset delay on successful connection
                    await self.listen()
                else:
                    delay = min(delay * 2, self.max_reconnect_delay)
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] Reconnection attempt failed: {e}")
                delay = min(delay * 2, self.max_reconnect_delay)
    
    async def run(self):
        """Main run loop with reconnection logic."""
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        # Note: add_signal_handler may not work on all platforms, so we also handle KeyboardInterrupt
        try:
            loop = asyncio.get_event_loop()
            if hasattr(loop, 'add_signal_handler'):
                def signal_handler(sig):
                    print(f"\n[{datetime.now().isoformat()}] Received signal {sig}, shutting down...")
                    self.shutdown()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    try:
                        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
                    except (NotImplementedError, RuntimeError):
                        # Signal handlers not supported on this platform
                        pass
        except Exception as e:
            # Signal handler setup failed, but we can still handle KeyboardInterrupt
            pass
        
        try:
            if await self.connect():
                await self.listen()
            else:
                # Initial connection failed, start reconnection loop
                await self.reconnect()
                
        except KeyboardInterrupt:
            print(f"\n[{datetime.now().isoformat()}] Received interrupt signal (Ctrl+C)")
            self.shutdown()
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ✗ Runtime error: {e}")
            if self.running:
                await self.reconnect()
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Stop the streamer."""
        self.running = False
    
    async def close(self):
        """Close the WebSocket connection."""
        if self.ws:
            try:
                await self.ws.close()
                print(f"[{datetime.now().isoformat()}] ✓ WebSocket connection closed")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] Error closing connection: {e}")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Kalshi Market WebSocket Streamer - Stream real-time market data"
    )
    parser.add_argument(
        "--market-id",
        type=str,
        help="Single market ticker ID to stream (e.g., KXMLBGAME-25OCT31LADTOR-LAD)"
    )
    parser.add_argument(
        "--market-ids",
        type=str,
        nargs="+",
        help="Multiple market ticker IDs to stream (e.g., --market-ids MARKET1 MARKET2 MARKET3)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo environment instead of production"
    )
    parser.add_argument(
        "--channels",
        type=str,
        nargs="+",
        help="Channels to subscribe to (default: ticker orderbook_delta trade). "
             "Valid: ticker, orderbook_delta, trade, fill, position"
    )
    
    args = parser.parse_args()
    
    # Determine which markets to use
    if args.market_ids:
        market_ids = args.market_ids
    elif args.market_id:
        market_ids = [args.market_id]
    else:
        parser.error("Either --market-id or --market-ids must be provided")
    
    # Validate channels if provided
    if args.channels:
        valid_channels = ["ticker", "orderbook_delta", "trade", "fill", "position"]
        invalid_channels = [ch for ch in args.channels if ch not in valid_channels]
        if invalid_channels:
            parser.error(f"Invalid channels: {invalid_channels}. Valid channels are: {valid_channels}")
    
    streamer = KalshiMarketStreamer(market_ids=market_ids, demo=args.demo, channels=args.channels)
    
    try:
        await streamer.run()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().isoformat()}] Shutting down...")
    finally:
        await streamer.close()


if __name__ == "__main__":
    asyncio.run(main())

