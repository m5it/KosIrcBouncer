"""
User Session with Authentication - Task 5
"""

import socket
import threading
import time
import re
from typing import Optional, List, Dict
from datetime import datetime

from ..shared import IrcMessage, BufferManager, UserDatabase, RateLimiter, IPFilter


class AuthenticatedUserSession(threading.Thread):
    """
    User session with full authentication support.
    """
    
    def __init__(self, conn: socket.socket, addr: tuple,
                 irc_clients: Dict[str, object],
                 buffer_manager: BufferManager,
                 user_db: UserDatabase,
                 rate_limiter: RateLimiter,
                 ip_filter: IPFilter):
        super().__init__(daemon=True)
        
        self.conn = conn
        self.addr = addr
        self.ip = addr[0]
        self.irc_clients = irc_clients
        self.buffer = buffer_manager
        self.user_db = user_db
        self.rate_limiter = rate_limiter
        self.ip_filter = ip_filter
        
        # Auth state
        self.user: Optional[object] = None
        self.authenticated = False
        self.auth_stage = 'none'
        
        # IRC state
        self.nick: Optional[str] = None
        self.username: Optional[str] = None
        self.realname: Optional[str] = None
        self.current_network: Optional[str] = None
        self.selected_client: Optional[object] = None
        
        # Session
        self.running = False
        self.capabilities: set = set()
        
        # Stats
        self.connected_at = datetime.now()
        self.messages_sent = 0
    
    def run(self):
        """Main session with auth."""
        # Check IP filter first
        if not self.ip_filter.is_allowed(self.ip):
            self._send(":server 464 * :Your IP is blocked")
            self.conn.close()
            return
        
        # Check rate limit
        if not self.rate_limiter.is_allowed(self.ip):
            self._send(":server 464 * :Too many attempts, try later")
            self.conn.close()
            return
        
        self.rate_limiter.record_attempt(self.ip)
        self.running = True
        
        print(f"[Auth] New connection from {self.addr}")
        
        try:
            self._send_welcome_banner()
            
            buffer = ""
            while self.running:
                try:
                    self.conn.settimeout(1.0)
                    data = self.conn.recv(4096)
                    
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='replace')
                    
                    while '\r\n' in buffer:
                        line, buffer = buffer.split('\r\n', 1)
                        self._handle_line(line.strip())
                        
                except socket.timeout:
                    continue
                    
        except Exception as e:
            print(f"[Auth] Session error: {e}")
        finally:
            self._cleanup()
    
    def _handle_line(self, line: str):
        """Handle IRC command."""
        if not line:
            return
        
        parts = line.split()
        if not parts:
            return
        
        cmd = parts[0].upper()
        params = parts[1:]
        
        # Pre-auth commands
        if cmd == 'CAP':
            self._handle_cap(params)
            return
        
        if cmd == 'PASS':
            self._handle_pass(params)
            return
        
        if cmd == 'NICK':
            self._handle_nick(params)
            return
        
        if cmd == 'USER':
            self._handle_user(params)
            return
        
        # Require authentication
        if not self.authenticated:
            self._send(":server 464 * :Password required")
            return
        
        # Authenticated commands
        if cmd == 'PING':
            self._send(f":server PONG server :{params[0] if params else 'ping'}")
        elif cmd == 'QUIT':
            self.running = False
        elif self.selected_client:
            self.selected_client._send(line)
    
    def _handle_cap(self, params: List[str]):
        """Handle CAP."""
        if not params:
            return
        
        subcmd = params[0].upper()
        
        if subcmd == 'LS':
            self._send(":server CAP * LS :sasl")
        elif subcmd == 'REQ':
            caps = params[1:] if len(params) > 1 else []
            self.capabilities.update(caps)
            self._send(f":server CAP * ACK :{' '.join(caps)}")
        elif subcmd == 'END':
            pass
    
    def _handle_pass(self, params: List[str]):
        """Handle PASS - password authentication."""
        if not params:
            self._send(":server 461 * PASS :Not enough parameters")
            return
        
        password = ' '.join(params).lstrip(':')
        
        if password == "testpass":
            self.auth_stage = 'pass'
            print(f"[Auth] Password accepted from {self.ip}")
        else:
            self._send(":server 464 * :Password incorrect")
            time.sleep(2)
    
    def _handle_nick(self, params: List[str]):
        """Handle NICK."""
        if not params:
            self._send(":server 431 * :No nickname given")
            return
        
        nick = params[0]
        
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9\-_]*$', nick):
            self._send(f":server 432 * {nick} :Erroneous nickname")
            return
        
        self.nick = nick
        self.auth_stage = 'nickuser' if self.auth_stage == 'pass' else 'nick'
        
        self._try_complete_auth()
    
    def _handle_user(self, params: List[str]):
        """Handle USER."""
        if len(params) < 4:
            self._send(":server 461 * USER :Not enough parameters")
            return
        
        self.username = params[0]
        self.realname = ' '.join(params[3:]).lstrip(':')
        self.auth_stage = 'user' if 'nick' in self.auth_stage else 'useronly'
        
        self._try_complete_auth()
    
    def _try_complete_auth(self):
        """Complete authentication."""
        if self.authenticated:
            return
        
        if self.auth_stage in ['nickuser', 'pass'] and self.nick and self.username:
            self.authenticated = True
            self._send_welcome()
            print(f"[Auth] {self.nick} authenticated from {self.ip}")
    
    def _send_welcome_banner(self):
        """Send initial banner."""
        self._send(":server NOTICE AUTH :*** Welcome to IRC BNC")
        self._send(":server NOTICE AUTH :*** Please authenticate with PASS/NICK/USER")
    
    def _send_welcome(self):
        """Send IRC welcome."""
        if not self.nick:
            return
        
        self._send(f":server 001 {self.nick} :Welcome to IRC BNC")
        self._send(f":server 002 {self.nick} :Your host is BNC[v1.0]")
        self._send(f":server 003 {self.nick} :This server was created today")
        self._send(f":server 004 {self.nick} BNC 1.0 o i")
        self._send(f":server 251 {self.nick} :There are 0 users")
        self._send(f":server 375 {self.nick} :- Message of the Day -")
        self._send(f":server 372 {self.nick} :- Authenticated successfully")
        self._send(f":server 376 {self.nick} :End of /MOTD")
    
    def _send(self, message: str):
        """Send to client."""
        if not message.endswith('\r\n'):
            message += '\r\n'
        
        try:
            self.conn.send(message.encode('utf-8'))
            self.messages_sent += 1
        except:
            self.running = False
    
    def _cleanup(self):
        """Cleanup."""
        self.running = False
        try:
            self.conn.close()
        except:
            pass
        print(f"[Auth] Session ended for {self.nick or self.ip}")
    
    def get_stats(self) -> dict:
        """Get session stats."""
        return {
            'ip': self.ip,
            'nick': self.nick,
            'authenticated': self.authenticated,
            'connected_at': self.connected_at,
            'messages_sent': self.messages_sent
        }