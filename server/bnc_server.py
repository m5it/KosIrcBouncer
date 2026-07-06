"""
BNC Server - Accepts IRC client connections
"""

import socket
import threading
import ssl
import time
from typing import Dict, List, Optional
from datetime import datetime

from ..config import BncServerConfig
from ..client import IrcClient
from .user_session import UserSession


class BncServer:
    """
    Main BNC server that accepts IRC client connections.
    Bridges users to IRC networks.
    """
    
    def __init__(self, config: BncServerConfig, irc_clients: Dict[str, IrcClient]):
        self.config = config
        self.irc_clients = irc_clients  # Available IRC connections
        
        self.socket: Optional[socket.socket] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        
        # Active sessions
        self.sessions: List[UserSession] = []
        self._lock = threading.Lock()
        
        # Running state
        self.running = False
        self._server_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.start_time: Optional[datetime] = None
        self.total_connections = 0
        
        # Setup SSL if configured
        if config.ssl_cert and config.ssl_key:
            self._setup_ssl()
    
    def _setup_ssl(self) -> None:
        """Setup SSL context."""
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(self.config.ssl_cert, self.config.ssl_key)
        print(f"[BNC] SSL configured with {self.config.ssl_cert}")
    
    def start(self) -> bool:
        """Start BNC server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.config.bind_host, self.config.bind_port))
            self.socket.listen(5)
            
            self.running = True
            self.start_time = datetime.now()
            
            # Start server thread
            self._server_thread = threading.Thread(target=self._accept_loop)
            self._server_thread.daemon = True
            self._server_thread.start()
            
            proto = "SSL" if self.ssl_context else "plain"
            print(f"[BNC] Server started on {self.config.bind_host}:{self.config.bind_port} ({proto})")
            return True
            
        except Exception as e:
            print(f"[BNC] Failed to start server: {e}")
            return False
    
    def stop(self) -> None:
        """Stop BNC server."""
        self.running = False
        
        # Close all sessions
        with self._lock:
            for session in self.sessions[:]:
                session.disconnect()
            self.sessions.clear()
        
        # Close server socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        print("[BNC] Server stopped")
    
    def _accept_loop(self) -> None:
        """Accept incoming connections."""
        self.socket.settimeout(1.0)  # Allow checking self.running
        
        while self.running:
            try:
                conn, addr = self.socket.accept()
                self._handle_connection(conn, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[BNC] Accept error: {e}")
    
    def _handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """Handle new connection."""
        self.total_connections += 1
        print(f"[BNC] New connection from {addr} (#{self.total_connections})")
        
        # Wrap with SSL if configured
        if self.ssl_context:
            try:
                conn = self.ssl_context.wrap_socket(conn, server_side=True)
                print(f"[BNC] SSL handshake successful for {addr}")
            except Exception as e:
                print(f"[BNC] SSL handshake failed: {e}")
                try:
                    conn.close()
                except:
                    pass
                return
        
        # Create session
        session = UserSession(
            conn=conn,
            addr=addr,
            irc_clients=self.irc_clients,
            require_auth=self.config.require_auth
        )
        
        with self._lock:
            self.sessions.append(session)
        
        session.start()
    
    def cleanup_sessions(self) -> int:
        """Remove dead sessions. Returns count removed."""
        with self._lock:
            dead = [s for s in self.sessions if not s.running]
            for s in dead:
                self.sessions.remove(s)
            return len(dead)
    
    def get_stats(self) -> dict:
        """Get server statistics."""
        self.cleanup_sessions()
        
        uptime = datetime.now() - self.start_time if self.start_time else None
        
        return {
            'running': self.running,
            'bind_host': self.config.bind_host,
            'bind_port': self.config.bind_port,
            'ssl': self.ssl_context is not None,
            'uptime': str(uptime) if uptime else None,
            'total_connections': self.total_connections,
            'active_sessions': len(self.sessions),
            'max_users': self.config.max_users
        }
    
    def list_sessions(self) -> List[dict]:
        """List active sessions."""
        self.cleanup_sessions()
        return [s.get_stats() for s in self.sessions]
    
    def disconnect_user(self, nick: str) -> bool:
        """Disconnect a user by nick."""
        with self._lock:
            for session in self.sessions:
                if session.nick == nick:
                    session.disconnect()
                    return True
        return False