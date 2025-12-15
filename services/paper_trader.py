import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Any, Dict, List, Optional, Tuple

from config import config as app_config
from services.kalshi_client import kalshi_service
from services.orderbook import orderbook_service, Orderbook
from services.public_trades import public_trades_service, TradePrint

logger = logging.getLogger(__name__)


@dataclass
class SimOrder:
    order_id: str
    side: str
    yes_price: int
    qty_total: int
    qty_remaining: int
    queue_ahead: int
    created_ts: float
    updated_ts: float


@dataclass
class SimFill:
    ts: float
    ticker: str
    side: str
    yes_price: int
    qty: int


@dataclass
class SimSeriesPoint:
    ts: float
    realized_pnl_cents: float
    unrealized_pnl_cents: float
    equity_cents: float
    inventory: int
    best_bid: Optional[int]
    best_ask: Optional[int]
    mid: Optional[float]
    spread: Optional[int]


@dataclass
class SimStats:
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    ticker: Optional[str] = None
    is_running: bool = False
    duration_seconds: int = 0

    order_size: int = 1
    min_spread: int = 5
    min_profit: int = 1

    quotes_placed: int = 0
    quotes_replaced: int = 0
    fills: int = 0
    volume: int = 0

    round_trips: int = 0
    wins: int = 0

    realized_pnl_cents: float = 0.0


