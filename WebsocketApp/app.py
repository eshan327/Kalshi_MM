"""
Kalshi Real-time Dashboard - Flask Web Application.

A Flask + SocketIO web application that provides:
- Real-time market price updates via WebSocket
- Live orderbook visualization
- Market subscription management
- Trade activity monitoring

Usage:
    cd WebsocketApp
    python app.py
    # Open http://localhost:5001 in your browser
"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import asyncio
import threading
import json
import time
import os
import sys
import webbrowser

project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
# Also add WebsocketApp directory for local imports when running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Websocket.market_streamer import KalshiMarketStreamer
from websocket_handler import KalshiWebSocketHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kalshi-websocket-dashboard'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

ws_handler = KalshiWebSocketHandler()
ws_event_loop = None


def run_async_websocket():
    """Run async WebSocket handler in separate thread."""
    global ws_event_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ws_event_loop = loop
    
    def message_callback(event_type, data):
        if event_type == 'log':
            socketio.emit('log_update', {'id': data.get('id', ''), 'timestamp': data.get('timestamp', int(time.time() * 1000)),
                         'level': data.get('level', 'info'), 'message': data.get('message', ''), 'details': data.get('details')})
        elif event_type == 'orderbook_update':
            socketio.emit('orderbook_update', {'market_id': data.get('market_id'), 'orderbook_data': data.get('orderbook_data')})
        elif event_type == 'ticker_update':
            socketio.emit('ticker_update', {'market_id': data.get('market_id'), 'ticker_data': data.get('ticker_data')})
        elif event_type == 'trade_update':
            socketio.emit('trade_update', {'market_id': data.get('market_id'), 'trade_data': data.get('trade_data')})
        elif event_type == 'price_update':
            socketio.emit('price_update', {'market_id': data.get('market_id'), 'yes_price': data.get('yes_price'),
                         'no_price': data.get('no_price'), 'timestamp': data.get('timestamp')})
        elif event_type == 'raw_message':
            socketio.emit('raw_message', {'message': data.get('message'), 'timestamp': data.get('timestamp', int(time.time() * 1000))})
    
    ws_handler.add_message_callback(message_callback)
    loop.run_until_complete(ws_handler.connect())


ws_thread = threading.Thread(target=run_async_websocket, daemon=True)
ws_thread.start()


def run_in_ws_loop(coro):
    """Run coroutine in WebSocket thread's event loop."""
    if ws_event_loop and ws_event_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, ws_event_loop).result(timeout=10)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    return jsonify(ws_handler.get_status())


@app.route('/api/subscribe', methods=['POST'])
def subscribe_market():
    market_id = request.get_json().get('market_id')
    if not market_id:
        return jsonify({'error': 'Market ID required'}), 400
    try:
        return jsonify({'success': run_in_ws_loop(ws_handler.subscribe_to_market(market_id))})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/unsubscribe', methods=['POST'])
def unsubscribe_market():
    market_id = request.get_json().get('market_id')
    if not market_id:
        return jsonify({'error': 'Market ID required'}), 400
    try:
        run_in_ws_loop(ws_handler.unsubscribe_from_market(market_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/reconnect', methods=['POST'])
def force_reconnect():
    try:
        run_in_ws_loop(ws_handler.force_reconnect())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    ws_handler.clear_logs()
    return jsonify({'success': True})


@socketio.on('connect')
def handle_connect():
    print('Client connected')
    try:
        status = ws_handler.get_status()
        emit('status', {'status': status.get('connection_status', 'disconnected')})
        
        if status.get('price_data'):
            emit('initial_price_data', {'price_data': status['price_data']})
        
        for market_id in status.get('subscribed_markets', []):
            if market_id in ws_handler.market_data:
                market = ws_handler.market_data[market_id]
                if market.orderbook:
                    emit('orderbook_update', {'market_id': market_id, 'orderbook_data': market.orderbook})
                if market.yes_price is not None:
                    emit('price_update', {'market_id': market_id, 'yes_price': market.yes_price,
                                         'no_price': market.no_price, 'timestamp': market.last_update})
            emit('subscription_result', {'success': True, 'market_id': market_id})
        
        emit('log_update', {'id': f"status_{int(time.time()*1000)}", 'timestamp': int(time.time()*1000),
             'level': 'info', 'message': f"Client connected. WS: {status.get('connection_status', 'disconnected')}"})
    except Exception as e:
        print(f"Error in handle_connect: {e}")
        emit('status', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@socketio.on('subscribe_market')
def handle_subscribe_market(data):
    market_id = data.get('market_id')
    if market_id:
        try:
            success = run_in_ws_loop(ws_handler.subscribe_to_market(market_id))
            emit('subscription_result', {'success': success, 'market_id': market_id})
        except Exception as e:
            emit('subscription_result', {'success': False, 'market_id': market_id, 'error': str(e)})


@socketio.on('unsubscribe_market')
def handle_unsubscribe_market(data):
    market_id = data.get('market_id')
    if market_id:
        try:
            run_in_ws_loop(ws_handler.unsubscribe_from_market(market_id))
            emit('unsubscription_result', {'success': True, 'market_id': market_id})
        except Exception as e:
            emit('unsubscription_result', {'success': False, 'market_id': market_id, 'error': str(e)})


def find_available_port(start_port=5000, max_attempts=10):
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available port in {start_port}-{start_port + max_attempts - 1}")


if __name__ == '__main__':
    print("🚀 Starting Kalshi WebSocket Dashboard...")
    port = find_available_port(5000)
    if port != 5000:
        print(f"⚠️  Port 5000 in use, using {port}")
    
    url = f"http://localhost:{port}"
    print(f"📊 Dashboard: {url}")
    
    browser_flag = os.path.join(os.path.dirname(__file__), '.browser_opened')
    
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        should_open = True
        if os.path.exists(browser_flag):
            try:
                with open(browser_flag) as f:
                    if f.read().strip() == str(port):
                        should_open = False
            except:
                pass
        
        if should_open:
            with open(browser_flag, 'w') as f:
                f.write(str(port))
            
            def open_browser():
                time.sleep(1.5)
                browser_port = max(5000, port - 1)
                print(f"🌐 Opening browser at http://localhost:{browser_port}...")
                webbrowser.open(f"http://localhost:{browser_port}")
            
            threading.Thread(target=open_browser, daemon=True).start()
    
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

