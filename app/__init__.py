"""
Flask Application Package
"""
import logging
from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()

logger = logging.getLogger(__name__)


def create_app():
    """Application factory."""
    app = Flask(__name__)
    
    # Load config
    from config import config as app_config
    app.config['SECRET_KEY'] = app_config.flask.secret_key
    
    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins="*")
    
    # Register blueprints
    from app.routes import dashboard_bp, api_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    try:
        from services.market_maker import market_maker
        from services.orderbook import orderbook_service

        if not market_maker.get_market_states():
            if market_maker.initialize():
                tickers = list(market_maker.get_market_states().keys())
                if tickers:
                    orderbook_service.subscribe(tickers)
            else:
                logger.warning(
                    "Market pre-initialization failed; dashboard will show no markets until strategy start or manual refresh"
                )
    except Exception as e:
        logger.warning(f"Market pre-initialization error: {e}")
    
    return app
