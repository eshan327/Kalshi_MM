"""Kalshi WebSocket Handler - wraps KalshiMarketStreamer for Flask app with caching."""

import asyncio
import json
import time
import os
import requests
from datetime import datetime
from typing import Dict, Set, List, Optional, Callable, Any
from collections import deque
import sys

project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
from Websocket.market_streamer import KalshiMarketStreamer
from Setup.apiSetup import KalshiAPI


class MarketData:
    """Container for market data."""
    def __init__(self, market_id: str):
        self.market_id = market_id
        self.orderbook: Dict[str, List] = {'yes_bids': [], 'yes_asks': []}
        self.ticker: Dict = {}
        self.recent_trades = deque(maxlen=50)
        self.yes_price: Optional[float] = None
        self.no_price: Optional[float] = None
        self.last_update = int(time.time() * 1000)
        self.subscribed = False


class KalshiWebSocketHandler:
    """Handler for Kalshi WebSocket with caching and data management."""
    
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.streamer: Optional[KalshiMarketStreamer] = None
        self.connection_status = 'disconnected'
        self.subscribed_markets: Set[str] = set()
        self.market_data: Dict[str, MarketData] = {}
        self.message_callbacks: List[Callable] = []
        self.logs: List[Dict] = []
        self.api_client = KalshiAPI().get_client(demo=demo)
        
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_interval = 600
        self.last_cache_time = {}
        self.price_data: Dict[str, List[Dict]] = {}
        self.price_data_file = os.path.join(self.data_dir, 'price_data.json')
        self.subscriptions_file = os.path.join(self.data_dir, 'subscriptions.json')
        
        self._load_price_data()
        self._load_subscriptions()
    
    def add_log(self, level: str, message: str, details: Optional[Dict] = None):
        """Add log entry and notify callbacks."""
        log_entry = {'id': f"{int(time.time()*1000)}{hash(message)%10000}", 'timestamp': int(time.time()*1000),
                    'level': level, 'message': message, 'details': details}
        self.logs = self.logs[-99:] + [log_entry]
        emoji = {'error': '🚨', 'warning': '⚠️', 'success': '✅', 'info': 'ℹ️'}.get(level, '📝')
        print(f"{emoji} {message}")
        for cb in self.message_callbacks:
            cb('log', log_entry)
    
    def add_message_callback(self, callback: Callable):
        self.message_callbacks.append(callback)
    
    async def connect(self):
        """Connect to Kalshi WebSocket."""
        if self.streamer and self.streamer._is_connected():
            self.add_log('info', 'Already connected'); return
        
        self.connection_status = 'connecting'
        self.add_log('info', f'Connecting to Kalshi WebSocket (demo={self.demo})')
        
        try:
            self.streamer = KalshiMarketStreamer(market_ids=[], demo=self.demo, channels=["ticker", "orderbook_delta", "trade"])
            self.streamer.on_orderbook_update = lambda d, m: asyncio.ensure_future(self._handle_orderbook_update(d, m))
            self.streamer.on_ticker_update = lambda d, m: asyncio.ensure_future(self._handle_ticker_update(d, m))
            self.streamer.on_trade_update = lambda d, m: asyncio.ensure_future(self._handle_trade_update(d, m))
            
            original_handle = self.streamer.handle_message
            async def wrapped_handle(message: str) -> None:
                self._emit_raw_message(message)
                await original_handle(message)
            self.streamer.handle_message = wrapped_handle
            
            if await self.streamer.connect():
                self.connection_status = 'connected'
                self.add_log('success', 'Connected to Kalshi WebSocket')
                asyncio.create_task(self.streamer.listen())
            else:
                self.connection_status = 'error'
                self.add_log('error', 'Failed to connect')
        except Exception as e:
            self.add_log('error', f'Connection error: {e}')
            self.connection_status = 'error'
    
    def _emit_raw_message(self, message: str):
        try:
            formatted = json.dumps(json.loads(message), indent=2)
        except:
            formatted = message
        for cb in self.message_callbacks:
            cb('raw_message', {'message': formatted, 'timestamp': int(time.time() * 1000)})
    
    async def _handle_orderbook_update(self, data: Dict, market_id: Optional[str]):
        if market_id is None or market_id not in self.subscribed_markets:
            return
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        for key in ['yes_bids', 'yes_asks', 'no_bids', 'no_asks']:
            if key in data:
                market.orderbook[key] = data[key]
        if 'bids' in data:
            market.orderbook['yes_bids'] = data.get('bids', [])
        if 'asks' in data:
            market.orderbook['yes_asks'] = data.get('asks', [])
        
        self._update_prices_from_orderbook(market)
        market.last_update = int(time.time() * 1000)
        await self._cache_orderbook_if_needed(market_id)
        self._store_price_data(market_id, market.yes_price, market.no_price)
        
        for cb in self.message_callbacks:
            cb('orderbook_update', {'market_id': market_id, 'orderbook_data': market.orderbook})
    
    async def _handle_ticker_update(self, data: Dict, market_id: Optional[str]):
        if market_id is None or market_id not in self.subscribed_markets:
            return
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        market.ticker = data
        market.last_update = int(time.time() * 1000)
        
        if 'yes_bid' in data and 'yes_ask' in data:
            try:
                bid, ask = float(data['yes_bid']), float(data['yes_ask'])
                if bid > 0 and ask > 0:
                    market.yes_price = (bid + ask) / 2
                    market.no_price = 100 - market.yes_price
            except:
                pass
        
        self._store_price_data(market_id, market.yes_price, market.no_price)
        
        if market.yes_price is not None:
            for cb in self.message_callbacks:
                cb('price_update', {'market_id': market_id, 'yes_price': market.yes_price,
                                   'no_price': market.no_price, 'timestamp': market.last_update})
        for cb in self.message_callbacks:
            cb('ticker_update', {'market_id': market_id, 'ticker_data': data})
    
    async def _handle_trade_update(self, data: Dict, market_id: Optional[str]):
        if market_id is None or market_id not in self.subscribed_markets:
            return
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        market.recent_trades.append(data)
        market.last_update = int(time.time() * 1000)
        
        for cb in self.message_callbacks:
            cb('trade_update', {'market_id': market_id, 'trade_data': data})
    
    def _update_prices_from_orderbook(self, market: MarketData):
        try:
            bids = market.orderbook.get('yes_bids', [])
            asks = market.orderbook.get('yes_asks', [])
            if bids and asks:
                def get_p(e: Any) -> float:
                    if isinstance(e, dict):
                        price_val = e.get('price')
                        if price_val is None:
                            price_val = e.get('p', 0)
                        if isinstance(price_val, (int, float, str)):
                            return float(price_val)
                        return 0.0
                    elif isinstance(e, list) and len(e) > 0:
                        first = e[0]
                        if isinstance(first, (int, float, str)):
                            return float(first)
                        return 0.0
                    elif isinstance(e, (int, float, str)):
                        return float(e)
                    return 0.0
                best_bid, best_ask = get_p(bids[0]), get_p(asks[0])
                if best_bid > 0 and best_ask > 0:
                    market.yes_price = (best_bid + best_ask) / 2
                    market.no_price = 100 - market.yes_price
        except Exception as e:
            self.add_log('warning', f'Price calc error: {e}')
    
    def _store_price_data(self, market_id: str, yes_price: Optional[float], no_price: Optional[float]):
        if market_id not in self.price_data:
            self.price_data[market_id] = []
        if yes_price is not None or no_price is not None:
            self.price_data[market_id].append({'timestamp': int(time.time()*1000), 'yes_price': yes_price, 'no_price': no_price})
            self.price_data[market_id] = self.price_data[market_id][-1000:]
            if len(self.price_data[market_id]) % 10 == 0:
                self._save_price_data()
    
    async def _cache_orderbook_if_needed(self, market_id: str):
        now = time.time()
        if now - self.last_cache_time.get(market_id, 0) >= self.cache_interval:
            await self._save_orderbook_to_disk(market_id, now)
    
    async def _save_orderbook_to_disk(self, market_id: str, ts: Optional[float] = None):
        ts = ts or time.time()
        try:
            market = self.market_data.get(market_id)
            if market and market.orderbook:
                path = os.path.join(self.data_dir, 'orderbooks', market_id)
                os.makedirs(path, exist_ok=True)
                with open(os.path.join(path, f'orderbook_{int(ts*1000)}.json'), 'w') as f:
                    json.dump({'market_id': market_id, 'timestamp': int(ts*1000), 'datetime': datetime.fromtimestamp(ts).isoformat(),
                              'orderbook': market.orderbook, 'yes_price': market.yes_price, 'no_price': market.no_price}, f, indent=2)
                self.last_cache_time[market_id] = ts
                self.add_log('info', f'Cached orderbook for {market_id}')
        except Exception as e:
            self.add_log('error', f'Cache failed for {market_id}: {e}')
    
    async def _fetch_initial_orderbook(self, market_id: str) -> Optional[Dict]:
        try:
            url = f"{self.api_client.api_client.configuration.host}/markets/{market_id}/orderbook"
            self.add_log('info', f'Fetching orderbook from {url}')
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.add_log('warning', f'Orderbook fetch failed: {e}')
            return None
    
    def _parse_orderbook_data(self, data: Dict) -> Dict:
        """Parse orderbook: YES bids from 'yes', YES asks from (100 - NO price)."""
        parsed = {'yes_bids': [], 'yes_asks': []}
        try:
            ob = data.get('orderbook', data)
            if 'yes' in ob:
                parsed['yes_bids'] = sorted([{'price': float(e[0]), 'size': float(e[1])} for e in ob['yes'] if len(e) >= 2],
                                           key=lambda x: x['price'], reverse=True)
            if 'no' in ob:
                parsed['yes_asks'] = sorted([{'price': 100 - float(e[0]), 'size': float(e[1])} for e in ob['no'] if len(e) >= 2],
                                           key=lambda x: x['price'])
        except Exception as e:
            self.add_log('warning', f'Parse error: {e}')
        return parsed
    
    def _calculate_price_from_orderbook(self, ob: Dict, prefer_ask: bool = False) -> tuple:
        try:
            bids, asks = ob.get('yes_bids', []), ob.get('yes_asks', [])
            def get_p(e: Any) -> float:
                if not e:
                    return 0.0
                if isinstance(e, dict):
                    price_val = e.get('price')
                    if price_val is None and isinstance(e, list):
                        price_val = e[0] if len(e) > 0 else 0
                    if isinstance(price_val, (int, float, str)):
                        return float(price_val)
                    return 0.0
                elif isinstance(e, list) and len(e) > 0:
                    first = e[0]
                    if isinstance(first, (int, float, str)):
                        return float(first)
                    return 0.0
                elif isinstance(e, (int, float, str)):
                    return float(e)
                return 0.0
            if bids and asks:
                best_bid, best_ask = get_p(bids[0]), get_p(asks[0])
                if best_bid > 0 and best_ask > 0:
                    yes_price = best_ask if prefer_ask else (best_bid + best_ask) / 2
                    return yes_price, 100 - yes_price
        except Exception as e:
            self.add_log('warning', f'Price calc error: {e}')
        return None, None
    
    async def subscribe_to_market(self, market_id: str) -> bool:
        """Subscribe to market and fetch initial orderbook."""
        self.add_log('info', f'Subscribing to {market_id}')
        
        if not self.streamer or not self.streamer._is_connected():
            await self.connect()
            if not self.streamer or not self.streamer._is_connected():
                return False
        
        try:
            if market_id not in self.market_data:
                self.market_data[market_id] = MarketData(market_id)
            market = self.market_data[market_id]
            
            initial = await self._fetch_initial_orderbook(market_id)
            if initial:
                market.orderbook = self._parse_orderbook_data(initial)
                yes_p, no_p = self._calculate_price_from_orderbook(market.orderbook, prefer_ask=True)
                if yes_p:
                    market.yes_price, market.no_price = yes_p, no_p
                    self._store_price_data(market_id, yes_p, no_p)
                await self._save_orderbook_to_disk(market_id)
                
                for cb in self.message_callbacks:
                    cb('orderbook_update', {'market_id': market_id, 'orderbook_data': market.orderbook})
                    if yes_p:
                        cb('price_update', {'market_id': market_id, 'yes_price': yes_p, 'no_price': no_p, 'timestamp': int(time.time()*1000)})
            
            if await self.streamer.subscribe_to_market(market_id, channels=["ticker", "orderbook_delta", "trade"]):
                self.subscribed_markets.add(market_id)
                market.subscribed = True
                self._save_subscriptions()
                self.add_log('success', f'Subscribed to {market_id}')
                return True
            self.add_log('error', f'Subscribe failed: {market_id}')
            return False
        except Exception as e:
            self.add_log('error', f'Subscribe error: {e}')
            return False
    
    async def unsubscribe_from_market(self, market_id: str):
        self.subscribed_markets.discard(market_id)
        if market_id in self.market_data:
            self.market_data[market_id].subscribed = False
        self._save_subscriptions()
        self.add_log('success', f'Unsubscribed from {market_id}')
    
    async def disconnect(self):
        if self.streamer:
            self.streamer.shutdown()
            self.streamer = None
        self.connection_status = 'disconnected'
        self.subscribed_markets.clear()
        self.add_log('success', 'Disconnected')
    
    async def force_reconnect(self):
        await self.disconnect()
        await asyncio.sleep(1)
        await self.connect()
    
    def clear_logs(self):
        self.logs.clear()
        self.add_log('info', 'Logs cleared')
    
    def get_status(self) -> Dict:
        return {
            'connection_status': self.connection_status, 'subscribed_markets': list(self.subscribed_markets),
            'market_data': {mid: {'yes_price': m.yes_price, 'no_price': m.no_price, 'last_update': m.last_update,
                                 'subscribed': m.subscribed, 'orderbook': m.orderbook} for mid, m in self.market_data.items()},
            'price_data': self.price_data, 'logs': self.logs[-50:]
        }
    
    def _save_price_data(self):
        try:
            with open(self.price_data_file, 'w') as f:
                json.dump(self.price_data, f)
        except Exception as e:
            self.add_log('warning', f'Save price data failed: {e}')
    
    def _load_price_data(self):
        if os.path.exists(self.price_data_file):
            try:
                with open(self.price_data_file) as f:
                    self.price_data = json.load(f)
                print(f'ℹ️ Loaded price data for {len(self.price_data)} markets')
            except Exception as e:
                print(f'⚠️ Load price data failed: {e}')
    
    def _save_subscriptions(self):
        try:
            with open(self.subscriptions_file, 'w') as f:
                json.dump(list(self.subscribed_markets), f)
        except Exception as e:
            self.add_log('warning', f'Save subscriptions failed: {e}')
    
    def _load_subscriptions(self):
        if os.path.exists(self.subscriptions_file):
            try:
                with open(self.subscriptions_file) as f:
                    self.subscribed_markets = set(json.load(f))
                print(f'ℹ️ Loaded {len(self.subscribed_markets)} subscriptions')
            except Exception as e:
                print(f'⚠️ Load subscriptions failed: {e}')

