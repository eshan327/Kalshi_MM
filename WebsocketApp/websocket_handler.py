"""
Kalshi WebSocket Handler
Wraps KalshiMarketStreamer for use in Flask app with caching and data management
"""

import asyncio
import json
import time
import os
import requests
from datetime import datetime
from typing import Dict, Set, List, Optional, Callable
from collections import deque

# Import the KalshiMarketStreamer
import sys
project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
from Websocket.market_streamer import KalshiMarketStreamer
from Setup.apiSetup import KalshiAPI


class MarketData:
    """Container for market data"""
    def __init__(self, market_id: str):
        self.market_id = market_id
        self.orderbook = {
            'yes_bids': [],
            'yes_asks': []
        }
        self.ticker = {}
        self.recent_trades = deque(maxlen=50)
        self.yes_price = None
        self.no_price = None
        self.last_update = int(time.time() * 1000)
        self.subscribed = False


class KalshiWebSocketHandler:
    """Handler for Kalshi WebSocket connection with caching and data management"""
    
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.streamer: Optional[KalshiMarketStreamer] = None
        self.connection_status = 'disconnected'
        self.subscribed_markets: Set[str] = set()
        self.market_data: Dict[str, MarketData] = {}
        self.message_callbacks: List[Callable] = []
        self.logs: List[Dict] = []
        
        # API client for fetching initial orderbook
        self.api_client = KalshiAPI().get_client(demo=demo)
        
        # Caching for orderbook and price data
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_interval = 600  # 10 minutes in seconds
        self.last_cache_time = {}
        self.price_data: Dict[str, List[Dict]] = {}  # {market_id: [{timestamp, yes_price, no_price}]}
        self.price_data_file = os.path.join(self.data_dir, 'price_data.json')
        self.subscriptions_file = os.path.join(self.data_dir, 'subscriptions.json')
        
        # Load persisted data on initialization
        self._load_price_data()
        self._load_subscriptions()
        
    def add_log(self, level: str, message: str, details: Optional[Dict] = None):
        """Add a log entry"""
        log_entry = {
            'id': f"{int(time.time() * 1000)}{hash(message) % 10000}",
            'timestamp': int(time.time() * 1000),
            'level': level,
            'message': message,
            'details': details
        }
        
        # Keep last 100 logs
        self.logs = self.logs[-99:] + [log_entry]
        
        # Log to console
        emoji_map = {
            'error': '🚨',
            'warning': '⚠️',
            'success': '✅',
            'info': 'ℹ️'
        }
        print(f"{emoji_map.get(level, '📝')} {message}")
        if details:
            print(f"   Details: {json.dumps(details, indent=2)}")
        
        # Notify callbacks
        for callback in self.message_callbacks:
            callback('log', log_entry)
    
    def add_message_callback(self, callback: Callable):
        """Add callback for real-time updates"""
        self.message_callbacks.append(callback)
    
    def remove_message_callback(self, callback: Callable):
        """Remove callback"""
        if callback in self.message_callbacks:
            self.message_callbacks.remove(callback)
    
    async def connect(self):
        """Connect to Kalshi WebSocket"""
        if self.streamer and self.streamer._is_connected():
            self.add_log('info', 'WebSocket already connected')
            return
        
        self.connection_status = 'connecting'
        self.add_log('info', f'Attempting connection to Kalshi WebSocket (demo={self.demo})')
        
        try:
            # Initialize streamer with no initial markets (we'll subscribe dynamically)
            self.streamer = KalshiMarketStreamer(market_ids=[], demo=self.demo, 
                                                channels=["ticker", "orderbook_delta", "trade"])
            
            # Set up callbacks for different message types
            async def on_orderbook_update(data, market_id):
                await self._handle_orderbook_update(data, market_id)
            
            async def on_ticker_update(data, market_id):
                await self._handle_ticker_update(data, market_id)
            
            async def on_trade_update(data, market_id):
                await self._handle_trade_update(data, market_id)
            
            self.streamer.on_orderbook_update = on_orderbook_update
            self.streamer.on_ticker_update = on_ticker_update
            self.streamer.on_trade_update = on_trade_update
            
            # Override handle_message to also emit raw messages
            original_handle = self.streamer.handle_message
            
            async def wrapped_handle(message):
                # Emit raw message for console display
                self._emit_raw_message(message)
                # Call original handler
                await original_handle(message)
            
            self.streamer.handle_message = wrapped_handle
            
            # Connect and start listening
            if await self.streamer.connect():
                self.connection_status = 'connected'
                self.add_log('success', 'Successfully connected to Kalshi WebSocket')
                # Start listening in background
                asyncio.create_task(self.streamer.listen())
            else:
                self.connection_status = 'error'
                self.add_log('error', 'Failed to connect to Kalshi WebSocket')
                
        except Exception as error:
            self.add_log('error', f'Failed to create WebSocket connection: {str(error)}')
            self.connection_status = 'error'
    
    def _emit_raw_message(self, message: str):
        """Emit raw message for console display"""
        try:
            # Try to parse and format the message
            try:
                parsed = json.loads(message)
                formatted = json.dumps(parsed, indent=2)
            except:
                formatted = message
            
            for callback in self.message_callbacks:
                callback('raw_message', {
                    'message': formatted,
                    'timestamp': int(time.time() * 1000)
                })
        except Exception as e:
            pass  # Silently fail for raw message emission
    
    async def _handle_orderbook_update(self, data: Dict, market_id: str):
        """Handle orderbook update"""
        if market_id not in self.subscribed_markets:
            return
        
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        
        # Update orderbook from delta
        # Kalshi orderbook format may vary - handle both full snapshots and deltas
        # Format could be: {"yes_bids": [...], "yes_asks": [...], "no_bids": [...], "no_asks": [...]}
        # Or: {"bids": [...], "asks": [...]} for yes contracts
        # Or delta format with updates
        
        # Handle yes contract orderbook
        if 'yes_bids' in data:
            market.orderbook['yes_bids'] = data['yes_bids']
        elif 'bids' in data and 'side' not in str(data):  # Full snapshot
            market.orderbook['yes_bids'] = data.get('bids', [])
        
        if 'yes_asks' in data:
            market.orderbook['yes_asks'] = data['yes_asks']
        elif 'asks' in data and 'side' not in str(data):  # Full snapshot
            market.orderbook['yes_asks'] = data.get('asks', [])
        
        # Handle no contract orderbook
        if 'no_bids' in data:
            market.orderbook['no_bids'] = data['no_bids']
        if 'no_asks' in data:
            market.orderbook['no_asks'] = data['no_asks']
        
        # Calculate prices from best bid/ask
        try:
            yes_bids = market.orderbook.get('yes_bids', [])
            yes_asks = market.orderbook.get('yes_asks', [])
            
            if yes_bids and yes_asks:
                # Handle different orderbook entry formats
                def get_price(entry):
                    if isinstance(entry, dict):
                        return float(entry.get('price', entry.get('p', 0)))
                    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        return float(entry[0])  # [price, size] format
                    else:
                        return float(entry) if entry else 0
                
                best_yes_bid = get_price(yes_bids[0]) if yes_bids else 0
                best_yes_ask = get_price(yes_asks[0]) if yes_asks else 0
                
                if best_yes_bid > 0 and best_yes_ask > 0:
                    market.yes_price = (best_yes_bid + best_yes_ask) / 2
                    market.no_price = 100 - market.yes_price  # Assuming probability market (0-100)
        except Exception as e:
            self.add_log('warning', f'Error calculating prices from orderbook: {str(e)}')
        
        market.last_update = int(time.time() * 1000)
        
        # Cache orderbook every 10 minutes
        await self._cache_orderbook_if_needed(market_id)
        
        # Store price data
        self._store_price_data(market_id, market.yes_price, market.no_price)
        
        # Notify callbacks
        for callback in self.message_callbacks:
            callback('orderbook_update', {
                'market_id': market_id,
                'orderbook_data': market.orderbook
            })
    
    async def _handle_ticker_update(self, data: Dict, market_id: str):
        """Handle ticker update"""
        if market_id not in self.subscribed_markets:
            return
        
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        market.ticker = data
        market.last_update = int(time.time() * 1000)
        
        # Extract prices from ticker if available
        # Ticker has yes_bid and yes_ask in cents (0-100)
        if 'yes_bid' in data and 'yes_ask' in data:
            try:
                yes_bid = float(data.get('yes_bid', 0))
                yes_ask = float(data.get('yes_ask', 0))
                if yes_bid > 0 and yes_ask > 0:
                    market.yes_price = (yes_bid + yes_ask) / 2
                    market.no_price = 100 - market.yes_price
                    self.add_log('info', f'Ticker price for {market_id}: yes={market.yes_price}, no={market.no_price}')
            except Exception as e:
                self.add_log('warning', f'Error extracting price from ticker: {str(e)}')
        elif 'yes_bid' in data:
            try:
                yes_bid = float(data.get('yes_bid', 0))
                if yes_bid > 0:
                    market.yes_price = yes_bid
                    market.no_price = 100 - yes_bid
            except:
                pass
        elif 'yes_ask' in data:
            try:
                yes_ask = float(data.get('yes_ask', 0))
                if yes_ask > 0:
                    market.yes_price = yes_ask
                    market.no_price = 100 - yes_ask
            except:
                pass
        
        # Store price data
        self._store_price_data(market_id, market.yes_price, market.no_price)
        
        # Notify callbacks with price update
        if market.yes_price is not None:
            for callback in self.message_callbacks:
                callback('price_update', {
                    'market_id': market_id,
                    'yes_price': market.yes_price,
                    'no_price': market.no_price,
                    'timestamp': market.last_update
                })
        
        # Notify callbacks
        for callback in self.message_callbacks:
            callback('ticker_update', {
                'market_id': market_id,
                'ticker_data': data
            })
    
    async def _handle_trade_update(self, data: Dict, market_id: str):
        """Handle trade update"""
        if market_id not in self.subscribed_markets:
            return
        
        if market_id not in self.market_data:
            self.market_data[market_id] = MarketData(market_id)
        
        market = self.market_data[market_id]
        market.recent_trades.append(data)
        market.last_update = int(time.time() * 1000)
        
        # Notify callbacks
        for callback in self.message_callbacks:
            callback('trade_update', {
                'market_id': market_id,
                'trade_data': data
            })
    
    def _store_price_data(self, market_id: str, yes_price: Optional[float], no_price: Optional[float]):
        """Store price data for chart reconstruction"""
        if market_id not in self.price_data:
            self.price_data[market_id] = []
        
        if yes_price is not None or no_price is not None:
            self.price_data[market_id].append({
                'timestamp': int(time.time() * 1000),
                'yes_price': yes_price,
                'no_price': no_price
            })
            
            # Keep last 1000 data points per market
            if len(self.price_data[market_id]) > 1000:
                self.price_data[market_id] = self.price_data[market_id][-1000:]
            
            # Persist to disk periodically (every 10 price updates per market)
            if len(self.price_data[market_id]) % 10 == 0:
                self._save_price_data()
    
    async def _cache_orderbook_if_needed(self, market_id: str):
        """Cache orderbook data every 10 minutes"""
        current_time = time.time()
        last_cache = self.last_cache_time.get(market_id, 0)
        
        if current_time - last_cache >= self.cache_interval:
            await self._save_orderbook_to_disk(market_id, current_time)
    
    async def _save_orderbook_to_disk(self, market_id: str, timestamp: float = None):
        """Save orderbook data to disk for later analysis"""
        if timestamp is None:
            timestamp = time.time()
        
        try:
            market = self.market_data.get(market_id)
            if market and market.orderbook:
                # Create a subdirectory for this market's orderbooks
                market_data_dir = os.path.join(self.data_dir, 'orderbooks', market_id)
                os.makedirs(market_data_dir, exist_ok=True)
                
                # Save with timestamp for chronological analysis
                cache_file = os.path.join(market_data_dir, f'orderbook_{int(timestamp * 1000)}.json')
                
                orderbook_data = {
                    'market_id': market_id,
                    'timestamp': int(timestamp * 1000),
                    'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                    'orderbook': market.orderbook,
                    'yes_price': market.yes_price,
                    'no_price': market.no_price,
                    'ticker': market.ticker if hasattr(market, 'ticker') else {}
                }
                
                with open(cache_file, 'w') as f:
                    json.dump(orderbook_data, f, indent=2)
                
                self.last_cache_time[market_id] = timestamp
                self.add_log('info', f'Cached orderbook for {market_id} at {datetime.fromtimestamp(timestamp).isoformat()}')
            else:
                self.add_log('warning', f'No orderbook data available to cache for {market_id}')
        except Exception as e:
            self.add_log('error', f'Failed to cache orderbook for {market_id}: {str(e)}')
            import traceback
            self.add_log('error', f'Traceback: {traceback.format_exc()}')
    
    async def _fetch_initial_orderbook(self, market_id: str) -> Optional[Dict]:
        """Fetch initial orderbook snapshot from REST API"""
        try:
            config = self.api_client.api_client.configuration
            base_url = config.host
            url = f"{base_url}/markets/{market_id}/orderbook"
            
            self.add_log('info', f'Fetching initial orderbook from {url}')
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            orderbook_data = response.json()
            
            self.add_log('info', f'Fetched initial orderbook for {market_id}, keys: {list(orderbook_data.keys()) if isinstance(orderbook_data, dict) else "not a dict"}')
            return orderbook_data
        except Exception as e:
            self.add_log('warning', f'Failed to fetch initial orderbook for {market_id}: {str(e)}')
            import traceback
            self.add_log('warning', f'Traceback: {traceback.format_exc()}')
            return None
    
    def _parse_orderbook_data(self, orderbook_data: Dict) -> Dict:
        """Parse orderbook data into our format
        
        Kalshi orderbook structure:
        - 'yes' array: buy orders for YES contracts (bids) [price_in_cents, size]
        - 'no' array: buy orders for NO contracts (which represent asks for YES) [price_in_cents, size]
        
        For YES contract orderbook:
        - YES bids = 'yes' array (sorted descending by price)
        - YES asks = 'no' array converted (100 - no_price, sorted ascending)
        """
        parsed = {
            'yes_bids': [],
            'yes_asks': []
        }
        
        try:
            # Handle different orderbook formats
            if 'orderbook' in orderbook_data:
                ob = orderbook_data['orderbook']
            else:
                ob = orderbook_data
            
            # Extract YES bids from 'yes' array
            if 'yes' in ob:
                yes_array = ob['yes']
                if isinstance(yes_array, list):
                    yes_bids = []
                    for entry in yes_array:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            price = float(entry[0])
                            size = float(entry[1])
                            yes_bids.append({'price': price, 'size': size})
                    
                    # Sort bids descending (highest bid first)
                    yes_bids.sort(key=lambda x: x['price'], reverse=True)
                    parsed['yes_bids'] = yes_bids
            
            # Extract YES asks from 'no' array
            # Buying NO at price X is equivalent to selling YES at (100 - X)
            if 'no' in ob:
                no_array = ob['no']
                if isinstance(no_array, list):
                    yes_asks = []
                    for entry in no_array:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            no_price = float(entry[0])  # Price for NO contract
                            size = float(entry[1])
                            # Convert NO price to YES ask price
                            yes_price = 100 - no_price
                            yes_asks.append({'price': yes_price, 'size': size})
                    
                    # Sort asks ascending (lowest ask first)
                    yes_asks.sort(key=lambda x: x['price'])
                    parsed['yes_asks'] = yes_asks
            
            # Also handle direct yes_bids/yes_asks format (from WebSocket deltas)
            if 'yes_bids' in ob:
                # Ensure it's in the right format
                if isinstance(ob['yes_bids'], list) and len(ob['yes_bids']) > 0:
                    if isinstance(ob['yes_bids'][0], dict):
                        parsed['yes_bids'] = ob['yes_bids']
                    elif isinstance(ob['yes_bids'][0], (list, tuple)):
                        parsed['yes_bids'] = [{'price': float(e[0]), 'size': float(e[1])} 
                                             for e in ob['yes_bids'] if len(e) >= 2]
                        parsed['yes_bids'].sort(key=lambda x: x['price'], reverse=True)
            
            if 'yes_asks' in ob:
                # Ensure it's in the right format
                if isinstance(ob['yes_asks'], list) and len(ob['yes_asks']) > 0:
                    if isinstance(ob['yes_asks'][0], dict):
                        parsed['yes_asks'] = ob['yes_asks']
                    elif isinstance(ob['yes_asks'][0], (list, tuple)):
                        parsed['yes_asks'] = [{'price': float(e[0]), 'size': float(e[1])} 
                                             for e in ob['yes_asks'] if len(e) >= 2]
                        parsed['yes_asks'].sort(key=lambda x: x['price'])
                
        except Exception as e:
            self.add_log('warning', f'Error parsing orderbook data: {str(e)}')
            import traceback
            self.add_log('warning', f'Traceback: {traceback.format_exc()}')
        
        return parsed
    
    def _calculate_price_from_orderbook(self, orderbook: Dict, prefer_ask: bool = False) -> tuple:
        """Calculate yes and no prices from orderbook
        Bids are sorted descending (highest first), asks are sorted ascending (lowest first)
        
        Args:
            orderbook: Parsed orderbook data
            prefer_ask: If True and both bids/asks available, use ask price. Otherwise use mid-price.
        """
        yes_price = None
        no_price = None
        
        try:
            yes_bids = orderbook.get('yes_bids', [])
            yes_asks = orderbook.get('yes_asks', [])
            
            def get_price(entry):
                if isinstance(entry, dict):
                    return float(entry.get('price', entry.get('p', 0)))
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    return float(entry[0])
                else:
                    return float(entry) if entry else 0
            
            if yes_bids and yes_asks:
                # Bids are sorted descending, so first element is best bid
                # Asks are sorted ascending, so first element is best ask
                best_yes_bid = get_price(yes_bids[0]) if yes_bids else 0
                best_yes_ask = get_price(yes_asks[0]) if yes_asks else 0
                
                if best_yes_bid > 0 and best_yes_ask > 0:
                    if prefer_ask:
                        # Use ask price as specified for initial orderbook
                        yes_price = best_yes_ask
                    else:
                        # Use mid-price for updates
                        yes_price = (best_yes_bid + best_yes_ask) / 2
                    no_price = 100 - yes_price  # Assuming probability market (0-100)
            elif yes_bids:
                # Only bids available, use highest bid (first element)
                best_yes_bid = get_price(yes_bids[0])
                if best_yes_bid > 0:
                    yes_price = best_yes_bid
                    no_price = 100 - yes_price
            elif yes_asks:
                # Only asks available, use lowest ask (first element)
                best_yes_ask = get_price(yes_asks[0])
                if best_yes_ask > 0:
                    yes_price = best_yes_ask
                    no_price = 100 - yes_price
        except Exception as e:
            self.add_log('warning', f'Error calculating price from orderbook: {str(e)}')
            import traceback
            self.add_log('warning', f'Traceback: {traceback.format_exc()}')
        
        return yes_price, no_price
    
    async def subscribe_to_market(self, market_id: str) -> bool:
        """Subscribe to a market and fetch initial orderbook"""
        self.add_log('info', f'Attempting to subscribe to market: {market_id}')
        
        if not self.streamer or not self.streamer._is_connected():
            self.add_log('warning', 'WebSocket not connected - attempting to connect')
            await self.connect()
            if not self.streamer or not self.streamer._is_connected():
                return False
        
        try:
            # Initialize market data
            if market_id not in self.market_data:
                self.market_data[market_id] = MarketData(market_id)
            
            market = self.market_data[market_id]
            
            # Fetch initial orderbook snapshot
            initial_orderbook = await self._fetch_initial_orderbook(market_id)
            if initial_orderbook:
                parsed_orderbook = self._parse_orderbook_data(initial_orderbook)
                market.orderbook = parsed_orderbook
                self.add_log('info', f'Parsed orderbook for {market_id}: yes_bids={len(parsed_orderbook.get("yes_bids", []))}, yes_asks={len(parsed_orderbook.get("yes_asks", []))}')
                
                # Calculate initial prices
                # For initial orderbook, use ask price (lowest ask) as specified
                yes_price, no_price = self._calculate_price_from_orderbook(parsed_orderbook, prefer_ask=True)
                if yes_price is not None:
                    market.yes_price = yes_price
                    market.no_price = no_price
                    # Store initial price data
                    self._store_price_data(market_id, yes_price, no_price)
                    self.add_log('info', f'Calculated initial prices for {market_id}: yes={yes_price}, no={no_price}')
                else:
                    self.add_log('warning', f'Could not calculate initial price for {market_id} from orderbook')
                    
                # Save initial orderbook to disk immediately for analysis
                await self._save_orderbook_to_disk(market_id)
                
                # Always notify callbacks with initial orderbook data (even if no price)
                for callback in self.message_callbacks:
                    callback('orderbook_update', {
                        'market_id': market_id,
                        'orderbook_data': market.orderbook
                    })
                
                # Notify price update if we have prices
                if yes_price is not None:
                    for callback in self.message_callbacks:
                        callback('price_update', {
                            'market_id': market_id,
                            'yes_price': yes_price,
                            'no_price': no_price,
                            'timestamp': int(time.time() * 1000)
                        })
            else:
                self.add_log('warning', f'Could not fetch initial orderbook for {market_id}')
            
            # Subscribe to WebSocket channels
            success = await self.streamer.subscribe_to_market(market_id, channels=["ticker", "orderbook_delta", "trade"])
            if success:
                self.subscribed_markets.add(market_id)
                market.subscribed = True
                self._save_subscriptions()  # Persist subscriptions
                self.add_log('success', f'Successfully subscribed to market: {market_id}')
                return True
            else:
                self.add_log('error', f'Failed to subscribe to market: {market_id}')
                return False
        except Exception as error:
            self.add_log('error', f'Error subscribing to market: {market_id} - {str(error)}')
            return False
    
    async def unsubscribe_from_market(self, market_id: str):
        """Unsubscribe from a market"""
        try:
            self.add_log('info', f'Unsubscribing from market: {market_id}')
            
            # Remove from local tracking
            self.subscribed_markets.discard(market_id)
            if market_id in self.market_data:
                self.market_data[market_id].subscribed = False
                # Optionally remove market data
                # del self.market_data[market_id]
            
            # Note: Kalshi WebSocket doesn't require explicit unsubscribe
            # The subscription is managed locally
            self._save_subscriptions()  # Persist subscriptions
            self.add_log('success', f'Successfully unsubscribed from market: {market_id}')
            
        except Exception as error:
            self.add_log('error', f'Error unsubscribing from market: {market_id} - {str(error)}')
    
    async def disconnect(self):
        """Disconnect WebSocket"""
        self.add_log('info', 'Disconnecting WebSocket...')
        
        if self.streamer:
            self.streamer.shutdown()
            self.streamer = None
        
        self.connection_status = 'disconnected'
        self.subscribed_markets.clear()
        self.add_log('success', 'WebSocket disconnected')
    
    async def force_reconnect(self):
        """Force reconnection"""
        self.add_log('info', 'Force reconnecting...')
        await self.disconnect()
        await asyncio.sleep(1)
        await self.connect()
    
    def clear_logs(self):
        """Clear all logs"""
        self.logs.clear()
        self.add_log('info', 'Logs cleared')
    
    def get_status(self) -> Dict:
        """Get current status"""
        return {
            'connection_status': self.connection_status,
            'subscribed_markets': list(self.subscribed_markets),
            'market_data': {
                market_id: {
                    'yes_price': market.yes_price,
                    'no_price': market.no_price,
                    'last_update': market.last_update,
                    'subscribed': market.subscribed,
                    'orderbook': market.orderbook
                }
                for market_id, market in self.market_data.items()
            },
            'price_data': self.price_data,  # Include all historical price data for charts
            'logs': self.logs[-50:]  # Last 50 logs
        }
    
    def _save_price_data(self):
        """Save price data to disk"""
        try:
            with open(self.price_data_file, 'w') as f:
                json.dump(self.price_data, f, indent=2)
        except Exception as e:
            self.add_log('warning', f'Failed to save price data: {str(e)}')
    
    def _load_price_data(self):
        """Load price data from disk"""
        if os.path.exists(self.price_data_file):
            try:
                with open(self.price_data_file, 'r') as f:
                    loaded_data = json.load(f)
                    # Convert string keys back to proper format if needed
                    self.price_data = {k: v for k, v in loaded_data.items()}
                    # Only log if add_log is available (after __init__ completes)
                    if hasattr(self, 'add_log'):
                        self.add_log('info', f'Loaded price data for {len(self.price_data)} markets')
                    else:
                        print(f'ℹ️ Loaded price data for {len(self.price_data)} markets')
            except Exception as e:
                if hasattr(self, 'add_log'):
                    self.add_log('warning', f'Failed to load price data: {str(e)}')
                else:
                    print(f'⚠️ Failed to load price data: {str(e)}')
    
    def _save_subscriptions(self):
        """Save subscriptions to disk"""
        try:
            with open(self.subscriptions_file, 'w') as f:
                json.dump(list(self.subscribed_markets), f, indent=2)
        except Exception as e:
            self.add_log('warning', f'Failed to save subscriptions: {str(e)}')
    
    def _load_subscriptions(self):
        """Load subscriptions from disk"""
        if os.path.exists(self.subscriptions_file):
            try:
                with open(self.subscriptions_file, 'r') as f:
                    loaded_subscriptions = json.load(f)
                    self.subscribed_markets = set(loaded_subscriptions)
                    # Only log if add_log is available (after __init__ completes)
                    if hasattr(self, 'add_log'):
                        self.add_log('info', f'Loaded {len(self.subscribed_markets)} persisted subscriptions')
                    else:
                        print(f'ℹ️ Loaded {len(self.subscribed_markets)} persisted subscriptions')
            except Exception as e:
                if hasattr(self, 'add_log'):
                    self.add_log('warning', f'Failed to load subscriptions: {str(e)}')
                else:
                    print(f'⚠️ Failed to load subscriptions: {str(e)}')

