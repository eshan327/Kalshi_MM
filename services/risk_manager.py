"""
Risk Manager Service

Handles position limits, inventory skewing, P&L tracking, and safety controls.
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from config import config as app_config
from services.kalshi_client import kalshi_service, Position

logger = logging.getLogger(__name__)


@dataclass
class MarketRisk:
    """Risk metrics for a single market."""
    ticker: str
    position: int = 0  # Positive = long YES, negative = long NO
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    open_buy_orders: int = 0
    open_sell_orders: int = 0
    
    @property
    def net_exposure(self) -> int:
        """Net exposure including open orders."""
        return self.position + self.open_buy_orders - self.open_sell_orders
    
    @property
    def total_pnl(self) -> float:
        """Total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl


@dataclass
class RiskState:
    """Global risk state."""
    total_position: int = 0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    markets: Dict[str, MarketRisk] = field(default_factory=dict)
    is_halted: bool = False
    halt_reason: Optional[str] = None
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskManager:
    """
    Manages trading risk including position limits, inventory skewing,
    and emergency controls.
    """
    
    def __init__(self):
        self._state = RiskState()
        self._lock = Lock()
        self._daily_start_balance: Optional[float] = None
    
    def initialize(self):
        """Initialize risk manager with current positions."""
        # Get current balance as starting point for daily P&L
        balance = kalshi_service.get_balance()
        if balance is not None:
            self._daily_start_balance = balance
        
        # Load current positions
        self.sync_positions()
        logger.info("RiskManager initialized")
    
    def sync_positions(self):
        """Sync positions from Kalshi API."""
        positions = kalshi_service.get_positions()
        
        with self._lock:
            # Reset position counts
            for mr in self._state.markets.values():
                mr.position = 0
            
            total_pos = 0
            for pos in positions:
                if pos.ticker not in self._state.markets:
                    self._state.markets[pos.ticker] = MarketRisk(ticker=pos.ticker)
                
                mr = self._state.markets[pos.ticker]
                mr.position = pos.position
                mr.avg_entry_price = pos.average_price
                mr.realized_pnl = pos.realized_pnl
                
                total_pos += abs(pos.position)
            
            self._state.total_position = total_pos
            self._state.last_update = datetime.now(timezone.utc)
        
        logger.info(f"Synced {len(positions)} positions, total={total_pos}")
    
    def update_daily_pnl(self):
        """Update daily P&L from current balance."""
        if self._daily_start_balance is None:
            return
        
        current_balance = kalshi_service.get_balance()
        if current_balance is not None:
            with self._lock:
                self._state.daily_pnl = current_balance - self._daily_start_balance
    
    # =========================================================================
    # Risk Checks
    # =========================================================================
    
    def can_place_order(
        self,
        ticker: str,
        side: str,  # 'yes' or 'no'
        action: str,  # 'buy' or 'sell'
        count: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if an order can be placed given risk limits.
        
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        with self._lock:
            # Check if trading is halted
            if self._state.is_halted:
                return False, f"Trading halted: {self._state.halt_reason}"
            
            # Check daily loss limit
            if self._state.daily_pnl < -app_config.risk.max_daily_loss:
                return False, f"Daily loss limit exceeded: ${-self._state.daily_pnl:.2f}"
            
            # Calculate position impact
            # Buying YES or selling NO increases YES exposure
            # Selling YES or buying NO decreases YES exposure
            if (action == 'buy' and side == 'yes') or (action == 'sell' and side == 'no'):
                position_delta = count
            else:
                position_delta = -count
            
            # Get current market risk
            mr = self._state.markets.get(ticker)
            current_pos = mr.position if mr else 0
            new_pos = current_pos + position_delta
            
            # Check per-market position limit
            if abs(new_pos) > app_config.risk.max_position_per_market:
                return False, f"Market position limit: {abs(new_pos)} > {app_config.risk.max_position_per_market}"
            
            # Check total position limit
            # Calculate new total (remove old, add new)
            new_total = self._state.total_position - abs(current_pos) + abs(new_pos)
            if new_total > app_config.risk.max_total_position:
                return False, f"Total position limit: {new_total} > {app_config.risk.max_total_position}"
            
            # Check order size
            if count > app_config.risk.max_order_size:
                return False, f"Order size limit: {count} > {app_config.risk.max_order_size}"
            
            return True, None
    
    def get_inventory_skew(self, ticker: str) -> int:
        """
        Calculate price skew based on inventory.
        
        Positive skew = bid lower (we're long, want to reduce)
        Negative skew = bid higher (we're short, want to reduce)
        
        Returns:
            Skew amount in cents to subtract from bid / add to ask
        """
        with self._lock:
            mr = self._state.markets.get(ticker)
            if not mr:
                return 0
            
            position = mr.position
            
            # Calculate skew
            skew = int(position * app_config.risk.inventory_skew_factor)
            
            # Cap the skew
            max_skew = app_config.risk.max_inventory_skew
            skew = max(-max_skew, min(max_skew, skew))
            
            return skew
    
    def should_exit_market(self, ticker: str, hours_to_settlement: float) -> bool:
        """Check if we should exit a market due to time-based risk."""
        return hours_to_settlement < app_config.risk.hours_before_settlement_exit
    
    # =========================================================================
    # Position Updates
    # =========================================================================
    
    def record_fill(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        price: float
    ):
        """Record a fill and update risk state."""
        with self._lock:
            if ticker not in self._state.markets:
                self._state.markets[ticker] = MarketRisk(ticker=ticker)
            
            mr = self._state.markets[ticker]
            
            # Calculate position change
            if (action == 'buy' and side == 'yes') or (action == 'sell' and side == 'no'):
                position_delta = count
            else:
                position_delta = -count
            
            # Update position
            old_pos = mr.position
            mr.position += position_delta
            
            # Update total position
            self._state.total_position = sum(
                abs(m.position) for m in self._state.markets.values()
            )
            
            logger.info(
                f"Fill recorded: {ticker} {action} {count} {side} @ {price}¢ "
                f"(pos: {old_pos} -> {mr.position})"
            )
    
    def update_open_orders(self, ticker: str, buy_count: int, sell_count: int):
        """Update open order counts for a market."""
        with self._lock:
            if ticker not in self._state.markets:
                self._state.markets[ticker] = MarketRisk(ticker=ticker)
            
            mr = self._state.markets[ticker]
            mr.open_buy_orders = buy_count
            mr.open_sell_orders = sell_count
    
    # =========================================================================
    # Emergency Controls
    # =========================================================================
    
    def halt_trading(self, reason: str):
        """Halt all trading."""
        with self._lock:
            self._state.is_halted = True
            self._state.halt_reason = reason
        logger.warning(f"Trading HALTED: {reason}")
    
    def resume_trading(self):
        """Resume trading."""
        with self._lock:
            self._state.is_halted = False
            self._state.halt_reason = None
        logger.info("Trading RESUMED")
    
    def trigger_kill_switch(self) -> bool:
        """
        Emergency kill switch - cancel all orders and halt.
        
        Returns:
            True if successful
        """
        self.halt_trading("Kill switch activated")
        
        # Cancel all orders
        result = kalshi_service.cancel_all_orders()
        
        if result.success:
            logger.info("Kill switch: All orders cancelled")
            return True
        else:
            logger.error(f"Kill switch: Failed to cancel orders - {result.error}")
            return False
    
    # =========================================================================
    # State Access
    # =========================================================================
    
    def get_state(self) -> RiskState:
        """Get a copy of the current risk state."""
        with self._lock:
            # Create a copy
            state_copy = RiskState(
                total_position=self._state.total_position,
                total_realized_pnl=self._state.total_realized_pnl,
                total_unrealized_pnl=self._state.total_unrealized_pnl,
                daily_pnl=self._state.daily_pnl,
                is_halted=self._state.is_halted,
                halt_reason=self._state.halt_reason,
                last_update=self._state.last_update,
            )
            # Deep copy markets
            state_copy.markets = {
                k: MarketRisk(
                    ticker=v.ticker,
                    position=v.position,
                    avg_entry_price=v.avg_entry_price,
                    realized_pnl=v.realized_pnl,
                    unrealized_pnl=v.unrealized_pnl,
                    open_buy_orders=v.open_buy_orders,
                    open_sell_orders=v.open_sell_orders,
                )
                for k, v in self._state.markets.items()
            }
            return state_copy
    
    def get_market_risk(self, ticker: str) -> Optional[MarketRisk]:
        """Get risk metrics for a specific market."""
        with self._lock:
            mr = self._state.markets.get(ticker)
            if mr:
                return MarketRisk(
                    ticker=mr.ticker,
                    position=mr.position,
                    avg_entry_price=mr.avg_entry_price,
                    realized_pnl=mr.realized_pnl,
                    unrealized_pnl=mr.unrealized_pnl,
                    open_buy_orders=mr.open_buy_orders,
                    open_sell_orders=mr.open_sell_orders,
                )
            return None
    
    @property
    def is_halted(self) -> bool:
        with self._lock:
            return self._state.is_halted


# Global instance
risk_manager = RiskManager()
