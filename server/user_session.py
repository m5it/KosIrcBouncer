"""
User Session - Manages individual IRC client connections to BNC
"""

import socket
import threading
import time
import re
from typing import Optional, List, Callable, Dict
from datetime import datetime

from shared import IrcMessage, UserConnection, UserDatabase, PasswordHasher
from client import IrcClient


class UserSession(threading.Thread):
    """
    Handles a single IRC client connection (e.g., HexChat).
    Bridges user commands to/from IRC network.
    """
    
    def __init__(self, conn: socket.socket, addr: tuple,
                 irc_clients: Dict[str, IrcClient],
                 require_auth: bool = True,
                 user_db: Optional[UserDatabase] = None,
                 buffer_manager=None,
                 command_handler=None):
        super().__init__(daemon=True)

        self.conn = conn
        self.addr = addr
        self.irc_clients = irc_clients  # Available IRC connections
        self.require_auth = require_auth
        self.user_db = user_db
        self.buffer_manager = buffer_manager
        self.command_handler = command_handler

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

        # Track channel joins/parts even before full authentication so they
        # can be replayed or persisted after login.
        if cmd == 'JOIN' and not self.authenticated:
            channels = parts[1].lstrip(':').split(',') if len(parts) > 1 else []
            for channel in channels:
                if channel:
                    self._save_channel(channel)
            return

        if cmd == 'PART' and not self.authenticated:
            channels = parts[1].split(',') if len(parts) > 1 else []
            for channel in channels:
                if channel:
                    self._remove_channel(channel)
            return
        
        # Authenticated commands (BNC LOGIN and PASS may run before auth)
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
            # BNC control commands can authenticate the user; don't reject them
            # for being unauthenticated.
            if self.require_auth and not self.authenticated and cmd != 'BNC':
                self._send(":server 464 * :Password required")
                return
            handler(parts[1:], line)
            return

        # Unknown command: require auth before passing through to IRC
        if self.require_auth and not self.authenticated:
            self._send(":server 464 * :Password required")
            return

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
        """Try to authenticate user with PASS or user database."""
        if self.authenticated:
            return

        if self.require_auth:
            if not self.password:
                return  # Wait for PASS

            if not self._check_password(self.password):
                self._send(":server 464 * :Password required")
                print(f"[BNC] Authentication failed for {self.addr}")
                return

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

    def _check_password(self, password: str) -> bool:
        """Verify supplied password against configured users."""
        if not self.user_db:
            # No user database: accept any non-empty password (testing mode)
            return bool(password)

        # Try matching by username if one was supplied, otherwise try all users.
        client_ip = self.addr[0]
        if self.username and self.username in self.user_db.users:
            return self.user_db.authenticate(self.username, password, client_ip) is not None

        for username, user in self.user_db.users.items():
            if user.check_password(password):
                self.username = username
                return True
        return False
    
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

        # If already attached to this network, detach first so we reset state.
        if self.current_network == network_name and self.selected_client is client:
            self._detach_from_network()

        self.current_network = network_name
        self.selected_client = client

        # Add callback for messages from IRC
        client.add_message_callback(self._on_irc_message)

        # Send connection info
        if client.is_connected():
            # Replay the real registration burst (001/002/003/.../376/MOTD/
            # NickServ notices) that the upstream IRC server sent.  This lets
            # the IRC client know it is attached to a fully registered session.
            for line in client.state.registration_burst:
                self._send(line)

            # Re-emit our current nick as a NICK command so the client knows
            # what nickname this session is using.
            self._send(f":{client.state.current_nick}!user@host NICK :{client.state.current_nick}")

            # Play buffer
            self._send_buffer_playback(network_name)

            # Re-join channels the user had previously saved, plus channels the
            # upstream client is already in.
            # Try to determine our real hostmask. Prefer the host field from a
            # WHO reply for our own nick, otherwise fall back to the cached
            # hostmask or a generic placeholder.
            own_nick_lower = (client.state.current_nick or "").lower()
            hostmask = client.state.hostmask
            if not hostmask:
                for channel in all_channels:
                    for line in client.state.channel_who.get(channel.lower(), []):
                        msg = IrcMessage.parse(line)
                        if len(msg.params) >= 8 and msg.params[6].lower() == own_nick_lower:
                            ident = msg.params[2]
                            host = msg.params[3]
                            hostmask = f"{client.state.current_nick}!{ident}@{host}"
                            client.state.hostmask = hostmask
                            break
                    if hostmask:
                        break
            if not hostmask:
                hostmask = f"{client.state.current_nick}!user@host"
            saved = self._get_saved_channels(network_name)
            irc_channels = set(client.get_channel_list())
            all_channels = irc_channels | saved
            for channel in sorted(all_channels):
                channel_lower = channel.lower()
                if channel not in irc_channels:
                    client.join_channel(channel)
                self._send(f":{hostmask} JOIN {channel}")

                # Replay channel metadata: modes, names, and WHO replies.
                # This is exactly what HexChat expects after a JOIN.
                for line in client.state.channel_modes.get(channel_lower, []):
                    self._send(line)

                # Send a fresh, live 353/366 names list for this channel.
                for line in client.build_names_list(channel):
                    self._send(line)

                for line in client.state.channel_who.get(channel_lower, []):
                    self._send(line)
        else:
            self._send(f":server NOTICE * :Network {network_name} not connected")

    def _send_buffer_playback(self, network: str) -> None:
        """Send buffered messages to user since their last detach/login."""
        if not self.buffer_manager:
            self._send(f":server NOTICE * :Buffer playback not available")
            return

        since = self.last_buffer_time
        self.last_buffer_time = datetime.now()

        buf = self.buffer_manager.get_buffer(network, "*")
        entries = buf.get_since(since) if since else buf.get_last(100)

        if not entries:
            self._send(f":server NOTICE * :No buffered messages")
            return

        self._send(f":server NOTICE * :Replay {len(entries)} buffered message(s)")
        for entry in entries:
            self._send(entry.message)
    
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

        for channel in params[0].lstrip(':').split(','):
            if not channel:
                continue
            if self.selected_client:
                self.selected_client.join_channel(channel)
            self._save_channel(channel)

    def _handle_part(self, params: List[str], line: str) -> None:
        """Handle PART."""
        if not params:
            return

        for channel in params[0].split(','):
            if not channel:
                continue
            reason = ' '.join(params[1:]).lstrip(':') if len(params) > 1 else ""
            if self.selected_client:
                self.selected_client.part_channel(channel, reason)
            self._remove_channel(channel)
    
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
        """Handle WHO by forwarding to IRC and replaying any cached replies."""
        if not params:
            self._send(f":server 315 {self.nick} :End of /WHO list")
            return

        target = params[0].lstrip(':').lower()

        # If we have a cached WHO reply burst for a channel, serve it directly.
        if target.startswith('#') and self.selected_client:
            cached = self.selected_client.state.channel_who.get(target, [])
            if cached:
                for cached_line in cached:
                    self._send(cached_line)
                return

        # Forward to IRC. Replies will be buffered and relayed by _on_irc_message.
        if self.selected_client:
            self.selected_client._send(line)

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
        if not params:
            return
        channel = params[0].lstrip(':').lower()

        # Serve cached names if available, otherwise pass through to IRC.
        if self.selected_client and channel in self.selected_client.state.channel_names:
            for cached_line in self.selected_client.state.channel_names[channel]:
                self._send(cached_line)
            return

        if self.selected_client:
            self.selected_client._send(line)

    def _handle_bnc_command(self, params: List[str], line: str) -> None:
        """Handle BNC control commands."""
        if not self.command_handler:
            # Fallback for sessions without a command handler
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
            return

        # Use the full BncCommandHandler.  It expects the raw line to start
        # with 'BNC' and uses parts[1] as the actual subcommand.
        command_line = line if line.upper().startswith('BNC') else 'BNC ' + ' '.join(params)
        for response in self.command_handler.handle(self, command_line):
            self._send(response)

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

    def _get_user_account(self):
        """Return the configured user account for this session, if any."""
        if not self.user_db or not self.username:
            return None
        return self.user_db.get_user(self.username)

    def _get_saved_channels(self, network: str):
        """Return the set of channels the user has saved for a network."""
        account = self._get_user_account()
        if not account:
            return set()
        return account.saved_channels.get(network, set())

    def _save_channel(self, channel: str) -> None:
        """Persist a channel in the user's saved channel list."""
        account = self._get_user_account()
        if not account:
            return
        # Ensure each saved entry is a single channel, never a comma list.
        for ch in channel.split(','):
            ch = ch.strip().lower()
            if not ch:
                continue
            if self.current_network:
                network = self.current_network
            elif len(self.irc_clients) == 1:
                network = list(self.irc_clients.keys())[0]
            else:
                return
            account.saved_channels.setdefault(network, set()).add(ch)
        self.user_db.save()

    def _remove_channel(self, channel: str) -> None:
        """Remove a channel from the user's saved channel list."""
        account = self._get_user_account()
        if not account:
            return
        for ch in channel.split(','):
            ch = ch.strip().lower()
            if not ch:
                continue
            if self.current_network:
                network = self.current_network
            elif len(self.irc_clients) == 1:
                network = list(self.irc_clients.keys())[0]
            else:
                return
            account.saved_channels.get(network, set()).discard(ch)
        self.user_db.save()

    def _detach_from_network(self) -> None:
        """Detach from current network."""
        if self.selected_client:
            # Remove our message callback so traffic is buffered instead of
            # being relayed to a disconnected client.
            try:
                self.selected_client._on_message = [
                    cb for cb in self.selected_client._on_message
                    if cb != self._on_irc_message
                ]
            except Exception:
                pass
            self.selected_client = None
            self.current_network = None
            self.last_buffer_time = datetime.now()
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