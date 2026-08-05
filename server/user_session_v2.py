"""
Enhanced User Session v2 - Full buffering and detach/reattach support
"""

import socket
import threading
import time
import re
from typing import Optional, List, Dict, Set, Callable
from datetime import datetime
from collections import defaultdict

from shared import IrcMessage, BufferManager, BufferEntry
from client import IrcClient


class UserSessionV2(threading.Thread):
    """
    Enhanced user session with full buffering and detach/reattach.
    
    Features:
    - Message buffering with playback
    - Real-time relay (user <-> IRC)
    - Detach mode: bot continues, buffers messages
    - Reattach: send buffered history
    - Nick/channel/user tracking
    """
    
    def __init__(self, conn: socket.socket, addr: tuple,
                 irc_clients: Dict[str, IrcClient],
                 buffer_manager: BufferManager,
                 require_auth: bool = True):
        super().__init__(daemon=True, name=f"Session-{addr[1]}")
        
        self.conn = conn
        self.addr = addr
        self.irc_clients = irc_clients
        self.buffer = buffer_manager
        self.require_auth = require_auth
        
        # Session state
        self.authenticated = False
        self.username: Optional[str] = None
        self.nick: Optional[str] = None
        self.realname: Optional[str] = None
        self.away_message: Optional[str] = None
        
        # Network selection
        self.current_network: Optional[str] = None
        self.selected_client: Optional[IrcClient] = None
        
        # Tracking
        self.joined_channels: Set[str] = set()
        self.known_users: Dict[str, dict] = {}  # nick -> user info
        self.channel_users: Dict[str, Set[str]] = defaultdict(set)
        
        # Buffering
        self.session_start = datetime.now()
        self.last_seen: Optional[datetime] = None
        self.detached = False
        
        # Capabilities
        self.capabilities: Set[str] = set()
        self.cap_negotiation = False
        
        # Connection
        self.running = False
        self._lock = threading.Lock()
        
        # Stats
        self.messages_sent = 0
        self.messages_received = 0
        self.buffer_played_back = 0
    
    def run(self):
        """Main session loop."""
        self.running = True
        print(f"[Session] Started for {self.addr}")
        
        try:
            self._send_welcome()
            
            buffer = ""
            while self.running:
                try:
                    self.conn.settimeout(1.0)
                    data = self.conn.recv(4096)
                    
                    if not data:
                        # Client disconnected
                        self._detach()
                        break
                    
                    buffer += data.decode('utf-8', errors='replace')
                    self.messages_received += len(data)
                    
                    # Process lines
                    while '\r\n' in buffer:
                        line, buffer = buffer.split('\r\n', 1)
                        self._handle_client_command(line.strip())
                        
                except socket.timeout:
                    # Check for buffered messages to relay
                    self._relay_buffered_messages()
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[Session] Error: {e}")
                    break
                    
        except Exception as e:
            print(f"[Session] Exception: {e}")
        finally:
            self._cleanup()
    
    def _detach(self):
        """Enter detach mode - bot continues, we buffer."""
        print(f"[Session] {self.nick} detached")
        self.detached = True
        self.last_seen = datetime.now()
        
        # Keep IRC callbacks but mark as detached
        # Bot continues running, messages go to buffer
    
    def _reattach(self):
        """Reattach session - send buffered history."""
        print(f"[Session] {self.nick} reattached")
        self.detached = False
        
        if self.last_seen and self.current_network:
            self._send_buffer_playback(self.last_seen)
        
        self._send(f":server NOTICE {self.nick} :Reattached. Missed messages above.")
    
    def _send_buffer_playback(self, since: datetime):
        """Send buffered messages since timestamp."""
        if not self.current_network:
            return
        
        # Get all channel buffers for this network
        channels = self.joined_channels if self.joined_channels else [f"#{self.current_network}"]
        
        for channel in channels:
            buf = self.buffer.get_buffer(self.current_network, channel)
            missed = buf.get_since(since)
            
            for entry in missed:
                # Format based on type
                if entry.msg_type == "PRIVMSG":
                    self._send(f":{self.selected_client.state.current_nick}!user@host PRIVMSG {channel} :[BACKLOG] {entry.message}")
                elif entry.msg_type == "JOIN":
                    self._send(f":server 331 {self.nick} {channel} :Topic")
                self.buffer_played_back += 1
        
        self._send(f":server 323 {self.nick} :End of buffer playback")
    
    def _relay_buffered_messages(self):
        """Relay real-time messages from buffer."""
        if self.detached or not self.current_network:
            return
        
        # Check for new messages in joined channels
        for channel in self.joined_channels:
            buf = self.buffer.get_buffer(self.current_network, channel)
            # Get messages since last check
            # This is simplified - in production use events/callbacks
    
    def _handle_client_command(self, line: str):
        """Handle command from IRC client."""
        if not line:
            return
        
        parts = line.split()
        if not parts:
            return
        
        cmd = parts[0].upper()
        
        # Pre-authentication commands
        if cmd == 'CAP':
            self._handle_cap(parts[1:])
            return
        elif cmd == 'PASS':
            self._handle_pass(parts[1:])
            return
        elif cmd == 'NICK':
            self._handle_nick(parts[1:])
            return
        elif cmd == 'USER':
            self._handle_user(parts[1:])
            return
        
        # Require authentication
        if self.require_auth and not self.authenticated:
            self._send(":server 464 * :Password required")
            return
        
        # Authenticated commands - relay to IRC
        handlers = {
            'PING': self._handle_ping,
            'PONG': self._handle_pong,
            'QUIT': self._handle_quit,
            'JOIN': self._handle_join,
            'PART': self._handle_part,
            'PRIVMSG': self._handle_privmsg,
            'NOTICE': self._handle_notice,
            'MODE': self._handle_mode,
            'TOPIC': self._handle_topic,
            'WHO': self._handle_who,
            'WHOIS': self._handle_whois,
            'AWAY': self._handle_away,
            'NICK': self._handle_nick_change,
            'LIST': self._handle_list,
            'INVITE': self._handle_invite,
            'KICK': self._handle_kick,
            'BNC': self._handle_bnc,
        }
        
        handler = handlers.get(cmd)
        if handler:
            handler(parts[1:], line)
        else:
            # Unknown command - pass through if attached
            if self.selected_client and not self.detached:
                self.selected_client._send(line)
    
    def _handle_cap(self, params: List[str]):
        """Handle CAP negotiation."""
        if not params:
            return
        
        subcmd = params[0].upper()
        
        if subcmd == 'LS':
            caps = "multi-prefix extended-join account-notify away-notify"
            self._send(f":server CAP * LS :{caps}")
        elif subcmd == 'REQ':
            requested = ' '.join(params[1:]).strip(':').split()
            self.capabilities.update(requested)
            self._send(f":server CAP * ACK :{' '.join(requested)}")
        elif subcmd == 'END':
            self.cap_negotiation = False
    
    def _handle_pass(self, params: List[str]):
        """Handle PASS."""
        if params:
            password = ' '.join(params).lstrip(':')
            # TODO: Validate password
            self.authenticated = True
    
    def _handle_nick(self, params: List[str]):
        """Handle initial NICK."""
        if params:
            self.nick = params[0]
            self._try_complete_auth()
    
    def _handle_user(self, params: List[str]):
        """Handle USER."""
        if len(params) >= 4:
            self.username = params[0]
            self.realname = ' '.join(params[3:]).lstrip(':')
            self._try_complete_auth()
    
    def _try_complete_auth(self):
        """Complete authentication if ready."""
        if self.authenticated and self.nick and self.username:
            self._send_welcome()
    
    def _handle_ping(self, params: List[str], raw: str):
        """Handle PING."""
        if params:
            self._send(f":server PONG server :{params[0].lstrip(':')}")
    
    def _handle_pong(self, params: List[str], raw: str):
        """Handle PONG."""
        pass  # Update last activity
    
    def _handle_quit(self, params: List[str], raw: str):
        """Handle QUIT."""
        reason = ' '.join(params).lstrip(':') if params else "Client quit"
        if self.selected_client:
            self.selected_client._send(f"QUIT :{reason}")
        self.running = False
    
    def _handle_join(self, params: List[str], raw: str):
        """Handle JOIN - user joining channel."""
        if not params or not self.selected_client:
            return
        
        channel = params[0].lstrip(':')
        
        # Track locally
        self.joined_channels.add(channel.lower())
        
        # Relay to IRC
        self.selected_client.join_channel(channel)
        
        # Send channel info
        self._send(f":{self.nick}!{self.username}@host JOIN {channel}")
        
        # Topic
        self._send(f":server 332 {self.nick} {channel} :Welcome to {channel}")
        
        # Names list
        users = self.channel_users.get(channel.lower(), set())
        user_list = ' '.join(users) if users else f"@{self.nick}"
        self._send(f":server 353 {self.nick} = {channel} :{user_list}")
        self._send(f":server 366 {self.nick} {channel} :End of /NAMES list")
    
    def _handle_part(self, params: List[str], raw: str):
        """Handle PART."""
        if not params or not self.selected_client:
            return
        
        channel = params[0]
        reason = ' '.join(params[1:]).lstrip(':') if len(params) > 1 else ""
        
        self.joined_channels.discard(channel.lower())
        self.selected_client.part_channel(channel, reason)
        
        self._send(f":{self.nick}!{self.username}@host PART {channel} :{reason}")
    
    def _handle_privmsg(self, params: List[str], raw: str):
        """Handle PRIVMSG."""
        if len(params) < 2 or not self.selected_client:
            return
        
        target = params[0]
        message = ' '.join(params[1:]).lstrip(':')
        
        # Relay to IRC
        self.selected_client.send_message(target, message)
        
        # Echo to client (IRC doesn't echo)
        self._send(f":{self.nick}!{self.username}@host PRIVMSG {target} :{message}")
    
    def _handle_notice(self, params: List[str], raw: str):
        """Handle NOTICE."""
        if self.selected_client:
            self.selected_client._send(raw)
    
    def _handle_mode(self, params: List[str], raw: str):
        """Handle MODE."""
        if self.selected_client:
            self.selected_client._send(raw)
    
    def _handle_topic(self, params: List[str], raw: str):
        """Handle TOPIC."""
        if self.selected_client:
            self.selected_client._send(raw)
    
    def _handle_who(self, params: List[str], raw: str):
        """Handle WHO."""
        # Simplified WHO response
        if params:
            target = params[0].lstrip(':')
            self._send(f":server 352 {self.nick} {target} user host server {self.nick} H :0 Real name")
            self._send(f":server 315 {self.nick} {target} :End of /WHO list")
    
    def _handle_whois(self, params: List[str], raw: str):
        """Handle WHOIS."""
        if not params:
            return
        
        target = params[0].lstrip(':')
        
        # WHOIS responses
        self._send(f":server 311 {self.nick} {target} user host * :Real Name")
        self._send(f":server 312 {self.nick} {target} server :Server Info")
        self._send(f":server 318 {self.nick} {target} :End of /WHOIS list")
    
    def _handle_away(self, params: List[str], raw: str):
        """Handle AWAY."""
        if not self.selected_client:
            return
        
        if params:
            self.away_message = ' '.join(params).lstrip(':')
            self.selected_client.set_away(self.away_message)
            self._send(f":server 306 {self.nick} :You have been marked as being away")
        else:
            self.away_message = None
            self.selected_client.set_away(None)
            self._send(f":server 305 {self.nick} :You are no longer marked as being away")
    
    def _handle_nick_change(self, params: List[str], raw: str):
        """Handle NICK change."""
        if not params or not self.selected_client:
            return
        
        new_nick = params[0]
        old_nick = self.nick
        self.nick = new_nick
        
        self.selected_client.change_nick(new_nick)
        self._send(f":{old_nick}!{self.username}@host NICK :{new_nick}")
    
    def _handle_list(self, params: List[str], raw: str):
        """Handle LIST."""
        # List joined channels
        for channel in self.joined_channels:
            self._send(f":server 322 {self.nick} {channel} 1 :Topic")
        self._send(f":server 323 {self.nick} :End of /LIST")
    
    def _handle_invite(self, params: List[str], raw: str):
        """Handle INVITE."""
        if self.selected_client:
            self.selected_client._send(raw)
    
    def _handle_kick(self, params: List[str], raw: str):
        """Handle KICK."""
        if self.selected_client:
            self.selected_client._send(raw)
    
    def _handle_bnc(self, params: List[str], raw: str):
        """Handle BNC control commands."""
        if not params:
            return
        
        cmd = params[0].upper()
        
        if cmd == 'DETACH':
            self._detach()
            self._send(f":server NOTICE {self.nick} :Detached from IRC. Bot continues.")
        elif cmd == 'ATTACH':
            self._reattach()
        elif cmd == 'STATUS':
            self._send_status()
        elif cmd == 'NETWORKS':
            self._send_networks()
        elif cmd == 'BUFFER':
            self._send_buffer_info()
    
    def _send_status(self):
        """Send BNC status."""
        self._send(f":server NOTICE {self.nick} :=== BNC Status ===")
        self._send(f":server NOTICE {self.nick} :Nick: {self.nick}")
        self._send(f":server NOTICE {self.nick} :Network: {self.current_network or 'None'}")
        self._send(f":server NOTICE {self.nick} :Detached: {self.detached}")
        self._send(f":server NOTICE {self.nick} :Channels: {', '.join(self.joined_channels)}")
        self._send(f":server NOTICE {self.nick} :Messages sent: {self.messages_sent}")
        self._send(f":server NOTICE {self.nick} :=================")
    
    def _send_networks(self):
        """Send available networks."""
        self._send(f":server NOTICE {self.nick} :Available networks:")
        for name, client in self.irc_clients.items():
            status = "connected" if client.is_connected() else "disconnected"
            current = " [current]" if name == self.current_network else ""
            self._send(f":server NOTICE {self.nick} :  {name} ({status}){current}")
    
    def _send_buffer_info(self):
        """Send buffer information."""
        if not self.current_network:
            return
        
        total = 0
        for channel in self.joined_channels:
            buf = self.buffer.get_buffer(self.current_network, channel)
            total += len(buf)
        
        self._send(f":server NOTICE {self.nick} :Buffered messages: {total}")
        self._send(f":server NOTICE {self.nick} :Played back: {self.buffer_played_back}")
    
    def _send_welcome(self):
        """Send IRC welcome messages."""
        if not self.nick:
            return
        
        self._send(f":server 001 {self.nick} :Welcome to IRC BNC")
        self._send(f":server 002 {self.nick} :Your host is BNC[v1.0], running mode")
        self._send(f":server 003 {self.nick} :This server was created today")
        self._send(f":server 004 {self.nick} BNC 1.0 o i")
        self._send(f":server 251 {self.nick} :There are 0 users and 1 invisibles on 1 servers")
        self._send(f":server 375 {self.nick} :- BNC Message of the Day -")
        self._send(f":server 372 {self.nick} :- Welcome! Use /BNC NETWORKS to see networks")
        self._send(f":server 372 {self.nick} :- Use /BNC DETACH to detach (bot continues)")
        self._send(f":server 376 {self.nick} :End of /MOTD command")
    
    def _send(self, message: str):
        """Send message to client."""
        if not message.endswith('\r\n'):
            message += '\r\n'
        
        try:
            with self._lock:
                self.conn.send(message.encode('utf-8', errors='replace'))
                self.messages_sent += len(message)
        except:
            self.running = False
    
    def _cleanup(self):
        """Cleanup session."""
        self.running = False
        self.detached = True  # Mark as detached
        
        # Don't disconnect IRC - bot continues!
        print(f"[Session] {self.nick} cleaned up (IRC bot continues)")
        
        try:
            self.conn.close()
        except:
            pass
    
    def attach_to_network(self, network_name: str) -> bool:
        """Attach to an IRC network."""
        client = self.irc_clients.get(network_name)
        if not client:
            return False
        
        self.current_network = network_name
        self.selected_client = client
        
        # Add callback for IRC events
        client.add_message_callback(self._on_irc_event)
        
        # Send connection burst
        if client.is_connected():
            self._send_connection_burst(client)
        
        return True
    
    def _on_irc_event(self, msg: IrcMessage):
        """Handle event from IRC."""
        if self.detached:
            return  # Don't relay when detached
        
        # Relay to client
        if msg.raw:
            self._send(msg.raw)
    
    def _send_connection_burst(self, client: IrcClient):
        """Send initial connection info."""
        nick = client.state.current_nick
        
        # Welcome
        self._send(f":server 001 {self.nick} :Welcome to BNC via {self.current_network}")
        
        # Send nick
        self._send(f":server NICK {nick}")
        
        # Joined channels
        for channel in client.get_channel_list():
            self._send(f":{nick}!user@host JOIN {channel}")
            self.joined_channels.add(channel.lower())
        
        # Buffer playback
        self._send_buffer_playback(self.session_start)
    
    def get_stats(self) -> dict:
        """Get session statistics."""
        return {
            'nick': self.nick,
            'network': self.current_network,
            'detached': self.detached,
            'channels': len(self.joined_channels),
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'buffer_played': self.buffer_played_back,
            'session_duration': str(datetime.now() - self.session_start)
        }