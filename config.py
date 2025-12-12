"""
Configuration settings for Kalshi Market Maker application.

Configuration is loaded from environment variables with sensible defaults.
Copy .env.example to .env and customize for your setup.
"""
import os
from dataclasses import dataclass, field
from typing import Optional


def _get_env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.environ.get(key, default)


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _get_env_int(key: str, default: int) -> int:
    """Get integer environment variable."""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float environment variable."""
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass
class KalshiConfig:
    """Kalshi API configuration."""
    # API endpoints
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    ws_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    
    # Production credentials (loaded from environment)
    prod_api_key_id: str = field(
        default_factory=lambda: _get_env("KALSHI_PROD_API_KEY_ID", "")
    )
    prod_key_file: str = "private_key.pem"
    
    # Demo credentials (loaded from environment)
    demo_api_key_id: str = field(
        default_factory=lambda: _get_env("KALSHI_DEMO_API_KEY_ID", "")
    )
    demo_key_file: str = "private_demo_key.pem"
    
    # Environment toggle (default to demo for safety)
    use_prod: bool = field(
        default_factory=lambda: _get_env("KALSHI_ENV", "demo").lower() == "prod"
    )
    
    @property
    def api_key_id(self) -> str:
        return self.prod_api_key_id if self.use_prod else self.demo_api_key_id
    
    @property
    def key_file(self) -> str:
        return self.prod_key_file if self.use_prod else self.demo_key_file


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Position limits
    max_position_per_market: int = field(
        default_factory=lambda: _get_env_int("MAX_POSITION_PER_MARKET", 100)
    )
    max_total_position: int = field(
        default_factory=lambda: _get_env_int("MAX_TOTAL_POSITION", 500)
    )
    max_daily_loss: float = field(
        default_factory=lambda: _get_env_float("MAX_DAILY_LOSS", 50.00)
    )
    
    # Inventory management
    inventory_skew_factor: float = 0.5  # Cents to skew per contract of inventory
    max_inventory_skew: int = 10  # Max cents to skew
    
    # Time-based risk
    hours_before_settlement_exit: float = 4.0  # Exit positions before settlement
    
    # Order sizing
    default_order_size: int = field(
        default_factory=lambda: _get_env_int("DEFAULT_ORDER_SIZE", 10)
    )
    max_order_size: int = 50  # Max contracts per order


@dataclass  
class StrategyConfig:
    """Market making strategy configuration."""
    # Target series
    target_series: str = field(
        default_factory=lambda: _get_env("TARGET_SERIES", "KXHIGHNY")
    )
    
    # Spread configuration
    min_spread: int = field(
        default_factory=lambda: _get_env_int("MIN_SPREAD", 5)
    )
    default_spread: int = 6  # Default half-spread on each side
    
    # Quote behavior
    quote_refresh_interval: float = 5.0  # Seconds between quote updates
    requote_on_fill: bool = True  # Immediately requote after a fill
    
    # Fair value
    use_weather_fair_value: bool = True  # Use weather API for pricing
    fair_value_confidence_threshold: float = 0.7  # Min confidence to use model FV


@dataclass
class FlaskConfig:
    """Flask application configuration."""
    secret_key: str = field(default_factory=lambda: os.urandom(24).hex())
    debug: bool = field(
        default_factory=lambda: _get_env_bool("FLASK_DEBUG", True)
    )
    host: str = field(
        default_factory=lambda: _get_env("FLASK_HOST", "127.0.0.1")
    )
    port: int = field(
        default_factory=lambda: _get_env_int("FLASK_PORT", 5000)
    )


@dataclass
class AppConfig:
    """Main application configuration."""
    kalshi: KalshiConfig = field(default_factory=KalshiConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    flask: FlaskConfig = field(default_factory=FlaskConfig)


# Global config instance
config = AppConfig()
