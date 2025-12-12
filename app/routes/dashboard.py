"""
Dashboard Routes

Main web interface for the market maker.
"""
from flask import Blueprint, render_template

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')


@dashboard_bp.route('/markets')
def markets():
    """Markets detail page."""
    return render_template('markets.html')


@dashboard_bp.route('/settings')
def settings():
    """Settings page."""
    return render_template('settings.html')
