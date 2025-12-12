"""
API Routes

REST API endpoints for the market maker dashboard.
"""
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone

from services.kalshi_client import kalshi_service
from services.risk_manager import risk_manager
from services.market_maker import market_maker, StrategyState
from services.orderbook import orderbook_service
from services.fair_value import fair_value_calculator
from config import config as app_config

api_bp = Blueprint('api', __name__)


# =============================================================================
# Account Endpoints
# =============================================================================

@api_bp.route('/account/balance')
def get_balance():
    """Get current account balance."""
    balance = kalshi_service.get_balance()
    if balance is None:
        return jsonify({'error': 'Failed to get balance'}), 500
    return jsonify({'balance': balance})


@api_bp.route('/account/positions')
def get_positions():
    """Get current positions."""
    positions = kalshi_service.get_positions()
    return jsonify({
        'positions': [
            {
                'ticker': p.ticker,
                'title': p.market_title,
                'position': p.position,
                'avg_price': p.average_price,
                'realized_pnl': p.realized_pnl,
            }
            for p in positions
        ]
    })


@api_bp.route('/account/orders')
def get_orders():
    """Get current orders."""
    status = request.args.get('status', 'resting')
    orders = kalshi_service.get_orders(status=status)
    return jsonify({'orders': orders})


@api_bp.route('/account/fills')
def get_fills():
    """Get recent fills."""
    limit = request.args.get('limit', 50, type=int)
    fills = kalshi_service.get_fills(limit=limit)
    return jsonify({'fills': fills})


# =============================================================================
# Market Data Endpoints
# =============================================================================

@api_bp.route('/markets')
def get_markets():
    """Get markets for the target series."""
    series = request.args.get('series', app_config.strategy.target_series)
    markets = kalshi_service.get_markets(series_ticker=series, status='open')
    return jsonify({'markets': markets})


@api_bp.route('/markets/<ticker>/orderbook')
def get_orderbook(ticker: str):
    """Get orderbook for a market."""
    # Try WebSocket cache first
    orderbook = orderbook_service.get_orderbook(ticker)
    if orderbook:
        return jsonify({
            'ticker': ticker,
            'best_bid': orderbook.best_yes_bid,
            'best_ask': orderbook.best_yes_ask,
            'spread': orderbook.spread,
            'mid': orderbook.mid,
            'yes_bids': [{'price': l.price, 'qty': l.quantity} for l in orderbook.get_yes_bids_sorted()[:10]],
            'no_bids': [{'price': l.price, 'qty': l.quantity} for l in orderbook.get_no_bids_sorted()[:10]],
            'last_update': orderbook.last_update,
        })
    
    # Fall back to REST API
    metrics = kalshi_service.get_market_metrics(ticker)
    return jsonify({
        'ticker': ticker,
        'best_bid': metrics['bid'],
        'best_ask': metrics['ask'],
        'spread': metrics['spread'],
        'mid': metrics['mid'],
    })


@api_bp.route('/markets/<ticker>/fair-value')
def get_fair_value(ticker: str):
    """Get fair value for a market."""
    fv = fair_value_calculator.calculate_fair_value(ticker)
    if fv:
        return jsonify({
            'ticker': fv.ticker,
            'fair_value': fv.fair_value,
            'confidence': fv.confidence,
            'forecast_temp': fv.forecast_temp,
            'threshold_temp': fv.threshold_temp,
            'market_type': fv.market_type,
            'reasoning': fv.reasoning,
        })
    return jsonify({'error': 'Could not calculate fair value'}), 404


# =============================================================================
# Strategy Control Endpoints
# =============================================================================

@api_bp.route('/strategy/status')
def get_strategy_status():
    """Get current strategy status."""
    stats = market_maker.get_stats()
    risk_state = risk_manager.get_state()
    
    return jsonify({
        'state': market_maker.state.value,
        'is_running': market_maker.is_running,
        'stats': {
            'total_quotes': stats.total_quotes,
            'total_fills': stats.total_fills,
            'total_volume': stats.total_volume,
            'uptime_seconds': stats.uptime_seconds,
            'start_time': stats.start_time.isoformat() if stats.start_time else None,
        },
        'risk': {
            'is_halted': risk_state.is_halted,
            'halt_reason': risk_state.halt_reason,
            'total_position': risk_state.total_position,
            'daily_pnl': risk_state.daily_pnl,
        },
        'websocket_connected': orderbook_service.is_connected,
    })


@api_bp.route('/strategy/start', methods=['POST'])
def start_strategy():
    """Start the market making strategy."""
    if market_maker.state != StrategyState.STOPPED:
        return jsonify({'error': f'Cannot start from state {market_maker.state.value}'}), 400
    
    # Initialize if needed
    if not market_maker.initialize():
        return jsonify({'error': 'Failed to initialize strategy'}), 500
    
    market_maker.start()
    return jsonify({'status': 'started'})


@api_bp.route('/strategy/stop', methods=['POST'])
def stop_strategy():
    """Stop the market making strategy."""
    market_maker.stop()
    return jsonify({'status': 'stopped'})


@api_bp.route('/strategy/pause', methods=['POST'])
def pause_strategy():
    """Pause the market making strategy."""
    market_maker.pause()
    return jsonify({'status': 'paused'})


@api_bp.route('/strategy/resume', methods=['POST'])
def resume_strategy():
    """Resume the market making strategy."""
    market_maker.resume()
    return jsonify({'status': 'resumed'})


