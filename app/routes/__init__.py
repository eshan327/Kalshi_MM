"""
Flask Routes Package
"""
from app.routes.dashboard import dashboard_bp
from app.routes.api import api_bp

__all__ = ['dashboard_bp', 'api_bp']
