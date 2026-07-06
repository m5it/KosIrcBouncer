"""
Web Dashboard for IRC BNC - Flask Application
"""

import os
import json
import time
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, jsonify, request, session
from flask_socketio import SocketIO, emit, disconnect


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")


# Global references (set by main)
bnc_server = None
irc_clients = None
buffer_manager = None
user_db = None


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'authenticated' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    """Authenticate user."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Simple auth for demo
    if username and password:
        session['authenticated'] = True
        session['username'] = username
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/logout', methods=['POST'])
def logout():
    """Logout user."""
    session.clear()
    return jsonify({'success': True})


# API Routes


@app.route('/api/status')
@require_auth
def api_status():
    """Get overall BNC status."""
    if not bnc_server:
        return jsonify({'error': 'BNC not initialized'}), 500
    
    status = bnc_server.get_stats()
    
    # Add IRC client statuses
    networks = {}
    if irc_clients:
        for name, client in irc_clients.items():
            networks[name] = {
                'connected': client.is_connected(),
                'nick': client.state.current_nick if client.is_connected() else None,
                'channels': len(client.get_channel_list()) if client.is_connected() else 0
            }
    
    return jsonify({
        'bnc': status,
        'networks': networks,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/networks')
@require_auth
def api_networks():
    """List all IRC networks."""
    if not irc_clients:
        return jsonify({'networks': []})
    
    networks = []
    for name, client in irc_clients.items():
        networks.append({
            'name': name,
            'connected': client.is_connected(),
            'host': client.config.host,
            'port': client.config.port,
            'nick': client.state.current_nick if client.is_connected() else None,
            'channels': client.get_channel_list() if client.is_connected() else []
        })
    
    return jsonify({'networks': networks})


@app.route('/api/networks/<name>/status')
@require_auth
def api_network_status(name):
    """Get specific network status."""
    client = irc_clients.get(name) if irc_clients else None
    if not client:
        return jsonify({'error': 'Network not found'}), 404
    
    return jsonify({
        'name': name,
        'connected': client.is_connected(),
        'nick': client.state.current_nick if client.is_connected() else None,
        'channels': client.get_channel_list() if client.is_connected() else [],
        'stats': client.get_stats() if client.is_connected() else {}
    })


@app.route('/api/buffers')
@require_auth
def api_buffers():
    """List all buffers."""
    if not buffer_manager:
        return jsonify({'buffers': []})
    
    stats = {}
    for name in irc_clients.keys() if irc_clients else []:
        stats[name] = buffer_manager.get_buffer_stats(name)
    
    return jsonify({'buffers': stats})


@app.route('/api/buffers/<network>/<channel>')
@require_auth
def api_buffer_messages(network, channel):
    """Get messages from a buffer."""
    if not buffer_manager:
        return jsonify({'messages': []})
    
    buf = buffer_manager.get_buffer(network, f"#{channel}")
    count = request.args.get('count', 50, type=int)
    messages = buf.get_last(count)
    
    return jsonify({
        'network': network,
        'channel': channel,
        'messages': [
            {
                'timestamp': m.timestamp.isoformat(),
                'nick': m.nick,
                'message': m.message,
                'type': m.msg_type.value if hasattr(m, 'msg_type') else 'text'
            }
            for m in messages
        ]
    })


@app.route('/api/users')
@require_auth
def api_users():
    """List connected users."""
    if not bnc_server:
        return jsonify({'users': []})
    
    sessions = bnc_server.list_sessions()
    return jsonify({'users': sessions})


@app.route('/api/stats')
@require_auth
def api_stats():
    """Get detailed statistics."""
    stats = {
        'timestamp': datetime.now().isoformat(),
        'uptime': None,
        'messages_per_minute': 0,
        'total_messages': 0,
        'active_users': 0,
        'connected_networks': 0
    }
    
    if bnc_server:
        bnc_stats = bnc_server.get_stats()
        stats['uptime'] = bnc_stats.get('uptime')
        stats['active_users'] = bnc_stats.get('active_sessions', 0)
    
    if irc_clients:
        stats['connected_networks'] = sum(
            1 for c in irc_clients.values() if c.is_connected()
        )
    
    return jsonify(stats)


@app.route('/api/config', methods=['GET', 'POST'])
@require_auth
def api_config():
    """Get or update configuration."""
    if request.method == 'GET':
        # Return current config
        return jsonify({
            'bnc': {
                'host': bnc_server.config.bind_host if bnc_server else None,
                'port': bnc_server.config.bind_port if bnc_server else None
            } if bnc_server else None,
            'networks': [
                {
                    'name': c.name,
                    'host': c.host,
                    'port': c.port,
                    'ssl': c.ssl,
                    'nick': c.nick,
                    'channels': c.channels
                }
                for c in (irc_clients.values() if irc_clients else [])
            ]
        })
    
    # POST - update config
    data = request.get_json()
    # Would update configuration here
    return jsonify({'success': True, 'message': 'Configuration updated'})


@app.route('/api/logs')
@require_auth
def api_logs():
    """Get recent logs."""
    # Would read from log file
    return jsonify({'logs': ['Log entry 1', 'Log entry 2']})


# WebSocket Events


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    print(f'[Web] Client connected: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    print(f'[Web] Client disconnected: {request.sid}')


@socketio.on('authenticate')
def handle_authenticate(data):
    """Authenticate WebSocket client."""
    token = data.get('token')
    if token:  # Would validate token
        emit('authenticated', {'success': True})
    else:
        emit('authenticated', {'success': False, 'error': 'Invalid token'})
        disconnect()


@socketio.on('join_channel')
def handle_join_channel(data):
    """Join IRC channel."""
    network = data.get('network')
    channel = data.get('channel')
    
    client = irc_clients.get(network) if irc_clients else None
    if client and client.is_connected():
        client.join_channel(channel)
        emit('channel_joined', {'network': network, 'channel': channel})


@socketio.on('send_message')
def handle_send_message(data):
    """Send IRC message."""
    network = data.get('network')
    target = data.get('target')
    message = data.get('message')
    
    client = irc_clients.get(network) if irc_clients else None
    if client and client.is_connected():
        client.send_message(target, message)
        emit('message_sent', {'network': network, 'target': target, 'message': message})


@socketio.on('subscribe_network')
def handle_subscribe_network(data):
    """Subscribe to network events."""
    network = data.get('network')
    
    def on_message(msg):
        socketio.emit('irc_message', {
            'network': network,
            'raw': msg.raw,
            'command': msg.command,
            'params': msg.params,
            'trailing': msg.trailing
        }, room=request.sid)
    
    client = irc_clients.get(network) if irc_clients else None
    if client:
        client.add_message_callback(on_message)
        emit('subscribed', {'network': network})


def broadcast_status():
    """Broadcast status to all connected clients."""
    while True:
        time.sleep(5)
        try:
            if bnc_server:
                status = bnc_server.get_stats()
                socketio.emit('status_update', status)
        except Exception as e:
            print(f'[Web] Broadcast error: {e}')


def init_web(server, clients, buffers, users, host='0.0.0.0', port=8080):
    """Initialize web server."""
    global bnc_server, irc_clients, buffer_manager, user_db
    
    bnc_server = server
    irc_clients = clients
    buffer_manager = buffers
    user_db = users
    
    # Start broadcast thread
    thread = threading.Thread(target=broadcast_status, daemon=True)
    thread.start()
    
    print(f'[Web] Starting web server on {host}:{port}')
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    # Development mode
    init_web(None, {}, None, None)