"""
User Session - Manages individual IRC client connections to BNC
"""

import socket
import threading
import time
import re
from typing import Optional, List, Callable, Dict
from datetime import datetime

from shared import IrcMessage, UserConnection
from client import IrcClient


class UserSession(threading.Thread):
    """
    Handles a single IRC client connection (e.g., HexChat).
    Bridges user commands to/from IRC network.
    """
    
    def __init__(self, conn: socket.socket, addr: tuple, 
                 irc_clients: Dict[str, IrcClient],
                 require_auth: bool = True):
        super().__init__(daemon=True)
        
        self.conn = conn
        self.addr = addr
        self.irc_clients = irc_clients  # Available IRC connections
        self.require_auth = require_auth
        
        # Session state
        self.authenticated = False
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.nick: Optional[str] = None
        self.realname: Optional[str] = None
        
        # IRC network selection
        self.current_network: Optional[str] = None
        self.selected_client: Optional[IrcClient] = None
        
        # Capabilities
        self.capabilities: List[str] = []
        self.cap_negotiation = False
        
        # Buffer playback
        self.connected_at = datetime.now()
        self.last_buffer_time: Optional[datetime] = None
        
        # Running state
        self.running = False
        self.ping_sent = False
        self.last_pong = time.time()
        
        # Statistics
        self.messages_sent = 0
        self.messages_received = 0
    
    def run(self) -> None:
        """Main session loop."""
        self.running = True
        print(f"[BNC] Session started for {self.addr}")
        
        try:
            self._send_welcome()
            
            buffer = ""
            while self.running:
                try:
                    data = self.conn.recv(4096)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='replace')
                    self.messages_received += 1
                    
                    # Process complete lines
                    while '\r\n' in buffer:
                        line, buffer = buffer.split('\r\n', 1)
                        self._handle_command(line.strip())
                    
                except socket.timeout:
                    # Check ping/pong
                    if self._should_ping():
                        self._send_ping()
                except Exception as e:
                    print(f"[BNC] Session error: {e}")
                    break
            
        except Exception as e:
            print(f"[BNC] Session exception: {e}")
        finally:
            self.disconnect()
    
    def _handle_command(self, line: str) -> None:
        """Handle command from IRC client."""
        if not line:
            return
        
        print(f"[BNC] <- {self.addr}: {line[:100]}")
        
        # Parse command
        parts = line.split()
        if not parts:
            return
        
        cmd = parts[0].upper()
        
        # CAP negotiation (before auth)
        if cmd == 'CAP':
            self._handle_cap(parts[1:])
            return
        
        # Authentication commands
        if cmd == 'PASS':
            self.password = ' '.join(parts[1:]).lstrip(':')
            return
        
        if cmd == 'NICK':
            self.nick = parts[1] if len(parts) > 1 else None
            # If already authenticated, change nick on IRC too
            if self.authenticated and self.selected_client:
                self.selected_client.change_nick(self.nick)
            return
        
        if cmd == 'USER':
            if len(parts) >= 5:
                self.username = parts[1]
                self.realname = ' '.join(parts[4:]).lstrip(':')
            self._try_authenticate()
            return
        
        # Require authentication for other commands
        if self.require_auth and not self.authenticated:
            self._send(":server 464 * :Password required")
            return
        
        # Authenticated commands
        handlers = {
            'PING': self._handle_ping,
            'PONG': self._handle_pong,
            'QUIT': self._handle_quit,
            'JOIN': self._handle_join,
            'PART': self._handle_part,
            'PRIVMSG': self._handle_privmsg,
            'NOTICE': self._handle_notice,
            'MODE': self._handle_mode,
            'WHO': self._handle_who,
            'WHOIS': self._handle_whois,
            'LIST': self._handle_list,
            'AWAY': self._handle_away,
            'TOPIC': self._handle_topic,
            'NAMES': self._handle_names,
            # BNC control commands
            'BNC': self._handle_bnc_command,
        }
        
        handler = handlers.get(cmd)
        if handler:
            handler(parts[1:], line)
        else:
            # Pass through to IRC
            if self.selected_client:
                self.selected_client._send(line)
    
    def _handle_cap(self, params: List[str]) -> None:
        """Handle CAP negotiation."""
        if not params:
            return
        
        subcmd = params[0].upper()
        
        if subcmd == 'LS':
            # List capabilities
            self._send(":server CAP * LS :multi-prefix extended-join account-notify")
            self.cap_negotiation = True
        
        elif subcmd == 'REQ':
            # Request capabilities
            caps = ' '.join(params[1:]).lstrip(':').split()
            self.capabilities.extend(caps)
            self._send(f":server CAP * ACK :{' '.join(caps)}")
        
        elif subcmd == 'END':
            # End negotiation
            self.cap_negotiation = False
            self._try_authenticate()
    
    def _try_authenticate(self) -> None:
        """Try to authenticate user."""
        if self.authenticated:
            return
        
        # Simple password check (should use hashed passwords in production)
        if self.require_auth:
            if not self.password:
                return  # Wait for PASS
            # TODO: Validate against user database
        
        self.authenticated = True
        print(f"[BNC] User authenticated: {self.nick}")
        
        # Send welcome
        self._send_welcome()
        
        # Send BNC status information
        self._send_connection_status()
        
        # If only one network, auto-connect
        if len(self.irc_clients) == 1:
            network = list(self.irc_clients.keys())[0]
            self._attach_to_network(network)
    
    def _send_connection_status(self) -> None:
        """Send BNC status information to the IRC client."""
        if not self.nick:
            return
        
        self._send(f":BNC NOTICE {self.nick} :Welcome to IRC BNC")
        self._send(f":BNC NOTICE {self.nick} :You are authenticated as {self.nick}")
        
        # Show available networks
        if self.irc_clients:
            self._send(f":BNC NOTICE {self.nick} :Available networks:")
            for name, client in self.irc_clients.items():
                if client.is_connected():
                    status = f"connected (nick: {client.state.current_nick})"
                else:
                    status = "disconnected"
                self._send(f":BNC NOTICE {self.nick} :  - {name}: {status}")
        else:
            self._send(f":BNC NOTICE {self.nick} :No networks configured")
        
        # Auto-attach hint or connect hint
        if len(self.irc_clients) == 1:
            network = list(self.irc_clients.keys())[0]
            self._send(f":BNC NOTICE {self.nick} :Auto-attaching to {network}...")
        elif len(self.irc_clients) > 1:
            self._send(f":BNC NOTICE {self.nick} :Use /BNC CONNECT <network> to attach to a network")
        
        self._send(f":BNC NOTICE {self.nick} :Use /BNC STATUS for status and /BNC HELP for commands")
    
    def _attach_to_network(self, network_name: str) -> None:
        """Attach to an IRC network."""
        client = self.irc_clients.get(network_name)
        if not client:
            self._send(f":server NOTICE * :Network {network_name} not found")
            return
        
        self.current_network = network_name
        self.selected_client = client
        
        # Add callback for messages from IRC
        client.add_message_callback(self._on_irc_message)
        
        # Send connection info
        if client.is_connected():
            self._send(f":server 001 {self.nick} :Welcome to BNC")
            self._send(f":server 002 {self.nick} :Your host is BNC, running version 1.0")
            self._send(f":server 003 {self.nick} :This server was created now")
            
            # Send nick info
            self._send(f":server 433 {self.nick} {client.state.current_nick}")
            
            # Play buffer
            self._send_buffer_playback(network_name)
            
            # Send joined channels
            for channel in client.get_channel_list():
                self._send(f":{client.state.current_nick}!user@host JOIN {channel}")
        else:
            self._send(f":server NOTICE * :Network {network_name} not connected")
    
    def _send_buffer_playback(self, network: str) -> None:
        """Send buffered messages to user."""
        # TODO: Implement buffer playback
        self._send(f":server NOTICE * :Buffer playback not yet implemented")
    
    def _on_irc_message(self, msg: IrcMessage) -> None:
        """Handle message from IRC network."""
        # Relay to user
        if msg.raw:
            self._send(msg.raw)
    
    def _handle_ping(self, params: List[str], line: str) -> None:
        """Handle PING from user."""
        if params:
            self._send(f":server PONG server :{params[0].lstrip(':')}")
    
    def _handle_pong(self, params: List[str], line: str) -> None:
        """Handle PONG from user."""
        self.last_pong = time.time()
        self.ping_sent = False
    
    def _handle_quit(self, params: List[str], line: str) -> None:
        """Handle QUIT."""
        reason = ' '.join(params).lstrip(':') if params else "Client quit"
        print(f"[BNC] User quit: {reason}")
        self.running = False
    
    def _handle_join(self, params: List[str], line: str) -> None:
        """Handle JOIN."""
        if not params:
            return
        
        channel = params[0].lstrip(':')
        if self.selected_client:
            self.selected_client.join_channel(channel)
    
    def _handle_part(self, params: List[str], line: str) -> None:
        """Handle PART."""
        if not params:
            return
        
        channel = params[0]
        reason = ' '.join(params[1:]).lstrip(':') if len(params) > 1 else ""
        if self.selected_client:
            self.selected_client.part_channel(channel, reason)
    
    def _handle_privmsg(self, params: List[str], line: str) -> None:
        """Handle PRIVMSG."""
        if len(params) < 2:
            return
        
        target = params[0]
        message = ' '.join(params[1:]).lstrip(':')
        
        if self.selected_client:
            self.selected_client.send_message(target, message)
    
    def _handle_notice(self, params: List[str], line: str) -> None:
        """Handle NOTICE."""
        # Pass through to IRC
        if self.selected_client:
            self.selected_client._send(line)
    
    def _handle_mode(self, params: List[str], line: str) -> None:
        """Handle MODE."""
        # Pass through to IRC
        if self.selected_client:
            self.selected_client._send(line)
    
    def _handle_who(self, params: List[str], line: str) -> None:
        """Handle WHO."""
        self._send(f":server 315 {self.nick} :End of /WHO list")
    
    def _handle_whois(self, params: List[str], line: str) -> None:
        """Handle WHOIS."""
        if params:
            target = params[0].lstrip(':')
            self._send(f":server 311 {self.nick} {target} user host * :Real name")
            self._send(f":server 318 {self.nick} {target} :End of /WHOIS list")
    
    def _handle_list(self, params: List[str], line: str) -> None:
        """Handle LIST."""
        self._send(f":server 323 {self.nick} :End of /LIST")
    
    def _handle_away(self, params: List[str], line: str) -> None:
        """Handle AWAY."""
        message = ' '.join(params).lstrip(':') if params else None
        if self.selected_client:
            self.selected_client.set_away(message)
    
    def _handle_topic(self, params: List[str], line: str) -> None:
        """Handle TOPIC."""
        # Pass through
        if self.selected_client:
            self.selected_client._send(line)
    
    def _handle_names(self, params: List[str], line: str) -> None:
        """Handle NAMES."""
        # Pass through
        if self.selected_client:
            self.selected_client._send(line)
    
    def _handle_bnc_command(self, params: List[str], line: str) -> None:
        """Handle BNC control commands."""
        if not params:
            return
        
        subcmd = params[0].upper()
        
        if subcmd == 'STATUS':
            self._send_status()
        elif subcmd == 'NETWORKS':
            self._send_networks()
        elif subcmd == 'CONNECT' and len(params) > 1:
            self._attach_to_network(params[1])
        elif subcmd == 'DISCONNECT':
            self._detach_from_network()
        else:
            self._send(f":server NOTICE {self.nick} :Unknown BNC command: {subcmd}")
    
    def _send_status(self) -> None:
        """Send BNC status."""
        self._send(f":server NOTICE {self.nick} :=== BNC Status ===")
        self._send(f":server NOTICE {self.nick} :Connected: {self.authenticated}")
        self._send(f":server NOTICE {self.nick} :Network: {self.current_network or 'None'}")
        self._send(f":server NOTICE {self.nick} :IRC Connected: {self.selected_client.is_connected() if self.selected_client else False}")
        self._send(f":server NOTICE {self.nick} :=================")
    
    def _send_networks(self) -> None:
        """Send available networks."""
        self._send(f":server NOTICE {self.nick} :Available networks:")
        for name in self.irc_clients.keys():
            client = self.irc_clients[name]
            status = "connected" if client.is_connected() else "disconnected"
            self._send(f":server NOTICE {self.nick} :  {name} ({status})")
    
    def _detach_from_network(self) -> None:
        """Detach from current network."""
        if self.selected_client:
            self.selected_client = None
            self.current_network = None
            self._send(f":server NOTICE {self.nick} :Detached from network")
    
    def _should_ping(self) -> bool:
        """Check if we should send PING."""
        return time.time() - self.last_pong > 60 and not self.ping_sent
    
    def _send_ping(self) -> None:
        """Send PING to client."""
        self._send(f":server PING :{int(time.time())}")
        self.ping_sent = True
    
    def _send_welcome(self) -> None:
        """Send welcome messages."""
        if not self.nick:
            return
        
        self._send(f":server 001 {self.nick} :Welcome to IRC BNC")
        self._send(f":server 002 {self.nick} :Your host is BNC, running version 1.0")
        self._send(f":server 003 {self.nick} :This server was created now")
        self._send(f":server 004 {self.nick} BNC 1.0 o o")
        self._send(f":server 251 {self.nick} :There are 0 users and 0 invisible on 1 servers")
        self._send(f":server 375 {self.nick} :BNC Message of the Day")
        self._send(f":server 372 {self.nick} :- Welcome to IRC BNC!")
        self._send(f":server 372 {self.nick} :- Type /BNC NETWORKS to see available networks")
        self._send(f":server 372 {self.nick} :- Type /BNC CONNECT <network> to connect")
        self._send(f":server 376 {self.nick} :End of /MOTD command")
    
    def _send(self, message: str) -> None:
        """Send message to IRC client."""
        if not message.endswith('\r\n'):
            message += '\r\n'
        
        try:
            self.conn.send(message.encode('utf-8'))
            self.messages_sent += 1
            print(f"[BNC] -> {self.addr}: {message[:100].strip()}")
        except Exception as e:
            print(f"[BNC] Send error: {e}")
            self.running = False
    
    def disconnect(self) -> None:
        """Disconnect user session."""
        self.running = False
        if self.selected_client:
            # Remove callback
            self.selected_client._on_message = [
                cb for cb in self.selected_client._on_message 
                if cb != self._on_irc_message
            ]
        try:
            self.conn.close()
        except:
            pass
        print(f"[BNC] Session ended for {self.addr}")
    
    def get_stats(self) -> dict:
        """Get session statistics."""
        return {
            'address': self.addr,
            'nick': self.nick,
            'authenticated': self.authenticated,
            'network': self.current_network,
            'connected_at': self.connected_at,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received
        }