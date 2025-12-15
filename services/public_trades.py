import asyncio
import json
import logging
import time
from dataclasses import dataclass
from threading import Lock, Thread
from typing import Callable, List, Optional

import websockets
from websockets import ClientConnection

from config import config as app_config
from services.orderbook import sign_ws_request

logger = logging.getLogger(__name__)


@dataclass
class TradePrint:
    market_ticker: str
    yes_price: int
    no_price: int
    count: int
    taker_side: str
    ts: float


class PublicTradesService:
    def __init__(self):
        self._lock = Lock()
        self._ws: Optional[ClientConnection] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._connected = False
        self._private_key: Optional[str] = None
        self._subscribed_tickers: set = set()
        self._callbacks: List[Callable[[TradePrint], None]] = []
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def initialize(self, private_key_pem: str):
        self._private_key = private_key_pem

    def add_callback(self, callback: Callable[[TradePrint], None]):
        self._callbacks.append(callback)

    def start(self):
        if self._running:
            logger.warning("PublicTradesService already running")
            return
        if not self._private_key:
            logger.error("PublicTradesService not initialized with private key")
            return
        self._running = True
        self._thread = Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        logger.info("PublicTradesService started")

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("PublicTradesService stopped")

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._websocket_loop())
        except Exception as e:
            logger.error(f"Public trades event loop error: {e}")
        finally:
            self._loop.close()

    async def _websocket_loop(self):
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"Public trades WebSocket error: {e}")
                self._connected = False

            if self._running:
                logger.info(f"Public trades reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _connect_and_listen(self):
        if self._private_key is None:
            raise RuntimeError("Private key not initialized")

        headers = sign_ws_request(self._private_key, app_config.kalshi.api_key_id)
        url = app_config.kalshi.ws_url

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected = True
            self._reconnect_delay = 1.0
            logger.info("Public trades WebSocket connected")

            if self._subscribed_tickers:
                await self._send_subscription(list(self._subscribed_tickers))

            async for message in ws:
                if not self._running:
                    break
                if isinstance(message, str):
                    await self._handle_message(message)
                else:
                    await self._handle_message(bytes(message).decode('utf-8'))

    async def _handle_message(self, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')
        if msg_type == 'trade':
            msg = data.get('msg', {})
            ticker = msg.get('market_ticker')
            yes_price = msg.get('yes_price')
            no_price = msg.get('no_price')
            count = msg.get('count')
            taker_side = msg.get('taker_side')
            ts = msg.get('ts')
            if not all([ticker, yes_price is not None, no_price is not None, count is not None, taker_side, ts is not None]):
                return

            tp = TradePrint(
                market_ticker=str(ticker),
                yes_price=int(yes_price),
                no_price=int(no_price),
                count=int(count),
                taker_side=str(taker_side),
                ts=float(ts),
            )
            for cb in list(self._callbacks):
                try:
                    cb(tp)
                except Exception as e:
                    logger.error(f"Public trades callback error: {e}")
        elif msg_type == 'subscribed':
            logger.info(f"Subscribed to: {data.get('msg', {}).get('channel')}")
        elif msg_type == 'error':
            logger.error(f"Public trades WebSocket error: {data}")

    async def _send_subscription(self, tickers: List[str]):
        if not self._ws or not self._connected:
            return

        msg = {
            "id": int(time.time() * 1000),
            "cmd": "subscribe",
            "params": {
                "channels": ["trades"],
                "market_tickers": tickers,
            },
        }
        await self._ws.send(json.dumps(msg))
        logger.info(f"Public trades subscription sent for: {tickers}")

    def subscribe(self, tickers: List[str]):
        with self._lock:
            self._subscribed_tickers.update(tickers)

        if self._connected and self._loop:
            asyncio.run_coroutine_threadsafe(self._send_subscription(tickers), self._loop)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def subscribed_tickers(self) -> set:
        with self._lock:
            return self._subscribed_tickers.copy()


public_trades_service = PublicTradesService()
