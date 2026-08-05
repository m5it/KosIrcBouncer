"""
User Session with Multi-Network Support
"""

import socket
import threading
from typing import Optional, Dict, List

from shared import IrcMessage, BufferManager, MultiNetworkManager


class MultiNetworkSession(threading.Thread):
    """
    User session supporting multiple IRC networks.
    Can switch between networks, relay messages.
    """
    
    def __init__(self, conn: socket.socket, addr: tuple,
                 multi_net: MultiNetworkManager):
        super().__init__(daemon=True)
        
        self.conn = conn
        self.addr = addr
        self.multi_net = multi_net
        
        # Session state
        self.nick: Optional[str] = None
        self.authenticated = False
        self.current_network: Optional[str] = None
        
        # Running
        self.running = False
    
    def run(self):
        """Main session loop."""
        self.running = True
        
        self._send(":server 001 * :Welcome to Multi-Network BNC")
        self._send(":server NOTICE * :Use /NETWORKS to list networks")
        self._send(":server NOTICE * :Use /CONNECT <network> to connect")
        
        while self.running:
            try:
                data = self.conn.recv(4096)
                if not data:
                    break
                
                lines = data.decode('utf-8', errors='replace').strip().split('\r\n')
                for line in lines:
                    self._handle_line(line)
                    
            except Exception as e:
                print(f"[MultiSession] Error: {e}")
                break
        
        self._cleanup()
    
    def _handle_line(self, line: str):
        """Handle IRC command."""
        if not line:
            return
        
        parts = line.split()
        if not parts:
            return
        
        cmd = parts[0].upper()
        args = parts[1:]
        
        if cmd == 'NICK':
            self.nick = args[0] if args else "user"
            self._send(f":server 001 {self.nick} :Welcome")
        
        elif cmd == 'NETWORKS':
            self._send_networks()
        
        elif cmd == 'CONNECT':
            if args:
                self._connect_network(args[0])
        
        elif cmd == 'STATUS':
            self._send_status()
        
        elif cmd == 'SAY':
            if len(args) >= 2 and self.current_network:
                target = args[0]
                message = ' '.join(args[1:])
                self.multi_net.send_message(self.current_network, target, message)
                self._send(f":server NOTICE {self.nick} :Sent to {target}")
        
        elif cmd == 'QUIT':
            self.running = False
    
    def _send_networks(self):
        """Send network list."""
        self._send(f":server NOTICE {self.nick} :=== Networks ===")
        
        for name in self.multi_net.get_network_list():
            status = self.multi_net.get_status(name)
            if status:
                state = "connected" if status.connected else "disconnected"
                self._send(f":server NOTICE {self.nick} :  {name}: {state}")
                if status.connected:
                    self._send(f":server NOTICE {self.nick} :    Nick: {status.nick}")
                    self._send(f":server NOTICE {self.nick} :    Channels: {', '.join(status.channels)}")
        
        self._send(f":server NOTICE {self.nick} :===============")
    
    def _connect_network(self, network: str):
        """Connect to a network."""
        if self.multi_net.start_network(network):
            self.current_network = network
            self._send(f":server NOTICE {self.nick} :Connected to {network}")
        else:
            self._send(f":server NOTICE {self.nick} :Failed to connect to {network}")
    
    def _send_status(self):
        """Send multi-network status."""
        self._send(f":server NOTICE {self.nick} :=== Status ===")
        
        connected = self.multi_net.get_connected_networks()
        disconnected = self.multi_net.get_disconnected_networks()
        
        self._send(f":server NOTICE {self.nick} :Connected: {', '.join(connected) or 'None'}")
        self._send(f":server NOTICE {self.nick} :Disconnected: {', '.join(disconnected) or 'None'}")
        self._send(f":server NOTICE {self.nick} :Current: {self.current_network or 'None'}")
        self._send(f":server NOTICE {self.nick} :============")
    
    def _send(self, msg: str):
        """Send message to client."""
        if not msg.endswith('\r\n'):
            msg += '\r\n'
        try:
            self.conn.send(msg.encode('utf-8'))
        except:
            self.running = False
    
    def _cleanup(self):
        """Cleanup session."""
        self.running = False
        try:
            self.conn.close()
        except:
            pass