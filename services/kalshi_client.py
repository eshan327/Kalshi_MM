"""
Kalshi API Client Service

Wrapper around the Kalshi Python SDK providing unified access to all API functionality.
Handles authentication, order management, positions, and market data.
"""
import uuid
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from kalshi_python import KalshiClient
from kalshi_python.api.portfolio_api import PortfolioApi
from kalshi_python.api.markets_api import MarketsApi
from kalshi_python.api.series_api import SeriesApi
from kalshi_python.models.create_order_request import CreateOrderRequest

from kalshi_python.configuration import Configuration

from config import config as app_config

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of an order operation."""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class Position:
    """Represents a position in a market."""
    ticker: str
    market_title: str
    position: int  # Positive = long YES, negative = short YES (long NO)
    average_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0


class KalshiService:
    """
    Service wrapper for Kalshi API operations.
    
    Uses the SDK for authenticated operations and falls back to REST API
    where SDK has known issues (e.g., orderbook mapping bug).
    """
    
    def __init__(self):
        self._client: Optional[KalshiClient] = None
        self._portfolio_api: Optional[PortfolioApi] = None
        self._markets_api: Optional[MarketsApi] = None
        self._series_api: Optional[SeriesApi] = None
        self._private_key: Optional[str] = None
        self._initialized = False
        
    def initialize(self) -> bool:
        """Initialize the Kalshi client with credentials."""
        try:
            # Load private key
            key_file = app_config.kalshi.key_file
            with open(key_file, "r") as f:
                self._private_key = f.read()
            
            # Configure SDK
            sdk_config = Configuration()
            sdk_config.host = app_config.kalshi.base_url
            sdk_config.api_key_id = app_config.kalshi.api_key_id
            sdk_config.private_key_pem = self._private_key
            
            # Create client and API instances
            self._client = KalshiClient(sdk_config)
            self._portfolio_api = PortfolioApi(self._client)
            self._markets_api = MarketsApi(self._client)
            self._series_api = SeriesApi(self._client)
            
            self._initialized = True
            logger.info(f"Kalshi service initialized (prod={app_config.kalshi.use_prod})")
            return True
            
        except FileNotFoundError:
            logger.error(f"Key file not found: {key_file}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Kalshi service: {e}")
            return False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    # =========================================================================
    # Account Operations
    # =========================================================================
    
    def get_balance(self) -> Optional[float]:
        """Get account balance in dollars."""
        if not self._initialized or self._portfolio_api is None:
            return None
        try:
            response = self._portfolio_api.get_balance()
            if response.balance is None:
                return None
            return response.balance / 100  # Convert cents to dollars
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None
    
    # =========================================================================
    # Market Data Operations
    # =========================================================================
    
    def get_series(self, series_ticker: str) -> Optional[Dict[str, Any]]:
        """Get series information."""
        if not self._initialized or self._series_api is None:
            return None
        try:
            response = self._series_api.get_series_by_ticker(series_ticker)
            if response.series is None:
                return None
            return {
                'ticker': response.series.ticker,
                'title': response.series.title,
            }
        except Exception as e:
            logger.error(f"Error getting series {series_ticker}: {e}")
            return None
    
    def get_markets(
        self, 
        series_ticker: Optional[str] = None,
        status: str = "open"
    ) -> List[Dict[str, Any]]:
        """Get markets, optionally filtered by series and status."""
        if not self._initialized or self._markets_api is None:
            return []
        try:
            kwargs = {"status": status}
            if series_ticker:
                kwargs["series_ticker"] = series_ticker
                
            response = self._markets_api.get_markets(**kwargs)
            
            markets = []
            if response.markets:
                for m in response.markets:
                    markets.append({
                        'ticker': m.ticker,
                        'title': m.title,
                        'status': m.status,
                        'close_time': m.close_time,
                        'yes_bid': m.yes_bid,
                        'yes_ask': m.yes_ask,
                        'last_price': m.last_price,
                        'volume': m.volume,
                        'volume_24h': m.volume_24h,
                    })
            return markets
        except Exception as e:
            logger.error(f"Error getting markets: {e}")
            return []
    
    def get_orderbook(self, market_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get orderbook for a market using SDK.
        
        Returns dict with 'yes' and 'no' lists of [price, quantity] pairs.
        Note: SDK uses var_true/var_false for yes/no due to Python naming.
        """
        if not self._initialized or self._markets_api is None:
            return None
        try:
            response = self._markets_api.get_market_orderbook(market_ticker)
            ob = response.orderbook
            
            if not ob:
                return {'yes': [], 'no': []}
            
            # Convert SDK model to simpler format
            # SDK uses var_true (YES bids) and var_false (NO bids)
            yes_bids = [[lvl.price, lvl.count] for lvl in (ob.var_true or [])]
            no_bids = [[lvl.price, lvl.count] for lvl in (ob.var_false or [])]
            
            return {'yes': yes_bids, 'no': no_bids}
        except Exception as e:
            logger.error(f"Error getting orderbook for {market_ticker}: {e}")
            return None
    
    def get_market_metrics(self, market_ticker: str) -> Dict[str, Any]:
        """
        Get computed metrics for a market (bid, ask, spread, mid).
        """
        orderbook = self.get_orderbook(market_ticker)
        if not orderbook:
            return {'bid': None, 'ask': None, 'spread': None, 'mid': None}
        
        yes_bids = orderbook.get('yes', [])
        no_bids = orderbook.get('no', [])
        
        metrics = {'bid': None, 'ask': None, 'spread': None, 'mid': None}
        
        # Best YES bid (highest price someone will pay for YES)
        if yes_bids:
            metrics['bid'] = yes_bids[-1][0]
        
        # Best YES ask (derived from best NO bid)
        if no_bids:
            best_no_bid = no_bids[-1][0]
            metrics['ask'] = 100 - best_no_bid
        
        # Spread and mid
        if metrics['bid'] is not None and metrics['ask'] is not None:
            spread = metrics['ask'] - metrics['bid']
            if spread > 0:
                metrics['spread'] = spread
                metrics['mid'] = (metrics['bid'] + metrics['ask']) / 2
        
        return metrics
    
    # =========================================================================
    # Order Operations
    # =========================================================================
    
    def create_order(
        self,
        ticker: str,
        action: str,  # 'buy' or 'sell'
        side: str,    # 'yes' or 'no'
        count: int,
        order_type: str = 'limit',
        price: Optional[int] = None,  # Price in cents (1-99) for limit orders
        client_order_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Create a new order.
        
        Args:
            ticker: Market ticker
            action: 'buy' or 'sell'
            side: 'yes' or 'no'
            count: Number of contracts
            order_type: 'limit' or 'market'
            price: Limit price in cents (required for limit orders)
            client_order_id: Optional UUID for idempotency
        
        Returns:
            OrderResult with success status and order details
        """
        if not self._initialized or self._portfolio_api is None:
            return OrderResult(success=False, error="Service not initialized")
        
        if order_type == 'limit' and price is None:
            return OrderResult(success=False, error="Limit orders require a price")
        
        if client_order_id is None:
            client_order_id = str(uuid.uuid4())
        
        try:
            # Build the order request
            order_params = {
                'ticker': ticker,
                'action': action,
                'side': side,
                'count': count,
                'type': order_type,
                'client_order_id': client_order_id,
            }
            
            # Add price based on side
            if order_type == 'limit':
                if side == 'yes':
                    order_params['yes_price'] = price
                else:
                    order_params['no_price'] = price
            
            request = CreateOrderRequest(**order_params)
            response = self._portfolio_api.create_order(create_order_request=request)
            
            if response.order is None:
                return OrderResult(success=False, error="Order response missing order data", client_order_id=client_order_id)
            
            logger.info(f"Order created: {ticker} {action} {count} {side} @ {price}¢")
            
            return OrderResult(
                success=True,
                order_id=response.order.order_id,
                client_order_id=client_order_id,
                data={
                    'ticker': ticker,
                    'action': action,
                    'side': side,
                    'count': count,
                    'price': price,
                    'status': response.order.status,
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return OrderResult(success=False, error=str(e), client_order_id=client_order_id)
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order by ID."""
        if not self._initialized or self._portfolio_api is None:
            return OrderResult(success=False, error="Service not initialized")
        
        try:
            response = self._portfolio_api.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return OrderResult(success=True, order_id=order_id)
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return OrderResult(success=False, order_id=order_id, error=str(e))
    
    def cancel_all_orders(self, ticker: Optional[str] = None) -> OrderResult:
        """Cancel all open orders, optionally filtered by ticker."""
        if not self._initialized or self._portfolio_api is None:
            return OrderResult(success=False, error="Service not initialized")
        
        try:
            # Get all open orders
            kwargs = {'status': 'resting'}
            if ticker:
                kwargs['ticker'] = ticker
            
            orders_response = self._portfolio_api.get_orders(**kwargs)
            
            if not orders_response.orders:
                logger.info("No orders to cancel")
                return OrderResult(success=True, data={'cancelled': 0})
            
            cancelled = 0
            errors = []
            
            for order in orders_response.orders:
                if order.order_id is None:
                    errors.append("Order missing order_id")
                    continue
                result = self.cancel_order(order.order_id)
                if result.success:
                    cancelled += 1
                else:
                    errors.append(f"{order.order_id}: {result.error}")
            
            if errors:
                return OrderResult(
                    success=False,
                    error=f"Cancelled {cancelled}, errors: {'; '.join(errors)}",
                    data={'cancelled': cancelled, 'errors': errors}
                )
            
            logger.info(f"Cancelled {cancelled} orders")
            return OrderResult(success=True, data={'cancelled': cancelled})
            
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return OrderResult(success=False, error=str(e))
    
    def get_orders(
        self,
        status: Optional[str] = None,  # 'resting', 'canceled', 'executed'
        ticker: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get orders, optionally filtered by status and ticker."""
        if not self._initialized or self._portfolio_api is None:
            return []
        
        try:
            kwargs = {}
            if status:
                kwargs['status'] = status
            if ticker:
                kwargs['ticker'] = ticker
            
            response = self._portfolio_api.get_orders(**kwargs)
            
            orders = []
            if response.orders:
                for o in response.orders:
                    orders.append({
                        'order_id': o.order_id,
                        'ticker': o.ticker,
                        'action': o.action,
                        'side': o.side,
                        'type': o.type,
                        'status': o.status,
                        'count': o.count,
                        'remaining_count': o.remaining_count,
                        'yes_price': o.yes_price,
                        'no_price': o.no_price,
                        'created_time': o.created_time,
                    })
            return orders
            
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    # =========================================================================
    # Position Operations
    # =========================================================================
    
    def get_positions(
        self,
        ticker: Optional[str] = None,
    ) -> List[Position]:
        """Get current positions."""
        if not self._initialized or self._portfolio_api is None:
            return []
        
        try:
            kwargs = {}
            if ticker:
                kwargs['ticker'] = ticker
            
            response = self._portfolio_api.get_positions(**kwargs)
            
            positions = []
            if response.positions:
                for p in response.positions:
                    if p.ticker is None:
                        continue
                    positions.append(Position(
                        ticker=p.ticker,
                        market_title=p.ticker,  # SDK doesn't provide market_title
                        position=p.position or 0,
                        average_price=(p.total_cost / p.position) if (p.position and p.total_cost is not None) else 0,
                        realized_pnl=p.realized_pnl / 100 if p.realized_pnl else 0,
                    ))
            return positions
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_fills(
        self,
        ticker: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent fills (trade executions)."""
        if not self._initialized or self._portfolio_api is None:
            return []
        
        try:
            kwargs: Dict[str, Any] = {'limit': limit}
            if ticker:
                kwargs['ticker'] = ticker
            
            response = self._portfolio_api.get_fills(**kwargs)
            
            fills = []
            if response.fills:
                for f in response.fills:
                    fills.append({
                        'fill_id': f.fill_id,
                        'order_id': f.order_id,
                        'ticker': f.ticker,
                        'side': f.side,
                        'action': f.action,
                        'count': f.count,
                        'price': f.price,
                        'is_taker': f.is_taker,
                        'created_time': f.created_time,
                    })
            return fills
            
        except Exception as e:
            logger.error(f"Error getting fills: {e}")
            return []


# Global service instance
kalshi_service = KalshiService()