class PaperTrader:
    def __init__(self):
        self._lock = Lock()
        self._thread: Optional[Thread] = None
        self._stop_event = Event()

        self._stats = SimStats()
        self._timeseries: List[SimSeriesPoint] = []
        self._fills: List[SimFill] = []

        self._ticker: Optional[str] = None
        self._latest_ob: Optional[Orderbook] = None

        self._open_buy: Optional[SimOrder] = None
        self._open_sell: Optional[SimOrder] = None

        self._inventory: int = 0
        self._avg_entry_price: float = 0.0

        self._cycle_entry_ts: Optional[float] = None
        self._cycle_entry_realized_pnl_cents: float = 0.0
        self._total_hold_seconds: float = 0.0
        self._total_cycle_pnl_cents: float = 0.0

        self._eq_peak: float = 0.0
        self._max_drawdown_cents: float = 0.0

        orderbook_service.add_callback(self._on_orderbook)
        public_trades_service.add_callback(self._on_trade)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._stats.is_running

    def start(
        self,
        duration_seconds: int = 1800,
        order_size: int = 10,
        min_spread: Optional[int] = None,
        min_profit: int = 1,
        ticker: Optional[str] = None,
    ):
        with self._lock:
            if self._stats.is_running:
                return

            self._reset_state_locked()
            self._stats.is_running = True
            self._stats.start_time = datetime.now(timezone.utc)
            self._stats.duration_seconds = int(duration_seconds)
            self._stats.order_size = int(order_size)
            self._stats.min_spread = int(min_spread) if min_spread is not None else int(app_config.strategy.min_spread)
            self._stats.min_profit = int(min_profit)

            self._ticker = str(ticker) if ticker else self._select_market_locked()
            self._stats.ticker = self._ticker

            if not self._ticker:
                self._stats.is_running = False
                return

            orderbook_service.subscribe([self._ticker])
            public_trades_service.subscribe([self._ticker])

            self._stop_event.clear()
            self._thread = Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        with self._lock:
            self._stats.is_running = False
            self._stats.end_time = datetime.now(timezone.utc)
            self._open_buy = None
            self._open_sell = None

        if self._thread:
            self._thread.join(timeout=5)

    def reset(self):
        self.stop()
        with self._lock:
            self._reset_state_locked()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            now = datetime.now(timezone.utc)
            uptime = 0.0
            if self._stats.start_time:
                uptime = (now - self._stats.start_time).total_seconds()

            best_bid, best_ask, mid, spread = self._best_prices_locked()
            unreal = self._compute_unrealized_locked(mid)
            equity = self._stats.realized_pnl_cents + unreal

            return {
                'is_running': self._stats.is_running,
                'ticker': self._stats.ticker,
                'uptime_seconds': uptime,
                'duration_seconds': self._stats.duration_seconds,
                'order_size': self._stats.order_size,
                'min_spread': self._stats.min_spread,
                'min_profit': self._stats.min_profit,
                'inventory': self._inventory,
                'avg_entry_price': self._avg_entry_price,
                'best_bid': best_bid,
                'best_ask': best_ask,
                'mid': mid,
                'spread': spread,
                'quotes_placed': self._stats.quotes_placed,
                'quotes_replaced': self._stats.quotes_replaced,
                'fills': self._stats.fills,
                'volume': self._stats.volume,
                'round_trips': self._stats.round_trips,
                'wins': self._stats.wins,
                'win_rate': (self._stats.wins / self._stats.round_trips) if self._stats.round_trips else None,
                'avg_hold_seconds': (self._total_hold_seconds / self._stats.round_trips) if self._stats.round_trips else None,
                'avg_cycle_pnl_cents': (self._total_cycle_pnl_cents / self._stats.round_trips) if self._stats.round_trips else None,
                'realized_pnl_cents': self._stats.realized_pnl_cents,
                'unrealized_pnl_cents': unreal,
                'equity_cents': equity,
                'max_drawdown_cents': self._max_drawdown_cents,
                'open_buy': self._order_to_dict_locked(self._open_buy),
                'open_sell': self._order_to_dict_locked(self._open_sell),
            }

    def get_timeseries(self, limit: int = 2000) -> List[Dict[str, Any]]:
        with self._lock:
            pts = self._timeseries[-limit:]
            return [
                {
                    'ts': p.ts,
                    'realized_pnl_cents': p.realized_pnl_cents,
                    'unrealized_pnl_cents': p.unrealized_pnl_cents,
                    'equity_cents': p.equity_cents,
                    'inventory': p.inventory,
                    'best_bid': p.best_bid,
                    'best_ask': p.best_ask,
                    'mid': p.mid,
                    'spread': p.spread,
                }
                for p in pts
            ]

    def get_fills(self, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            fs = self._fills[-limit:]
            return [
                {
                    'ts': f.ts,
                    'ticker': f.ticker,
                    'side': f.side,
                    'yes_price': f.yes_price,
                    'qty': f.qty,
                }
                for f in fs
            ]

    def _order_to_dict_locked(self, o: Optional[SimOrder]) -> Optional[Dict[str, Any]]:
        if not o:
            return None
        return {
            'order_id': o.order_id,
            'side': o.side,
            'yes_price': o.yes_price,
            'qty_total': o.qty_total,
            'qty_remaining': o.qty_remaining,
            'queue_ahead': o.queue_ahead,
            'created_ts': o.created_ts,
            'updated_ts': o.updated_ts,
        }

    def _reset_state_locked(self):
        self._timeseries = []
        self._fills = []
        self._ticker = None
        self._latest_ob = None
        self._open_buy = None
        self._open_sell = None
        self._inventory = 0
        self._avg_entry_price = 0.0

        self._cycle_entry_ts = None
        self._cycle_entry_realized_pnl_cents = 0.0
        self._total_hold_seconds = 0.0
        self._total_cycle_pnl_cents = 0.0
        self._eq_peak = 0.0
        self._max_drawdown_cents = 0.0
        self._stats = SimStats()

    def _select_market_locked(self) -> Optional[str]:
        series_candidates: List[str] = []
        if isinstance(app_config.strategy.target_series, list):
            series_candidates.extend(app_config.strategy.target_series)
        elif isinstance(app_config.strategy.target_series, str):
            series_candidates.append(app_config.strategy.target_series)

        extra = app_config.__dict__.get('sim_series', None)
        if isinstance(extra, list):
            series_candidates.extend(extra)

        markets_by_ticker: Dict[str, Dict[str, Any]] = {}
        for series in series_candidates:
            try:
                for m in kalshi_service.get_markets(series_ticker=series, status='open'):
                    t = m.get('ticker')
                    if t:
                        markets_by_ticker[str(t)] = m
            except Exception:
                continue

        markets: List[Dict[str, Any]] = list(markets_by_ticker.values())
        if not markets:
            try:
                from services.market_maker import market_maker

                ms = market_maker.get_market_states()
                for t, st in ms.items():
                    markets.append({'ticker': t, 'title': st.title, 'volume_24h': 0, 'volume': 0})
            except Exception:
                return None

        def vol_key(m: Dict[str, Any]) -> int:
            v24 = m.get('volume_24h')
            v = m.get('volume')
            try:
                return int(v24 if v24 is not None else (v if v is not None else 0))
            except Exception:
                return 0

        markets = sorted(markets, key=vol_key, reverse=True)[:200]

        keywords = [
            'weather', 'temperature', 'temp', 'high', 'low', 'rain', 'snow', 'wind',
            'nfl', 'nba', 'mlb', 'nhl', 'soccer', 'ufc', 'tennis', 'golf',
            'election', 'president', 'senate', 'house', 'governor', 'primary',
            'trump', 'biden', 'harris',
        ]
        filtered = []
        for m in markets:
            title = str(m.get('title') or '').lower()
            if any(k in title for k in keywords):
                filtered.append(m)

        if filtered:
            markets = filtered[:50]
        else:
            markets = markets[:50]

        best_ticker: Optional[str] = None
        best_score: float = -1.0

        for m in markets:
            t = m.get('ticker')
            if not t:
                continue

            ob = kalshi_service.get_orderbook(t)
            if not ob:
                continue

            yes_bids = ob.get('yes', [])
            no_bids = ob.get('no', [])

            best_yes_bid = max((lvl[0] for lvl in yes_bids), default=None)
            best_yes_ask = (100 - max((lvl[0] for lvl in no_bids), default=None)) if no_bids else None
            if best_yes_bid is None or best_yes_ask is None:
                continue

            spread = best_yes_ask - best_yes_bid
            if spread <= 0:
                continue

            depth_bid = 0
            if best_yes_bid is not None:
                depth_bid = sum(int(lvl[1]) for lvl in yes_bids if lvl[0] == best_yes_bid)

            depth_ask = 0
            if best_yes_ask is not None:
                no_price = 100 - best_yes_ask
                depth_ask = sum(int(lvl[1]) for lvl in no_bids if lvl[0] == no_price)

            volume = vol_key(m)
            score = float(volume) + 0.25 * float(depth_bid + depth_ask) + 5.0 * float(spread)

            if score > best_score:
                best_score = score
                best_ticker = str(t)

        return best_ticker

    def _best_prices_locked(self) -> Tuple[Optional[int], Optional[int], Optional[float], Optional[int]]:
        if not self._latest_ob:
            return None, None, None, None
        return self._latest_ob.best_yes_bid, self._latest_ob.best_yes_ask, self._latest_ob.mid, self._latest_ob.spread

    def _compute_unrealized_locked(self, mid: Optional[float]) -> float:
        if self._inventory == 0 or mid is None:
            return 0.0
        return float((mid - self._avg_entry_price) * self._inventory)

    def _place_or_replace_buy_locked(self, yes_price: int):
        now = time.time()
        if self._open_buy and self._open_buy.yes_price == yes_price and self._open_buy.qty_remaining > 0:
            return

        ob = self._latest_ob
        queue_ahead = 0
        if ob:
            queue_ahead = int(ob.yes_bids.get(yes_price, 0))

        oid = f"sim-buy-{int(now*1000)}"
        if self._open_buy:
            self._stats.quotes_replaced += 1
        else:
            self._stats.quotes_placed += 1

        self._open_buy = SimOrder(
            order_id=oid,
            side='buy_yes',
            yes_price=int(yes_price),
            qty_total=int(self._stats.order_size),
            qty_remaining=int(self._stats.order_size),
            queue_ahead=queue_ahead,
            created_ts=now,
            updated_ts=now,
        )

    def _place_or_replace_sell_locked(self, yes_price: int, qty: int):
        now = time.time()
        if self._open_sell and self._open_sell.yes_price == yes_price and self._open_sell.qty_remaining == qty and self._open_sell.qty_remaining > 0:
            return

        ob = self._latest_ob
        queue_ahead = 0
        if ob:
            no_price = 100 - yes_price
            queue_ahead = int(ob.no_bids.get(no_price, 0))

        oid = f"sim-sell-{int(now*1000)}"
        if self._open_sell:
            self._stats.quotes_replaced += 1
        else:
            self._stats.quotes_placed += 1

        self._open_sell = SimOrder(
            order_id=oid,
            side='sell_yes',
            yes_price=int(yes_price),
            qty_total=int(qty),
            qty_remaining=int(qty),
            queue_ahead=queue_ahead,
            created_ts=now,
            updated_ts=now,
        )

    def _run_loop(self):
        start = time.time()
        while not self._stop_event.is_set():
            with self._lock:
                if not self._stats.is_running:
                    break

                if self._stats.duration_seconds and (time.time() - start) >= self._stats.duration_seconds:
                    self._stats.is_running = False
                    self._stats.end_time = datetime.now(timezone.utc)
                    self._open_buy = None
                    self._open_sell = None
                    break

                if self._ticker is None:
                    self._stats.is_running = False
                    break

                best_bid, best_ask, mid, spread = self._best_prices_locked()

                if self._inventory == 0:
                    self._open_sell = None
                    if spread is not None and spread >= self._stats.min_spread and best_bid is not None:
                        bid_price = min(98, best_bid + 1)
                        self._place_or_replace_buy_locked(bid_price)
                    else:
                        self._open_buy = None
                else:
                    self._open_buy = None
                    if best_ask is not None:
                        target = max(int(self._avg_entry_price) + self._stats.min_profit, best_ask - 1)
                        target = max(2, min(99, target))
                        self._place_or_replace_sell_locked(target, self._inventory)
                    else:
                        self._open_sell = None

                unreal = self._compute_unrealized_locked(mid)
                equity = self._stats.realized_pnl_cents + unreal
                if equity > self._eq_peak:
                    self._eq_peak = equity
                dd = self._eq_peak - equity
                if dd > self._max_drawdown_cents:
                    self._max_drawdown_cents = dd

                self._timeseries.append(
                    SimSeriesPoint(
                        ts=time.time(),
                        realized_pnl_cents=self._stats.realized_pnl_cents,
                        unrealized_pnl_cents=unreal,
                        equity_cents=equity,
                        inventory=self._inventory,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        mid=mid,
                        spread=spread,
                    )
                )

            time.sleep(1.0)

    def _on_orderbook(self, ticker: str, orderbook: Orderbook):
        with self._lock:
            if self._ticker and ticker != self._ticker:
                return
            self._latest_ob = orderbook

    def _on_trade(self, tp: TradePrint):
        with self._lock:
            if not self._stats.is_running:
                return
            if not self._ticker or tp.market_ticker != self._ticker:
                return

            if self._open_buy and self._open_buy.qty_remaining > 0:
                if tp.taker_side == 'no' and tp.yes_price == self._open_buy.yes_price:
                    self._consume_queue_and_fill_locked(self._open_buy, tp.count, tp.ts)

            if self._open_sell and self._open_sell.qty_remaining > 0:
                if tp.taker_side == 'yes' and tp.yes_price == self._open_sell.yes_price:
                    self._consume_queue_and_fill_locked(self._open_sell, tp.count, tp.ts)

    def _consume_queue_and_fill_locked(self, o: SimOrder, traded_count: int, trade_ts: float):
        if traded_count <= 0 or o.qty_remaining <= 0:
            return

        o.queue_ahead -= int(traded_count)
        if o.queue_ahead >= 0:
            o.updated_ts = time.time()
            return

        fill_qty = min(o.qty_remaining, -o.queue_ahead)
        if fill_qty <= 0:
            o.updated_ts = time.time()
            return

        o.qty_remaining -= int(fill_qty)
        o.queue_ahead = 0
        o.updated_ts = time.time()

        self._stats.fills += 1
        self._stats.volume += int(fill_qty)

        self._fills.append(
            SimFill(
                ts=float(trade_ts),
                ticker=self._ticker or '',
                side=o.side,
                yes_price=o.yes_price,
                qty=int(fill_qty),
            )
        )

        if o.side == 'buy_yes':
            was_flat = self._inventory == 0
            total_cost = self._avg_entry_price * self._inventory
            total_cost += float(o.yes_price) * int(fill_qty)
            self._inventory += int(fill_qty)
            if self._inventory > 0:
                self._avg_entry_price = total_cost / self._inventory

            if was_flat and self._inventory > 0:
                self._cycle_entry_ts = float(trade_ts)
                self._cycle_entry_realized_pnl_cents = float(self._stats.realized_pnl_cents)
        else:
            if self._inventory <= 0:
                return
            sell_qty = min(self._inventory, int(fill_qty))
            entry = self._avg_entry_price
            pnl = float((o.yes_price - entry) * sell_qty)
            self._stats.realized_pnl_cents += pnl

            self._inventory -= sell_qty
            if self._inventory == 0:
                self._avg_entry_price = 0.0

                if self._cycle_entry_ts is not None:
                    hold = float(trade_ts) - float(self._cycle_entry_ts)
                    self._total_hold_seconds += max(0.0, hold)
                    cycle_pnl = float(self._stats.realized_pnl_cents) - float(self._cycle_entry_realized_pnl_cents)
                    self._total_cycle_pnl_cents += cycle_pnl
                    self._stats.round_trips += 1
                    if cycle_pnl > 0:
                        self._stats.wins += 1
                self._cycle_entry_ts = None
                self._cycle_entry_realized_pnl_cents = float(self._stats.realized_pnl_cents)


paper_trader = PaperTrader()
