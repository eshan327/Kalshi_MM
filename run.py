#!/usr/bin/env python3
"""
Kalshi Market Maker - Main Entry Point

Run this script to start the Flask web application and market maker.
"""
import logging
import os
import sys
from pathlib import Path

# Load .env file if it exists
def load_dotenv():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('kalshi_mm.log'),
    ]
)
logger = logging.getLogger(__name__)


def initialize_services():
    """Initialize all services."""
    from config import config as app_config
    from services.kalshi_client import kalshi_service
    from services.orderbook import orderbook_service
    from services.risk_manager import risk_manager
    
    # Initialize Kalshi client
    if not kalshi_service.initialize():
        logger.error("Failed to initialize Kalshi service")
        return False
    
    # Initialize orderbook service with private key
    key_file = app_config.kalshi.key_file
    try:
        with open(key_file, "r") as f:
            private_key = f.read()
    except FileNotFoundError:
        logger.error(f"Private key file not found: {key_file}")
        return False
    
    orderbook_service.initialize(private_key)
    
    # Initialize risk manager
    risk_manager.initialize()
    
    logger.info("All services initialized successfully")
    return True


def main():
    """Main entry point."""
    from config import config as app_config
    
    logger.info("=" * 60)
    logger.info("Kalshi Market Maker Starting")
    logger.info(f"Environment: {'PRODUCTION' if app_config.kalshi.use_prod else 'DEMO'}")
    logger.info("=" * 60)
    
    # Initialize services
    if not initialize_services():
        sys.exit(1)
    
    # Start orderbook WebSocket service
    from services.orderbook import orderbook_service
    orderbook_service.start()
    
    # Create and run Flask app
    from app import create_app, socketio
    
    app = create_app()
    
    logger.info(f"Starting web server on http://{app_config.flask.host}:{app_config.flask.port}")
    
    try:
        socketio.run(
            app, 
            host=app_config.flask.host,
            port=app_config.flask.port,
            debug=app_config.flask.debug,
            use_reloader=False,  # Disable reloader to prevent double initialization
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        from services.market_maker import market_maker
        market_maker.stop()
        orderbook_service.stop()
        logger.info("Shutdown complete")


if __name__ == '__main__':
    main()
