"""
Market Maker Strategy Engine

Core market making logic - manages quotes, reacts to fills, and maintains positions.
"""
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from threading import Thread, Lock, Event
from enum import Enum

from config import config as app_config
from services.kalshi_client import kalshi_service, OrderResult
from services.orderbook import orderbook_service, Orderbook
from services.risk_manager import risk_manager
from services.fair_value import fair_value_calculator, FairValueResult

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """Strategy running state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class Quote:
    """Represents a two-sided quote."""
    ticker: str
    bid_price: int  # Cents (1-99)
    bid_size: int
    ask_price: int  # Cents (1-99)
    ask_size: int
    fair_value: Optional[float] = None


@dataclass
class MarketState:
    """State for a single market being quoted."""
    ticker: str
    title: str
    is_active: bool = True
    current_quote: Optional[Quote] = None
    fair_value: Optional[FairValueResult] = None
    last_quote_time: Optional[datetime] = None
    bid_order_id: Optional[str] = None
    ask_order_id: Optional[str] = None
    fills_count: int = 0
    close_time: Optional[datetime] = None


@dataclass  
class StrategyStats:
    """Strategy performance statistics."""
    total_quotes: int = 0
    total_fills: int = 0
    total_volume: int = 0
    start_time: Optional[datetime] = None
    uptime_seconds: float = 0


class MarketMaker:
    """
    Market making strategy engine.
    
    Continuously quotes on target markets, adjusting prices based on:
    - Fair value from weather forecasts
    - Current inventory (skew quotes to reduce risk)
    - Orderbook state
    - Risk limits
    """
    
    def __init__(self):
        self._state = StrategyState.STOPPED
        self._markets: Dict[str, MarketState] = {}
        self._stats = StrategyStats()
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        
    @property
    def state(self) -> StrategyState:
        return self._state
    
    @property
    def is_running(self) -> bool:
        return self._state == StrategyState.RUNNING
    
    def initialize(self) -> bool:
        """Initialize the market maker with target markets."""
        if not kalshi_service.is_initialized:
            logger.error("Kalshi service not initialized")
            return False
        
        # Load target series markets
        series = app_config.strategy.target_series
        markets = kalshi_service.get_markets(series_ticker=series, status="open")
        
        if not markets:
            logger.warning(f"No open markets found for series {series}")
            return False
        
        with self._lock:
            self._markets.clear()
            for m in markets:
                ticker = m['ticker']
                self._markets[ticker] = MarketState(
                    ticker=ticker,
                    title=m.get('title', ticker),
                    close_time=m.get('close_time'),
                )
        
        logger.info(f"Initialized with {len(self._markets)} markets")
        return True
    
    def start(self):
        """Start the market making strategy."""
        if self._state != StrategyState.STOPPED:
            logger.warning(f"Cannot start from state {self._state}")
            return
        
        self._state = StrategyState.STARTING
        self._stop_event.clear()
        
        # Start the main strategy thread
        self._thread = Thread(target=self._run_strategy_loop, daemon=True)
        self._thread.start()
        
        self._stats.start_time = datetime.now(timezone.utc)
        logger.info("Market maker started")
    
    def stop(self):
        """Stop the market making strategy."""
        if self._state == StrategyState.STOPPED:
            return
        
        self._state = StrategyState.STOPPING
        self._stop_event.set()
        
        # Cancel all outstanding orders
        self._cancel_all_quotes()
        
        if self._thread:
            self._thread.join(timeout=10)
        
        self._state = StrategyState.STOPPED
        logger.info("Market maker stopped")
    
    def pause(self):
        """Pause quoting (keeps orders but doesn't refresh)."""
        if self._state == StrategyState.RUNNING:
            self._state = StrategyState.PAUSED
            logger.info("Market maker paused")
    
    def resume(self):
        """Resume quoting."""
        if self._state == StrategyState.PAUSED:
            self._state = StrategyState.RUNNING
            logger.info("Market maker resumed")
    
    def _run_strategy_loop(self):
        """Main strategy loop."""
        self._state = StrategyState.RUNNING
        
        # Subscribe to orderbook updates for all markets
        tickers = list(self._markets.keys())
        orderbook_service.subscribe(tickers)
        
        # Add callback for orderbook updates
        orderbook_service.add_callback(self._on_orderbook_update)
        
        while not self._stop_event.is_set():
            try:
                if self._state == StrategyState.RUNNING:
                    self._quote_cycle()
                
                # Update stats
                if self._stats.start_time:
                    self._stats.uptime_seconds = (
                        datetime.now(timezone.utc) - self._stats.start_time
                    ).total_seconds()
                
                # Sleep between cycles
                self._stop_event.wait(timeout=app_config.strategy.quote_refresh_interval)
                
            except Exception as e:
                logger.error(f"Strategy loop error: {e}", exc_info=True)
                time.sleep(1)
    
    def _quote_cycle(self):
        """Execute one quote cycle for all markets."""
        # Check risk status
        if risk_manager.is_halted:
            logger.debug("Trading halted, skipping quote cycle")
            return
        
        # Update fair values
        self._update_fair_values()
        
        # Quote each market
        with self._lock:
            markets_to_quote = list(self._markets.values())
        
        for market in markets_to_quote:
            if not market.is_active:
                continue
            
            try:
                self._quote_market(market)
            except Exception as e:
                logger.error(f"Error quoting {market.ticker}: {e}")
    
    def _update_fair_values(self):
        """Update fair values for all markets."""
        with self._lock:
            markets_list = [
                {'ticker': m.ticker, 'title': m.title}
                for m in self._markets.values()
            ]
        
        if not app_config.strategy.use_weather_fair_value:
            return
        
        fair_values = fair_value_calculator.calculate_all_fair_values(markets_list)
        
        with self._lock:
            for ticker, fv in fair_values.items():
                if ticker in self._markets:
                    self._markets[ticker].fair_value = fv
    
    def _quote_market(self, market: MarketState):
        """Generate and send quotes for a single market."""
        # Check time-based exit
        if market.close_time:
            hours_to_close = (
                market.close_time - datetime.now(timezone.utc)
            ).total_seconds() / 3600
            
            if risk_manager.should_exit_market(market.ticker, hours_to_close):
                logger.info(f"Exiting {market.ticker} - too close to settlement")
                self._cancel_market_quotes(market)
                market.is_active = False
                return
        
        # Get current orderbook
        orderbook = orderbook_service.get_orderbook(market.ticker)
        if not orderbook:
            # Fall back to REST API
            ob_data = kalshi_service.get_orderbook(market.ticker)
            if not ob_data:
                return
        
        # Calculate quote prices
        quote = self._calculate_quote(market, orderbook)
        if not quote:
            return
        
        # Check risk before placing orders
        can_bid, bid_reason = risk_manager.can_place_order(
            market.ticker, 'yes', 'buy', quote.bid_size
        )
        can_ask, ask_reason = risk_manager.can_place_order(
            market.ticker, 'yes', 'sell', quote.ask_size
        )
        
        # Cancel existing orders if prices changed
        if market.current_quote:
            if (market.current_quote.bid_price != quote.bid_price or
                market.current_quote.ask_price != quote.ask_price):
                self._cancel_market_quotes(market)
        
        # Place new orders
        if can_bid and not market.bid_order_id:
            result = kalshi_service.create_order(
                ticker=market.ticker,
                action='buy',
                side='yes',
                count=quote.bid_size,
                order_type='limit',
                price=quote.bid_price,
            )
            if result.success:
                market.bid_order_id = result.order_id
                self._stats.total_quotes += 1
        
        if can_ask and not market.ask_order_id:
            result = kalshi_service.create_order(
                ticker=market.ticker,
                action='sell',
                side='yes',
                count=quote.ask_size,
                order_type='limit',
                price=quote.ask_price,
            )
            if result.success:
                market.ask_order_id = result.order_id
                self._stats.total_quotes += 1
        
        market.current_quote = quote
        market.last_quote_time = datetime.now(timezone.utc)
    
    def _calculate_quote(
        self,
        market: MarketState,
        orderbook: Optional[Orderbook]
    ) -> Optional[Quote]:
        """
        Calculate bid and ask prices for a market.
        
        Strategy:
        1. Start with fair value (from weather) or mid price
        2. Apply half-spread on each side
        3. Adjust for inventory skew
        4. Ensure prices are within 1-99 range
        """
        # Determine base price (fair value or orderbook mid)
        if market.fair_value and market.fair_value.confidence >= app_config.strategy.fair_value_confidence_threshold:
            base_price = market.fair_value.fair_value
        elif orderbook and orderbook.mid:
            base_price = orderbook.mid
        else:
            # Default to 50 if no information
            base_price = 50
        
        # Get half spread
        half_spread = app_config.strategy.default_spread
        
        # Get inventory skew
        skew = risk_manager.get_inventory_skew(market.ticker)
        
        # Calculate prices
        # Skew > 0 means we're long, so bid lower and ask lower to reduce position
        bid_price = int(round(base_price - half_spread - skew))
        ask_price = int(round(base_price + half_spread - skew))
        
        # Ensure minimum spread
        if ask_price - bid_price < app_config.strategy.min_spread:
            # Widen around midpoint
            mid = (bid_price + ask_price) / 2
            half_min = app_config.strategy.min_spread / 2
            bid_price = int(mid - half_min)
            ask_price = int(mid + half_min)
        
        # Clamp to valid range
        bid_price = max(1, min(98, bid_price))
        ask_price = max(2, min(99, ask_price))
        
        # Ensure ask > bid
        if ask_price <= bid_price:
            ask_price = bid_price + 1
        
        return Quote(
            ticker=market.ticker,
            bid_price=bid_price,
            bid_size=app_config.risk.default_order_size,
            ask_price=ask_price,
            ask_size=app_config.risk.default_order_size,
            fair_value=base_price,
        )
    
    def _cancel_market_quotes(self, market: MarketState):
        """Cancel all quotes for a market."""
        if market.bid_order_id:
            kalshi_service.cancel_order(market.bid_order_id)
            market.bid_order_id = None
        
        if market.ask_order_id:
            kalshi_service.cancel_order(market.ask_order_id)
            market.ask_order_id = None
    
    def _cancel_all_quotes(self):
        """Cancel all outstanding quotes."""
        with self._lock:
            for market in self._markets.values():
                self._cancel_market_quotes(market)
    
    def _on_orderbook_update(self, ticker: str, orderbook: Orderbook):
        """Callback when orderbook updates (from WebSocket)."""
        # Could trigger immediate requote here if configured
        pass
    
    def _on_fill(self, ticker: str, side: str, action: str, count: int, price: int):
        """Handle a fill notification."""
        logger.info(f"Fill: {ticker} {action} {count} {side} @ {price}¢")
        
        # Update risk manager
        risk_manager.record_fill(ticker, side, action, count, price)
        
        # Update stats
        self._stats.total_fills += 1
        self._stats.total_volume += count
        
        # Update market state
        with self._lock:
            if ticker in self._markets:
                self._markets[ticker].fills_count += 1
        
        # Requote if configured
        if app_config.strategy.requote_on_fill:
            with self._lock:
                if ticker in self._markets:
                    market = self._markets[ticker]
                    # Clear order IDs to force new quotes
                    if action == 'buy':
                        market.bid_order_id = None
                    else:
                        market.ask_order_id = None
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def get_market_states(self) -> Dict[str, MarketState]:
        """Get current state of all markets."""
        with self._lock:
            return {k: v for k, v in self._markets.items()}
    
    def get_stats(self) -> StrategyStats:
        """Get strategy statistics."""
        return StrategyStats(
            total_quotes=self._stats.total_quotes,
            total_fills=self._stats.total_fills,
            total_volume=self._stats.total_volume,
            start_time=self._stats.start_time,
            uptime_seconds=self._stats.uptime_seconds,
        )
    
    def set_market_active(self, ticker: str, active: bool):
        """Enable or disable quoting for a specific market."""
        with self._lock:
            if ticker in self._markets:
                self._markets[ticker].is_active = active
                if not active:
                    self._cancel_market_quotes(self._markets[ticker])
    
    def refresh_markets(self):
        """Refresh the list of target markets."""
        self.initialize()


# Global instance
market_maker = MarketMaker()