@api_bp.route('/strategy/markets')
def get_strategy_markets():
    """Get current market states from the strategy."""
    markets = market_maker.get_market_states()
    return jsonify({
        'markets': [
            {
                'ticker': m.ticker,
                'title': m.title,
                'is_active': m.is_active,
                'quote': {
                    'bid': m.current_quote.bid_price if m.current_quote else None,
                    'ask': m.current_quote.ask_price if m.current_quote else None,
                    'fair_value': m.current_quote.fair_value if m.current_quote else None,
                } if m.current_quote else None,
                'fair_value': {
                    'value': m.fair_value.fair_value if m.fair_value else None,
                    'confidence': m.fair_value.confidence if m.fair_value else None,
                    'forecast_temp': m.fair_value.forecast_temp if m.fair_value else None,
                } if m.fair_value else None,
                'fills_count': m.fills_count,
                'last_quote_time': m.last_quote_time.isoformat() if m.last_quote_time else None,
            }
            for m in markets.values()
        ]
    })


@api_bp.route('/strategy/markets/<ticker>/toggle', methods=['POST'])
def toggle_market(ticker: str):
    """Toggle a market on/off."""
    data = request.get_json() or {}
    active = data.get('active', True)
    market_maker.set_market_active(ticker, active)
    return jsonify({'ticker': ticker, 'active': active})


# =============================================================================
# Risk Control Endpoints
# =============================================================================

@api_bp.route('/risk/status')
def get_risk_status():
    """Get detailed risk status."""
    state = risk_manager.get_state()
    return jsonify({
        'is_halted': state.is_halted,
        'halt_reason': state.halt_reason,
        'total_position': state.total_position,
        'total_realized_pnl': state.total_realized_pnl,
        'total_unrealized_pnl': state.total_unrealized_pnl,
        'daily_pnl': state.daily_pnl,
        'last_update': state.last_update.isoformat(),
        'markets': {
            ticker: {
                'position': mr.position,
                'net_exposure': mr.net_exposure,
                'realized_pnl': mr.realized_pnl,
                'unrealized_pnl': mr.unrealized_pnl,
                'open_buy_orders': mr.open_buy_orders,
                'open_sell_orders': mr.open_sell_orders,
            }
            for ticker, mr in state.markets.items()
        }
    })


@api_bp.route('/risk/kill-switch', methods=['POST'])
def kill_switch():
    """Emergency kill switch - cancel all orders and halt trading."""
    success = risk_manager.trigger_kill_switch()
    market_maker.stop()
    
    return jsonify({
        'status': 'activated' if success else 'partial',
        'orders_cancelled': success,
        'strategy_stopped': True,
    })


@api_bp.route('/risk/halt', methods=['POST'])
def halt_trading():
    """Halt trading with a reason."""
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual halt')
    risk_manager.halt_trading(reason)
    return jsonify({'status': 'halted', 'reason': reason})


@api_bp.route('/risk/resume', methods=['POST'])
def resume_trading():
    """Resume trading after halt."""
    risk_manager.resume_trading()
    return jsonify({'status': 'resumed'})


@api_bp.route('/risk/cancel-all', methods=['POST'])
def cancel_all_orders():
    """Cancel all open orders."""
    ticker = request.args.get('ticker')
    result = kalshi_service.cancel_all_orders(ticker=ticker)
    
    if result.success:
        cancelled = result.data.get('cancelled', 0) if result.data else 0
        return jsonify({'status': 'success', 'cancelled': cancelled})
    return jsonify({'status': 'error', 'error': result.error}), 500


# =============================================================================
# Configuration Endpoints
# =============================================================================

@api_bp.route('/config')
def get_config():
    """Get current configuration."""
    return jsonify({
        'kalshi': {
            'use_prod': app_config.kalshi.use_prod,
            'base_url': app_config.kalshi.base_url,
        },
        'risk': {
            'max_position_per_market': app_config.risk.max_position_per_market,
            'max_total_position': app_config.risk.max_total_position,
            'max_daily_loss': app_config.risk.max_daily_loss,
            'inventory_skew_factor': app_config.risk.inventory_skew_factor,
            'max_inventory_skew': app_config.risk.max_inventory_skew,
            'hours_before_settlement_exit': app_config.risk.hours_before_settlement_exit,
            'default_order_size': app_config.risk.default_order_size,
            'max_order_size': app_config.risk.max_order_size,
        },
        'strategy': {
            'target_series': app_config.strategy.target_series,
            'min_spread': app_config.strategy.min_spread,
            'default_spread': app_config.strategy.default_spread,
            'quote_refresh_interval': app_config.strategy.quote_refresh_interval,
            'use_weather_fair_value': app_config.strategy.use_weather_fair_value,
        },
    })


@api_bp.route('/config', methods=['PATCH'])
def update_config():
    """Update configuration (limited fields)."""
    data = request.get_json() or {}
    
    # Update risk config
    if 'risk' in data:
        risk = data['risk']
        if 'max_position_per_market' in risk:
            app_config.risk.max_position_per_market = int(risk['max_position_per_market'])
        if 'max_total_position' in risk:
            app_config.risk.max_total_position = int(risk['max_total_position'])
        if 'default_order_size' in risk:
            app_config.risk.default_order_size = int(risk['default_order_size'])
    
    # Update strategy config
    if 'strategy' in data:
        strategy = data['strategy']
        if 'min_spread' in strategy:
            app_config.strategy.min_spread = int(strategy['min_spread'])
        if 'default_spread' in strategy:
            app_config.strategy.default_spread = int(strategy['default_spread'])
        if 'quote_refresh_interval' in strategy:
            app_config.strategy.quote_refresh_interval = float(strategy['quote_refresh_interval'])
    
    return jsonify({'status': 'updated'})
