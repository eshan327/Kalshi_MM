"""
WebSocket Orderbook Service

Maintains real-time orderbook state via Kalshi WebSocket connection.
Handles subscription, delta updates, and provides current orderbook snapshots.
"""
import asyncio
import json
import time
import base64
import logging
from typing import Dict, List, Optional, Callable, Any, cast
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Thread, Lock

import websockets
from websockets import ClientConnection
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.backends import default_backend

from config import config as app_config

logger = logging.getLogger(__name__)


@dataclass
class OrderbookLevel:
    """Single price level in the orderbook."""
    price: int  # Cents (1-99)
    quantity: int


@dataclass
class Orderbook:
    """Orderbook state for a single market."""
    ticker: str
    yes_bids: Dict[int, int] = field(default_factory=dict)  # price -> quantity
    no_bids: Dict[int, int] = field(default_factory=dict)   # price -> quantity
    last_update: float = 0.0
    
    @property
    def best_yes_bid(self) -> Optional[int]:
        """Highest price someone will pay for YES."""
        if not self.yes_bids:
            return None
        return max(self.yes_bids.keys())
    
    @property
    def best_yes_ask(self) -> Optional[int]:
        """Lowest price someone will sell YES (derived from best NO bid)."""
        if not self.no_bids:
            return None
        best_no_bid = max(self.no_bids.keys())
        return 100 - best_no_bid
    
    @property
    def spread(self) -> Optional[int]:
        """Current spread in cents."""
        bid = self.best_yes_bid
        ask = self.best_yes_ask
        if bid is None or ask is None:
            return None
        spread = ask - bid
        return spread if spread > 0 else None
    
    @property
    def mid(self) -> Optional[float]:
        """Midpoint price."""
        bid = self.best_yes_bid
        ask = self.best_yes_ask
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2
    
    def get_yes_bids_sorted(self) -> List[OrderbookLevel]:
        """Get YES bids sorted by price (highest first)."""
        return [
            OrderbookLevel(price=p, quantity=q)
            for p, q in sorted(self.yes_bids.items(), reverse=True)
            if q > 0
        ]
    
    def get_no_bids_sorted(self) -> List[OrderbookLevel]:
        """Get NO bids sorted by price (highest first)."""
        return [
            OrderbookLevel(price=p, quantity=q)
            for p, q in sorted(self.no_bids.items(), reverse=True)
            if q > 0
        ]
    
    def apply_snapshot(self, yes_levels: List, no_levels: List):
        """Apply a full orderbook snapshot."""
        self.yes_bids.clear()
        self.no_bids.clear()
        
        for price, qty in yes_levels:
            if qty > 0:
                self.yes_bids[price] = qty
        
        for price, qty in no_levels:
            if qty > 0:
                self.no_bids[price] = qty
        
        self.last_update = time.time()
    
    def apply_delta(self, side: str, price: int, delta: int):
        """
        Apply a delta update to the orderbook.
        
        Args:
            side: 'yes' or 'no'
            price: Price level in cents
            delta: Quantity change (positive = add, negative = remove)
        """
        book = self.yes_bids if side == 'yes' else self.no_bids
        
        current_qty = book.get(price, 0)
        new_qty = current_qty + delta
        
        if new_qty <= 0:
            book.pop(price, None)
        else:
            book[price] = new_qty
        
        self.last_update = time.time()


def sign_ws_request(private_key_pem: str, api_key_id: str) -> Dict[str, str]:
    """
    Generate authentication headers for WebSocket connection.
    
    Args:
        private_key_pem: PEM-encoded RSA private key
        api_key_id: Kalshi API key ID
    
    Returns:
        Dict with authentication headers
    """
    timestamp = str(int(time.time() * 1000))
    method = "GET"
    path = "/trade-api/ws/v2"
    
    # Load private key
    private_key = cast(RSAPrivateKey, serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
        backend=default_backend()
    ))
    
    # Create message to sign
    message = f"{timestamp}{method}{path}".encode('utf-8')
    
    # Sign with RSA-PSS
    pss_padding = padding.PSS(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH
    )
    signature = private_key.sign(
        message,
        pss_padding,
        hashes.SHA256()
    )
    
    # Return headers
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode('utf-8'),
        "KALSHI-ACCESS-TIMESTAMP": timestamp
    }


