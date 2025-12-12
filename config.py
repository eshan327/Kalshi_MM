"""
Configuration settings for Kalshi Market Maker application.

Loads settings from environment variables with sensible defaults.
Copy .env.example to .env and customize for your setup.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars


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
    except (ValueError, TypeError):
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float environment variable."""
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


@dataclass
class KalshiConfig:
    """Kalshi API configuration."""
    # API endpoints
    base_url: str = field(default_factory=lambda: _get_env(
        "KALSHI_BASE_URL", 
        "https://api.elections.kalshi.com/trade-api/v2"
    ))
    ws_url: str = field(default_factory=lambda: _get_env(
        "KALSHI_WS_URL",
        "wss://api.elections.kalshi.com/trade-api/ws/v2"
    ))
    
    # API Key (from environment)
    api_key_id: str = field(default_factory=lambda: _get_env("KALSHI_API_KEY_ID", ""))
    key_file: str = field(default_factory=lambda: _get_env("KALSHI_PRIVATE_KEY_FILE", "private_key.pem"))
    
    # Environment toggle (kept for backwards compatibility)
    use_prod: bool = field(default_factory=lambda: _get_env("KALSHI_ENVIRONMENT", "production").lower() == "production")
    
    def __post_init__(self):
        if not self.api_key_id:
            raise ValueError(
                "KALSHI_API_KEY_ID environment variable is required. "
                "Set it in your .env file or environment."
            )


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Position limits
    max_position_per_market: int = field(default_factory=lambda: _get_env_int("MAX_POSITION_PER_MARKET", 100))
    max_total_position: int = field(default_factory=lambda: _get_env_int("MAX_TOTAL_POSITION", 500))
    max_daily_loss: float = field(default_factory=lambda: _get_env_float("MAX_DAILY_LOSS", 50.00))
    
    # Inventory management
    inventory_skew_factor: float = field(default_factory=lambda: _get_env_float("INVENTORY_SKEW_FACTOR", 0.5))
    max_inventory_skew: int = field(default_factory=lambda: _get_env_int("MAX_INVENTORY_SKEW", 10))
    
    # Time-based risk
    hours_before_settlement_exit: float = field(default_factory=lambda: _get_env_float("HOURS_BEFORE_SETTLEMENT_EXIT", 4.0))
    
    # Order sizing
    default_order_size: int = field(default_factory=lambda: _get_env_int("DEFAULT_ORDER_SIZE", 10))
    max_order_size: int = field(default_factory=lambda: _get_env_int("MAX_ORDER_SIZE", 50))


@dataclass  
class StrategyConfig:
    """Market making strategy configuration."""
    # Target series
    target_series: str = field(default_factory=lambda: _get_env("TARGET_SERIES", "KXHIGHNY"))
    
    # Spread configuration
    min_spread: int = field(default_factory=lambda: _get_env_int("MIN_SPREAD", 5))
    default_spread: int = field(default_factory=lambda: _get_env_int("DEFAULT_SPREAD", 6))
    
    # Quote behavior
    quote_refresh_interval: float = field(default_factory=lambda: _get_env_float("QUOTE_REFRESH_INTERVAL", 5.0))
    requote_on_fill: bool = field(default_factory=lambda: _get_env_bool("REQUOTE_ON_FILL", True))


@dataclass
class FlaskConfig:
    """Flask application configuration."""
    secret_key: str = field(default_factory=lambda: _get_env("FLASK_SECRET_KEY", "") or os.urandom(24).hex())
    debug: bool = field(default_factory=lambda: _get_env_bool("FLASK_DEBUG", True))
    host: str = field(default_factory=lambda: _get_env("FLASK_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _get_env_int("FLASK_PORT", 5000))


@dataclass
class AppConfig:
    """Main application configuration."""
    kalshi: KalshiConfig = field(default_factory=KalshiConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    flask: FlaskConfig = field(default_factory=FlaskConfig)


# Global config instance
config = AppConfig()
