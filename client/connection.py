"""
IRC Connection handler with SSL and SASL support
"""

import socket
import ssl
import threading
import time
import re
from typing import Optional, Callable, List
from datetime import datetime


class IrcConnection:
    """
    Low-level IRC connection handler.
    Manages socket, SSL, and basic protocol.
    """
    
    def __init__(self, host: str, port: int, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        
        self.socket: Optional[socket.socket] = None
        self.connected: bool = False
        self.receiving: bool = False
        self.receive_thread: Optional[threading.Thread] = None
        
        self._callbacks: List[Callable[[str], None]] = []
        self._lock = threading.Lock()
        
        # Statistics
        self.bytes_sent = 0
        self.bytes_received = 0
        self.connect_time: Optional[datetime] = None
    
    def connect(self) -> bool:
        """Establish connection to IRC server."""
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            
            # Wrap with SSL if enabled
            if self.use_ssl:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.socket = context.wrap_socket(sock, server_hostname=self.host)
            else:
                self.socket = sock
            
            # Connect
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(None)  # Non-blocking for select
            
            self.connected = True
            self.connect_time = datetime.now()
            
            # Start receive thread
            self.receiving = True
            self.receive_thread = threading.Thread(target=self._receive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Close connection."""
        self.receiving = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
    
    def send(self, message: str) -> bool:
        """Send raw IRC message."""
        if not self.connected or not self.socket:
            return False
        
        try:
            # Ensure CRLF termination
            if not message.endswith('\r\n'):
                message += '\r\n'
            
            data = message.encode('utf-8', errors='replace')
            
            with self._lock:
                self.socket.sendall(data)
                self.bytes_sent += len(data)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Send failed: {e}")
            self.disconnect()
            return False
    
    def _receive_loop(self) -> None:
        """Background receive loop."""
        buffer = ""
        
        while self.receiving and self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    # Connection closed
                    break
                
                buffer += data.decode('utf-8', errors='replace')
                self.bytes_received += len(data)
                
                # Process complete lines
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    self._handle_line(line)
                
            except Exception as e:
                if self.receiving:
                    print(f"[ERROR] Receive error: {e}")
                break
        
        self.connected = False
        self.receiving = False
    
    def _handle_line(self, line: str) -> None:
        """Process received line."""
        # Notify all callbacks
        for callback in self._callbacks:
            try:
                callback(line)
            except Exception as e:
                print(f"[ERROR] Callback error: {e}")
    
    def add_callback(self, callback: Callable[[str], None]) -> None:
        """Add message callback."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[str], None]) -> None:
        """Remove message callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def is_connected(self) -> bool:
        """Check connection status."""
        return self.connected and self.socket is not None
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            'connected': self.connected,
            'host': self.host,
            'port': self.port,
            'ssl': self.use_ssl,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'connect_time': self.connect_time
        }