class OrderbookService:
    """
    Service for managing real-time orderbook data via WebSocket.
    
    Runs in a background thread with its own asyncio event loop.
    Provides thread-safe access to orderbook state.
    """
    
    def __init__(self):
        self._orderbooks: Dict[str, Orderbook] = {}
        self._lock = Lock()
        self._subscribed_tickers: set = set()
        self._ws: Optional[ClientConnection] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._connected = False
        self._private_key: Optional[str] = None
        self._callbacks: List[Callable[[str, Orderbook], None]] = []
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
    
    def initialize(self, private_key_pem: str):
        """Initialize with private key for authentication."""
        self._private_key = private_key_pem
    
    def add_callback(self, callback: Callable[[str, Orderbook], None]):
        """Add a callback to be called on orderbook updates."""
        self._callbacks.append(callback)
    
    def start(self):
        """Start the WebSocket service in a background thread."""
        if self._running:
            logger.warning("OrderbookService already running")
            return
        
        if not self._private_key:
            logger.error("OrderbookService not initialized with private key")
            return
        
        self._running = True
        self._thread = Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        logger.info("OrderbookService started")
    
    def stop(self):
        """Stop the WebSocket service."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("OrderbookService stopped")
    
    def _run_event_loop(self):
        """Run the asyncio event loop in the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._websocket_loop())
        except Exception as e:
            logger.error(f"Event loop error: {e}")
        finally:
            self._loop.close()
    
    async def _websocket_loop(self):
        """Main WebSocket connection loop with auto-reconnect."""
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self._connected = False
            
            if self._running:
                logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, 
                    self._max_reconnect_delay
                )
    
    async def _connect_and_listen(self):
        """Connect to WebSocket and process messages."""
        if self._private_key is None:
            raise RuntimeError("Private key not initialized")
        
        # Generate auth headers
        headers = sign_ws_request(
            self._private_key,
            app_config.kalshi.api_key_id
        )
        
        url = app_config.kalshi.ws_url
        
        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected = True
            self._reconnect_delay = 1.0  # Reset on successful connect
            logger.info("WebSocket connected")
            
            # Resubscribe to any previously subscribed tickers
            if self._subscribed_tickers:
                await self._send_subscription(list(self._subscribed_tickers))
            
            # Process messages
            async for message in ws:
                if not self._running:
                    break
                if isinstance(message, str):
                    await self._handle_message(message)
                else:
                    await self._handle_message(bytes(message).decode('utf-8'))
    
    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'orderbook_snapshot':
                await self._handle_snapshot(data)
            elif msg_type == 'orderbook_delta':
                await self._handle_delta(data)
            elif msg_type == 'subscribed':
                logger.info(f"Subscribed to: {data.get('msg', {}).get('channel')}")
            elif msg_type == 'error':
                logger.error(f"WebSocket error: {data}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
    
    async def _handle_snapshot(self, data: Dict):
        """Handle orderbook snapshot message."""
        msg = data.get('msg', {})
        ticker = msg.get('market_ticker')
        
        if not ticker:
            return
        
        with self._lock:
            if ticker not in self._orderbooks:
                self._orderbooks[ticker] = Orderbook(ticker=ticker)
            
            ob = self._orderbooks[ticker]
            ob.apply_snapshot(
                yes_levels=msg.get('yes', []),
                no_levels=msg.get('no', [])
            )
        
        logger.debug(f"Snapshot received for {ticker}")
        self._notify_callbacks(ticker)
    
    async def _handle_delta(self, data: Dict):
        """Handle orderbook delta message."""
        msg = data.get('msg', {})
        ticker = msg.get('market_ticker')
        
        if not ticker:
            return
        
        with self._lock:
            if ticker not in self._orderbooks:
                self._orderbooks[ticker] = Orderbook(ticker=ticker)
            
            ob = self._orderbooks[ticker]
            
            # Process deltas
            for side in ['yes', 'no']:
                for price, delta in msg.get(side, []):
                    ob.apply_delta(side, price, delta)
        
        self._notify_callbacks(ticker)
    
    async def _send_subscription(self, tickers: List[str]):
        """Send subscription message for market tickers."""
        if not self._ws or not self._connected:
            return
        
        msg = {
            "id": int(time.time() * 1000),
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": tickers
            }
        }
        
        await self._ws.send(json.dumps(msg))
        logger.info(f"Subscription sent for: {tickers}")
    
    def _notify_callbacks(self, ticker: str):
        """Notify all callbacks of an orderbook update."""
        with self._lock:
            ob = self._orderbooks.get(ticker)
            if ob:
                for callback in self._callbacks:
                    try:
                        callback(ticker, ob)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
    
    # =========================================================================
    # Public API (thread-safe)
    # =========================================================================
    
    def subscribe(self, tickers: List[str]):
        """Subscribe to orderbook updates for given tickers."""
        self._subscribed_tickers.update(tickers)
        
        if self._connected and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_subscription(tickers),
                self._loop
            )
    
    def unsubscribe(self, tickers: List[str]):
        """Unsubscribe from orderbook updates."""
        for ticker in tickers:
            self._subscribed_tickers.discard(ticker)
        
        # Note: Kalshi WS doesn't have explicit unsubscribe,
        # would need to reconnect with new subscription list
    
    def get_orderbook(self, ticker: str) -> Optional[Orderbook]:
        """Get current orderbook state for a ticker (thread-safe copy)."""
        with self._lock:
            ob = self._orderbooks.get(ticker)
            if ob:
                # Return a copy to avoid thread issues
                copy = Orderbook(ticker=ob.ticker)
                copy.yes_bids = dict(ob.yes_bids)
                copy.no_bids = dict(ob.no_bids)
                copy.last_update = ob.last_update
                return copy
            return None
    
    def get_all_orderbooks(self) -> Dict[str, Orderbook]:
        """Get all orderbook states (thread-safe copies)."""
        with self._lock:
            result = {}
            for ticker, ob in self._orderbooks.items():
                copy = Orderbook(ticker=ob.ticker)
                copy.yes_bids = dict(ob.yes_bids)
                copy.no_bids = dict(ob.no_bids)
                copy.last_update = ob.last_update
                result[ticker] = copy
            return result
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def subscribed_tickers(self) -> set:
        return self._subscribed_tickers.copy()


# Global service instance
orderbook_service = OrderbookService()
