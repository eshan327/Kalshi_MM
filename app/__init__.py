"""
Flask Application Package
"""
from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


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
    
    return app
