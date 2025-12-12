"""
Kalshi Real-time Dashboard Web Application
Flask app with SocketIO for real-time WebSocket data streaming
"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import asyncio
import threading
import json
import time
import os
import traceback
from datetime import datetime
import sys
import webbrowser

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from Websocket.market_streamer import KalshiMarketStreamer
from websocket_handler import KalshiWebSocketHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kalshi-websocket-dashboard'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global WebSocket handler
# Determine demo mode from environment or default to False (production)
# Set KALSHI_DEMO=true environment variable to use demo mode
# By default, use PRODUCTION mode (demo=False)
demo_mode = os.environ.get('KALSHI_DEMO', 'false').lower() == 'true'
ws_handler = KalshiWebSocketHandler(demo=demo_mode)
ws_event_loop = None  # Will hold reference to the WebSocket thread's event loop

# Log the mode being used
print(f"\n{'='*60}")
print(f"🌐 Kalshi WebSocket Dashboard")
print(f"{'='*60}")
print(f"Mode: {'DEMO' if demo_mode else 'PRODUCTION'}")
if demo_mode:
    print("⚠️  WARNING: Running in DEMO mode - trades will not execute in production!")
    print("   To use production, ensure KALSHI_DEMO is not set or set to 'false'")
else:
    print("✓ Running in PRODUCTION mode - trades will execute with REAL MONEY!")
    print("   To use demo, set environment variable: KALSHI_DEMO=true")
print(f"{'='*60}\n")

def run_async_websocket():
    """Run the async WebSocket handler in a separate thread"""
    global ws_event_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ws_event_loop = loop  # Store reference for thread-safe operations
    
    def message_callback(event_type, data):
        """Callback for WebSocket events"""
        if event_type == 'log':
            socketio.emit('log_update', {
                'id': data.get('id', ''),
                'timestamp': data.get('timestamp', int(time.time() * 1000)),
                'level': data.get('level', 'info'),
                'message': data.get('message', ''),
                'details': data.get('details')
            })
        elif event_type == 'orderbook_update':
            socketio.emit('orderbook_update', {
                'market_id': data.get('market_id'),
                'orderbook_data': data.get('orderbook_data')
            })
        elif event_type == 'ticker_update':
            socketio.emit('ticker_update', {
                'market_id': data.get('market_id'),
                'ticker_data': data.get('ticker_data')
            })
        elif event_type == 'trade_update':
            socketio.emit('trade_update', {
                'market_id': data.get('market_id'),
                'trade_data': data.get('trade_data')
            })
        elif event_type == 'price_update':
            socketio.emit('price_update', {
                'market_id': data.get('market_id'),
                'yes_price': data.get('yes_price'),
                'no_price': data.get('no_price'),
                'timestamp': data.get('timestamp')
            })
        elif event_type == 'raw_message':
            socketio.emit('raw_message', {
                'message': data.get('message'),
                'timestamp': data.get('timestamp', int(time.time() * 1000))
            })
    
    ws_handler.add_message_callback(message_callback)
    
    # Start the WebSocket connection
    loop.run_until_complete(ws_handler.connect())

# Start WebSocket handler in background thread
ws_thread = threading.Thread(target=run_async_websocket, daemon=True)
ws_thread.start()

def run_in_ws_loop(coro):
    """Helper to run coroutine in the WebSocket thread's event loop"""
    if ws_event_loop and ws_event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, ws_event_loop)
        return future.result(timeout=10)  # 10 second timeout
    else:
        # Fallback: create temporary loop if WS loop not ready
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get current WebSocket status"""
    status = ws_handler.get_status()
    return jsonify(status)

@app.route('/api/subscribe', methods=['POST'])
def subscribe_market():
    """Subscribe to a market"""
    data = request.get_json()
    market_id = data.get('market_id')
    
    if not market_id:
        return jsonify({'error': 'Market ID is required'}), 400
    
    # Run async subscription in the WebSocket thread's event loop
    try:
        success = run_in_ws_loop(ws_handler.subscribe_to_market(market_id))
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/unsubscribe', methods=['POST'])
def unsubscribe_market():
    """Unsubscribe from a market"""
    data = request.get_json()
    market_id = data.get('market_id')
    
    if not market_id:
        return jsonify({'error': 'Market ID is required'}), 400
    
    # Run async unsubscription in the WebSocket thread's event loop
    try:
        run_in_ws_loop(ws_handler.unsubscribe_from_market(market_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/reconnect', methods=['POST'])
def force_reconnect():
    """Force WebSocket reconnection"""
    try:
        run_in_ws_loop(ws_handler.force_reconnect())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    """Clear all logs"""
    ws_handler.clear_logs()
    return jsonify({'success': True})

@app.route('/api/find-opportunities', methods=['POST'])
def find_opportunities():
    """Find market opportunities using basicMM - matches the main method logic"""
    try:
        data = request.get_json() or {}
        
        # Import BasicMM
        from Strategies.basicMM import BasicMM

        # Create BasicMM instance (using demo mode from ws_handler)
        demo = ws_handler.demo if hasattr(ws_handler, 'demo') else False
        print(f"Initializing BasicMM in {'DEMO' if demo else 'PRODUCTION'} mode...")
        mm = BasicMM(demo=demo)
        
        # Call identify_market_opportunities with max_total=None to fetch ALL markets (like main method)
        print(f"Finding opportunities from ALL markets on Kalshi (this may take several minutes)...")
        print("This will use pagination to fetch all available markets...")
        
        try:
            mm.identify_market_opportunities(max_total=None, continue_from_last=False)  # None = fetch all markets
        except Exception as identify_error:
            import traceback
            print(f"Error in identify_market_opportunities: {identify_error}")
            traceback.print_exc()
            return jsonify({
                'error': f'Error identifying opportunities: {str(identify_error)}',
                'success': False
            }), 500
        
        # Check if market_opportunities was populated
        if not hasattr(mm, 'market_opportunities') or not mm.market_opportunities:
            print("Warning: No market opportunities found after identification")
            return jsonify({
                'success': True,
                'opportunities': [],
                'count': 0,
                'message': 'No market opportunities found'
            })
        
        print(f"Total markets analyzed: {len(mm.market_opportunities)}")
        print(f"Total opportunities identified: {len(mm.market_opportunities)}")
        
        # Call filter_market_opportunities with default parameters (matching main method)
        print("\nFiltering for markets with good volume and spread >= 3 cents...")
        try:
            filtered = mm.filter_market_opportunities(
                min_spread=0.03,  # 3 cents spread minimum
                min_volume=1000,  # Good volume threshold
                max_spread=0.1,   # Maximum spread
                min_price=0.1     # Minimum price
            )
        except Exception as filter_error:
            import traceback
            print(f"Error in filter_market_opportunities: {filter_error}")
            traceback.print_exc()
            return jsonify({
                'error': f'Error filtering opportunities: {str(filter_error)}',
                'success': False
            }), 500
        
        print(f"Total filtered opportunities: {len(filtered)}")
        
        # Convert market objects to dictionaries for JSON serialization (matching main method format)
        opportunities = []
        for market in filtered:
            try:
                # Get spread (matching main method logic)
                spread = mm.get_market_spread(market) if hasattr(mm, 'get_market_spread') else 0
                if spread == 0:
                    # Calculate spread from bid/ask
                    yes_bid = getattr(market, 'yes_bid', None)
                    yes_ask = getattr(market, 'yes_ask', None)
                    if yes_bid is not None and yes_ask is not None:
                        if yes_bid > 1 or yes_ask > 1:
                            spread = (yes_ask - yes_bid) / 100.0
                        else:
                            spread = yes_ask - yes_bid
                
                # Get market details
                market_id = getattr(market, 'ticker', None) or getattr(market, 'market_id', None)
                title = getattr(market, 'title', None) or getattr(market, 'question', None)
                volume = getattr(market, 'volume', 0) or 0
                yes_bid = getattr(market, 'yes_bid', None)
                yes_ask = getattr(market, 'yes_ask', None)
                no_bid = getattr(market, 'no_bid', None)
                no_ask = getattr(market, 'no_ask', None)
                
                opp_dict = {
                    'ticker': market_id,
                    'title': title,
                    'spread': spread,
                    'volume': volume,
                    'yes_bid': yes_bid,
                    'yes_ask': yes_ask,
                    'no_bid': no_bid,
                    'no_ask': no_ask,
                }
                opportunities.append(opp_dict)
            except Exception as e:
                print(f"Error serializing market opportunity: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"Successfully serialized {len(opportunities)} opportunities")
        
        return jsonify({
            'success': True,
            'opportunities': opportunities,
            'count': len(opportunities),
            'message': f'Found {len(opportunities)} market opportunities'
        })
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Unexpected error in find_opportunities: {error_msg}")
        traceback.print_exc()
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/api/start-market-making', methods=['POST'])
def start_market_making():
    """Start market making for a single market using basicMM"""
    try:
        data = request.get_json()
        market_id = data.get('market_id')
        bankroll = data.get('bankroll')  # Bankroll in dollars
        stop_loss = data.get('stop_loss', 0)  # Stop loss in cents, default 0
        
        if not market_id:
            return jsonify({'error': 'Market ID is required', 'success': False}), 400
        
        if not bankroll or bankroll <= 0:
            return jsonify({'error': 'Valid bankroll amount is required', 'success': False}), 400
        
        if stop_loss < 0:
            return jsonify({'error': 'Stop loss must be non-negative', 'success': False}), 400
        
        # Import BasicMM
        from Strategies.basicMM import BasicMM
        
        # Create BasicMM instance (using demo mode from ws_handler)
        demo = ws_handler.demo if hasattr(ws_handler, 'demo') else False
        
        # Log mode clearly
        mode_str = 'DEMO' if demo else 'PRODUCTION'
        if demo:
            print(f"⚠️  WARNING: Trading in DEMO mode - orders will not execute in production!")
        else:
            print(f"✓ Trading in PRODUCTION mode - orders will execute with REAL MONEY!")
        
        mm = BasicMM(demo=demo)
        
        # Verify the client is using the correct mode
        if hasattr(mm.client, 'api_client') and hasattr(mm.client.api_client, 'configuration'):
            config_host = mm.client.api_client.configuration.host
            if 'demo' in config_host.lower():
                print(f"⚠️  Client configured for DEMO environment: {config_host}")
            else:
                print(f"✓ Client configured for PRODUCTION environment: {config_host}")
        
        # Convert bankroll from dollars to cents (trade function expects cents)
        bankroll_cents = int(bankroll * 100)
        stop_loss_cents = int(stop_loss)  # Stop loss is already in cents
        
        print(f"Starting market making for {market_id} with bankroll ${bankroll} (${bankroll_cents} cents) and stop loss {stop_loss_cents} cents in {mode_str} mode")
        
        # Call trade function with single market ID (trade accepts both market objects and strings)
        # The trade function will handle getting prices and placing orders
        mm.trade([market_id], bankroll_cents, stop_loss=stop_loss_cents)
        
        return jsonify({
            'success': True,
            'message': f'Market making orders placed for {market_id}',
            'details': {
                'market_id': market_id,
                'bankroll': bankroll,
                'bankroll_cents': bankroll_cents,
                'demo_mode': demo
            }
        })
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    # Emit normalized status payload
    try:
        status = ws_handler.get_status()
        emit('status', {'status': status.get('connection_status', 'disconnected')})
        
        # Send subscribed markets and their data to restore state
        subscribed_markets = status.get('subscribed_markets', [])
        market_data = status.get('market_data', {})
        
        # Send all price data for charts
        price_data = status.get('price_data', {})
        if price_data:
            emit('initial_price_data', {'price_data': price_data})
        
        # Emit initial state for each subscribed market
        for market_id in subscribed_markets:
            market_info = market_data.get(market_id, {})
            # Send orderbook if available
            if market_id in ws_handler.market_data:
                market = ws_handler.market_data[market_id]
                if market.orderbook and (market.orderbook.get('yes_bids') or market.orderbook.get('yes_asks')):
                    emit('orderbook_update', {
                        'market_id': market_id,
                        'orderbook_data': market.orderbook
                    })
                # Send price if available (this will trigger chart update)
                if market.yes_price is not None:
                    emit('price_update', {
                        'market_id': market_id,
                        'yes_price': market.yes_price,
                        'no_price': market.no_price,
                        'timestamp': market.last_update
                    })
        
        # If WebSocket is connected, trigger orderbook fetch for any markets that don't have orderbook data yet
        if ws_event_loop and ws_event_loop.is_running():
            # Check if any subscribed markets are missing orderbook data
            markets_needing_orderbook = []
            for market_id in subscribed_markets:
                if market_id not in ws_handler.market_data or \
                   not ws_handler.market_data[market_id].orderbook or \
                   (not ws_handler.market_data[market_id].orderbook.get('yes_bids') and 
                    not ws_handler.market_data[market_id].orderbook.get('yes_asks')):
                    markets_needing_orderbook.append(market_id)
            
            if markets_needing_orderbook:
                print(f"Triggering orderbook fetch for {len(markets_needing_orderbook)} markets without orderbook data: {markets_needing_orderbook}")
                # Trigger orderbook fetch asynchronously for markets that need it
                asyncio.run_coroutine_threadsafe(
                    ws_handler.fetch_orderbooks_for_subscribed_markets(market_ids=markets_needing_orderbook),
                    ws_event_loop
                )
        
        # Also emit a log entry so the terminal unblocks immediately
        current_time = int(time.time() * 1000)
        emit('log_update', {
            'id': f"status_{current_time}",
            'timestamp': current_time,
            'level': 'info',
            'message': f"Client connected. Backend WS status: {status.get('connection_status', 'disconnected')}",
            'details': {
                'backend_status': status.get('connection_status', 'disconnected'),
                'subscribed_markets': subscribed_markets
            }
        })
        
        # Emit subscription results for all subscribed markets to restore UI state
        for market_id in subscribed_markets:
            emit('subscription_result', {'success': True, 'market_id': market_id})
            
    except Exception as e:
        print(f"Error in handle_connect: {e}")
        # Fallback minimal status
        emit('status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('subscribe_market')
def handle_subscribe_market(data):
    """Handle market subscription from client"""
    market_id = data.get('market_id')
    if market_id:
        try:
            success = run_in_ws_loop(ws_handler.subscribe_to_market(market_id))
            emit('subscription_result', {'success': success, 'market_id': market_id})
        except Exception as e:
            emit('subscription_result', {'success': False, 'market_id': market_id, 'error': str(e)})

@socketio.on('unsubscribe_market')
def handle_unsubscribe_market(data):
    """Handle market unsubscription from client"""
    market_id = data.get('market_id')
    if market_id:
        try:
            run_in_ws_loop(ws_handler.unsubscribe_from_market(market_id))
            emit('unsubscription_result', {'success': True, 'market_id': market_id})
        except Exception as e:
            emit('unsubscription_result', {'success': False, 'market_id': market_id, 'error': str(e)})

def find_available_port(start_port=5000, max_attempts=10):
    """Find an available port starting from start_port"""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_attempts - 1}")

if __name__ == '__main__':
    print("🚀 Starting Kalshi WebSocket Dashboard...")
    
    # Find an available port
    port = find_available_port(5000)
    
    if port != 5000:
        print(f"⚠️  Port 5000 is in use, using port {port} instead")
    
    url = f"http://localhost:{port}"
    print(f"📊 Dashboard available at: {url}")
    
    # Prevent multiple browser opens when Flask reloader runs
    # Flask's debug mode uses a reloader that can cause the script to run twice
    # Use a file-based flag to ensure browser only opens once per actual server start
    import os
    browser_flag_file = os.path.join(os.path.dirname(__file__), '.browser_opened')
    
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # This is the main process (not the reloader), safe to open browser
        # Check if we've already opened the browser for this port
        should_open = True
        if os.path.exists(browser_flag_file):
            try:
                with open(browser_flag_file, 'r') as f:
                    saved_port = f.read().strip()
                # Only skip if it's the same port (same server instance)
                if saved_port == str(port):
                    should_open = False
            except:
                pass
        
        if should_open:
            # Create/update flag file to mark that browser will be opened
            with open(browser_flag_file, 'w') as f:
                f.write(str(port))
            
            # Open browser automatically after a short delay
            def open_browser():
                # Wait for server to start
                time.sleep(1.5)
                # Open port one before the actual port (fix for port offset issue)
                browser_port = max(5000, port - 1)
                browser_url = f"http://localhost:{browser_port}"
                print(f"🌐 Opening browser at {browser_url}...")
                webbrowser.open(browser_url)
            
            # Start browser opener in a separate thread (only once)
            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()
        else:
            # Browser already opened for this port, just print the URL
            print(f"💡 Browser already opened for this port. Dashboard at: {url}")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

