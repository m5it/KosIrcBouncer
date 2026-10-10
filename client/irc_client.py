"""
Main IRC Client - Bot that connects to IRC networks
"""

import threading
import time
import re
import base64
from typing import Optional, List, Callable, Dict, Set
from datetime import datetime
from dataclasses import dataclass, field

from config import IrcNetworkConfig
from shared import IrcMessage, ChannelMessage, BufferManager
from client.connection import IrcConnection


@dataclass
class IrcState:
    """Current IRC connection state."""
    connected: bool = False
    registered: bool = False
    nick: str = ""
    current_nick: str = ""
    channels: Dict[str, dict] = field(default_factory=dict)
    users: Dict[str, dict] = field(default_factory=dict)
    away_message: Optional[str] = None
    registration_burst: List[str] = field(default_factory=list)
    # Last seen 353/366 burst per channel, keyed by lowercase channel name.
    channel_names: Dict[str, List[str]] = field(default_factory=dict)
    # Last seen 352/315 WHO reply burst per channel, keyed by lowercase channel name.
    channel_who: Dict[str, List[str]] = field(default_factory=dict)
    # Last seen 324/329 channel mode burst per channel, keyed by lowercase channel name.
    channel_modes: Dict[str, List[str]] = field(default_factory=dict)
    # Our own hostmask as reported by the IRC server (e.g. from 001/002 or 396).
    hostmask: Optional[str] = None
    # Live channel user lists: channel_lower -> {nick_lower: prefix_char}.
    channel_users: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # IRC server name used as prefix for generated replies.
    server_name: str = ""


class IrcClient:
    """
    High-level IRC client for BNC.
    Connects to IRC networks, handles protocol, buffers messages.
    """
    
    def __init__(self, config: IrcNetworkConfig, buffer_manager: BufferManager):
        self.config = config
        self.buffer = buffer_manager
        
        self.connection = IrcConnection(
            host=config.host,
            port=config.port,
            use_ssl=config.ssl
        )
        
        self.state = IrcState()
        self.state.nick = config.nick
        self.state.current_nick = config.nick
        
        # Event callbacks
        self._on_message: List[Callable[[IrcMessage], None]] = []
        self._on_connect: List[Callable[[], None]] = []
        self._on_disconnect: List[Callable[[], None]] = []

        # Threads
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Auto-reconnect
        self._reconnect_attempts = 0
        self._max_reconnect_delay = 300  # 5 minutes
        self._last_server_pong = 0.0
        self._last_sent_ping = 0.0

        # Auto-op masks aggregated from all attached BNC users.
        # channel_lower -> set of nick!user@host masks.
        self._auto_op_masks: Dict[str, Set[str]] = {}
        self._auto_op_lock = threading.Lock()
    
    def start(self) -> None:
        """Start IRC client in background thread."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._run)
        self._worker_thread.daemon = True
        self._worker_thread.start()
    
    def stop(self) -> None:
        """Stop IRC client."""
        self._running = False
        self.connection.disconnect()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
    
    def _run(self) -> None:
        """Main client loop with auto-reconnect."""
        while self._running:
            if self._connect_and_run():
                # Clean disconnect
                self._reconnect_attempts = 0
                if not self._running:
                    break
            else:
                # Connection failed
                if not self._running:
                    break
            
            # Auto-reconnect
            if self.config.auto_reconnect and self._running:
                delay = min(
                    self.config.reconnect_delay * (2 ** self._reconnect_attempts),
                    self._max_reconnect_delay
                )
                self._reconnect_attempts += 1
                print(f"[IRC] Reconnecting in {delay}s... (attempt {self._reconnect_attempts})")
                time.sleep(delay)
    
    def _connect_and_run(self) -> bool:
        """Connect and handle IRC session."""
        # Reset state
        # Reset state and create a fresh connection object so reconnects start
        # from a clean socket.
        self.state = IrcState()
        self.state.nick = self.config.nick
        self.state.current_nick = self.config.nick
        self.connection = IrcConnection(
            host=self.config.host,
            port=self.config.port,
            use_ssl=self.config.ssl,
        )
        self._last_server_pong = time.time()
        self._last_sent_ping = 0.0

        # Connect
        print(f"[IRC] Connecting to {self.config.host}:{self.config.port}...")
        if not self.connection.connect():
            return False

        # Add callback for incoming messages
        self.connection.add_callback(self._on_raw_message)

        # Send registration
        self._send_registration()

        # Wait for connection to complete/fail
        timeout = 60
        start = time.time()
        while self._running and self.connection.is_connected():
            if self.state.registered:
                # Connected successfully - keep running and maintain keepalive
                self._on_connected()
                while self._running and self.connection.is_connected():
                    self._maintain_keepalive()
                    time.sleep(0.5)
                return True

            if time.time() - start > timeout:
                print("[IRC] Registration timeout")
                break
            time.sleep(0.1)

        self.connection.disconnect()
        return False
    
    def _send_registration(self) -> None:
        """Send IRC registration commands."""
        # CAP for SASL if needed
        if self.config.sasl_enabled:
            self._send("CAP REQ :sasl")
        
        # NICK and USER
        self._send(f"NICK {self.state.nick}")
        self._send(f"USER {self.config.user} 0 * :{self.config.realname}")
        
        # Server password (not SASL)
        if self.config.password and not self.config.sasl_enabled:
            self._send(f"PASS {self.config.password}")
    
    def _send(self, message: str) -> None:
        """Send raw IRC message."""
        self.connection.send(message)
    
    def _on_raw_message(self, line: str) -> None:
        """Handle incoming IRC message."""
        msg = IrcMessage.parse(line)
        
        # Handle SASL
        if self.config.sasl_enabled and not self.state.registered:
            if self._handle_sasl(msg):
                return
        
        # Handle numeric replies
        if msg.command.isdigit():
            self._handle_numeric(msg)
        else:
            self._handle_command(msg)
        
        # Notify callbacks
        for callback in self._on_message:
            try:
                callback(msg)
            except Exception as e:
                print(f"[ERROR] Message callback: {e}")
    
    def _handle_sasl(self, msg: IrcMessage) -> bool:
        """Handle SASL authentication."""
        if "ACK" in str(msg.raw) and "sasl" in str(msg.raw).lower():
            self._send("AUTHENTICATE PLAIN")
            return True
        
        if msg.raw.startswith("AUTHENTICATE +"):
            # Send credentials
            auth = f"{self.config.sasl_user}\0{self.config.sasl_user}\0{self.config.sasl_pass}"
            encoded = base64.b64encode(auth.encode()).decode()
            self._send(f"AUTHENTICATE {encoded}")
            return True
        
        if "sasl" in str(msg.raw).lower() and "successful" in str(msg.raw).lower():
            self._send("CAP END")
            return True
        
        return False
    
    def _handle_numeric(self, msg: IrcMessage) -> None:
        """Handle numeric IRC replies."""
        code = int(msg.command)

        # Capture the registration burst (001, 002, 003, 004, 005, 251, 252,
        # 253, 254, 255, 265, 266, 372, 375, 376, and related notices).
        # We store them so they can be replayed to IRC clients that attach
        # after the network connection is already registered.
        if not self.state.registered:
            self.state.registration_burst.append(msg.raw)

        # Buffer important numerics for later replay (topic, names, motd,
        # server info, etc.) regardless of registration state.
        if msg.raw and code not in (1, 2, 3, 4, 5, 251, 252, 253, 254, 255, 265, 266, 372, 375, 376):
            self._buffer_message(msg.raw, "numeric")

        if code == 1:  # RPL_WELCOME
            self.state.registered = True
            # Server name is the prefix of the welcome message.
            if msg.prefix:
                self.state.server_name = msg.prefix
            print(f"[IRC] Connected as {self.state.current_nick}")

        elif code == 396:  # RPL_HOSTHIDDEN / visible host
            if len(msg.params) >= 3:
                self.state.hostmask = msg.params[1]

        elif code == 433:  # ERR_NICKNAMEINUSE
            # Try alternative nick
            self.state.current_nick = f"{self.state.nick}_"
            self._send(f"NICK {self.state.current_nick}")

        elif code == 353:  # RPL_NAMREPLY
            self._handle_namreply(msg)

        elif code == 366:  # RPL_ENDOFNAMES
            self._handle_endofnames(msg)

        elif code == 324:  # RPL_CHANNELMODEIS
            self._handle_channelmodeis(msg)

        elif code == 329:  # RPL_CREATIONTIME
            self._handle_creationtime(msg)

        elif code == 352:  # RPL_WHOREPLY
            self._handle_whoreply(msg)

        elif code == 315:  # RPL_ENDOFWHO
            self._handle_endofwho(msg)

        elif code == 376:  # RPL_ENDOFMOTD
            # Join configured channels
            for channel in self.config.channels:
                self.join_channel(channel)
    
    def _handle_command(self, msg: IrcMessage) -> None:
        """Handle IRC commands."""
        # Capture server notices that arrive before registration completes,
        # e.g. NickServ "This nickname is registered."
        if msg.command == 'NOTICE' and not self.state.registered:
            self.state.registration_burst.append(msg.raw)

        # Buffer non-registration traffic for detached clients.
        # Skip per-channel numerics (324/329/352/353/366/315) because they are
        # captured per-channel and replayed with the channel metadata burst.
        if msg.raw and msg.command not in ('PING', 'PONG'):
            try:
                code = int(msg.command)
            except ValueError:
                code = None
            if code not in (324, 329, 352, 353, 366, 315):
                self._buffer_message(msg.raw, msg.command.lower())

        handlers = {
            'PING': self._handle_ping,
            'PRIVMSG': self._handle_privmsg,
            'NOTICE': self._handle_notice,
            'JOIN': self._handle_join,
            'PART': self._handle_part,
            'QUIT': self._handle_quit,
            'KICK': self._handle_kick,
            'NICK': self._handle_nick,
            'MODE': self._handle_mode,
        }

        handler = handlers.get(msg.command)
        if handler:
            handler(msg)
    
    def _handle_ping(self, msg: IrcMessage) -> None:
        """Respond to server PING."""
        payload = msg.trailing or (msg.params[0] if msg.params else "")
        if payload:
            self._send(f"PONG :{payload}")

    def _maintain_keepalive(self) -> None:
        """Send periodic PING to the IRC server and detect dead connections."""
        now = time.time()
        # Any incoming traffic (including PONG) counts as activity.
        if not hasattr(self.connection, 'last_activity') or self.connection.last_activity <= 0:
            self.connection.last_activity = now
        # If we haven't received anything for 60 seconds, send a PING.
        if now - self.connection.last_activity > 60 and now - self._last_sent_ping > 30:
            self._send(f"PING :{int(now)}")
            self._last_sent_ping = now
        # If we haven't seen any traffic for 180 seconds, consider the
        # connection dead and force a reconnect.
        if now - self.connection.last_activity > 180:
            print("[IRC] Keepalive timeout, forcing reconnect")
            self.connection.disconnect()
    
    def _handle_privmsg(self, msg: IrcMessage) -> None:
        """Handle PRIVMSG."""
        if len(msg.params) < 1:
            return
        
        target = msg.params[0]
        text = msg.trailing or ""
        
        # Determine if channel or query
        is_channel = target.startswith(('#', '&', '+', '!'))
        
        # Buffer the message
        buffer_target = target if is_channel else msg.nick
        self.buffer.add_message(
            network=self.config.name,
            target=buffer_target,
            message=f"<{msg.nick}> {text}",
            msg_type="PRIVMSG"
        )
        
        # CTCP handling
        if text.startswith('\x01') and text.endswith('\x01'):
            self._handle_ctcp(msg.nick, target, text[1:-1])
    
    def _handle_ctcp(self, nick: str, target: str, text: str) -> None:
        """Handle CTCP requests."""
        if text.startswith('VERSION'):
            self._send(f"NOTICE {nick} :\x01VERSION IRC-BNC v1.0\x01")
        elif text.startswith('PING'):
            self._send(f"NOTICE {nick} :\x01{text}\x01")
    
    def _handle_notice(self, msg: IrcMessage) -> None:
        """Handle NOTICE."""
        pass  # Notices usually don't need buffering
    
    def _handle_join(self, msg: IrcMessage) -> None:
        """Handle JOIN."""
        nick = msg.nick
        channel = msg.trailing or (msg.params[0] if msg.params else "")
        if not nick or not channel:
            return
        channel_lower = channel.lower()

        # Extract full hostmask from the message prefix: nick!ident@host
        ident = msg.ident or ""
        host = msg.host or ""
        if nick and ident and host:
            self.state.users[nick.lower()] = {
                'nick': nick,
                'ident': ident,
                'host': host,
            }

        if nick == self.state.current_nick:
            self.state.channels[channel_lower] = {
                'name': channel,
                'joined': True
            }
            # Reset cached metadata for this channel so we capture the
            # fresh lists sent after joining.
            self.state.channel_names[channel_lower] = []
            self.state.channel_who[channel_lower] = []
            self.state.channel_modes[channel_lower] = []
            self.state.channel_users[channel_lower] = {}
            print(f"[IRC] Joined {channel}")
        else:
            self.state.channel_users.setdefault(channel_lower, {})[nick.lower()] = ""
            # Auto-op immediately if the joining user's hostmask matches.
            if ident and host:
                self._check_auto_op(channel_lower, nick, ident, host)

    def _handle_part(self, msg: IrcMessage) -> None:
        """Handle PART."""
        nick = msg.nick
        channel = msg.params[0] if msg.params else ""
        if not nick or not channel:
            return
        channel_lower = channel.lower()

        if nick == self.state.current_nick:
            self.state.channels.pop(channel_lower, None)
            self.state.channel_names.pop(channel_lower, None)
            self.state.channel_who.pop(channel_lower, None)
            self.state.channel_modes.pop(channel_lower, None)
            self.state.channel_users.pop(channel_lower, None)
        else:
            self.state.channel_users.get(channel_lower, {}).pop(nick.lower(), None)

    def _handle_quit(self, msg: IrcMessage) -> None:
        """Handle QUIT: remove nick from all channels."""
        if not msg.nick:
            return
        nick_lower = msg.nick.lower()
        for users in self.state.channel_users.values():
            users.pop(nick_lower, None)

    def _handle_nick(self, msg: IrcMessage) -> None:
        """Handle NICK change."""
        old_nick = msg.nick
        new_nick = msg.trailing or (msg.params[0] if msg.params else "")
        if not old_nick or not new_nick:
            return
        if old_nick == self.state.current_nick:
            self.state.current_nick = new_nick

        old_lower = old_nick.lower()
        new_lower = new_nick.lower()
        for users in self.state.channel_users.values():
            if old_lower in users:
                users[new_lower] = users.pop(old_lower)

    def _handle_kick(self, msg: IrcMessage) -> None:
        """Handle KICK."""
        if len(msg.params) < 2:
            return
        channel = msg.params[0].lower()
        target = msg.params[1].lower()
        users = self.state.channel_users.get(channel)
        if users:
            users.pop(target, None)
        if target == (self.state.current_nick or "").lower():
            self.state.channels.pop(channel, None)
            self.state.channel_users.pop(channel, None)

    def _handle_mode(self, msg: IrcMessage) -> None:
        """Handle MODE (only track +/-o/v for now)."""
        if len(msg.params) < 3:
            return
        channel = msg.params[0].lower()
        if not channel.startswith('#'):
            return
        modes = msg.params[1]
        args = msg.params[2:]
        users = self.state.channel_users.setdefault(channel, {})
        idx = 0
        adding = True
        for c in modes:
            if c == '+':
                adding = True
                continue
            elif c == '-':
                adding = False
                continue
            if c in ('o', 'v', 'h', 'a', 'q') and idx < len(args):
                target = args[idx].lower()
                idx += 1
                if c == 'o':
                    users[target] = '@' if adding else ''
                elif c == 'v':
                    users[target] = '+' if adding else ''
                elif c == 'h':
                    users[target] = '%' if adding else ''
                elif c == 'a':
                    users[target] = '&' if adding else ''
                elif c == 'q':
                    users[target] = '~' if adding else ''

    def _channel_from_numeric(self, msg: IrcMessage, pos: int) -> Optional[str]:
        """Extract channel from a numeric reply safely."""
        if len(msg.params) > pos:
            return msg.params[pos].lstrip(':').lower()
        return None

    def _handle_namreply(self, msg: IrcMessage) -> None:
        """Capture RPL_NAMREPLY (353) and update live user list."""
        channel = self._channel_from_numeric(msg, 2)
        if not channel:
            return
        names = msg.trailing or ""
        self.state.channel_names.setdefault(channel, []).append(msg.raw)
        users = self.state.channel_users.setdefault(channel, {})
        for nick in names.split():
            prefix = ""
            if nick.startswith('@'):
                prefix = '@'
                nick = nick[1:]
            elif nick.startswith('+'):
                prefix = '+'
                nick = nick[1:]
            elif nick.startswith('%'):
                prefix = '%'
                nick = nick[1:]
            elif nick.startswith('&'):
                prefix = '&'
                nick = nick[1:]
            elif nick.startswith('~'):
                prefix = '~'
                nick = nick[1:]
            if nick:
                users[nick.lower()] = prefix
                # Trigger auto-op on names sync if we know ident@host.
                user_info = self.state.users.get(nick.lower(), {})
                if user_info.get('ident') and user_info.get('host'):
                    self._check_auto_op(channel, nick, user_info['ident'], user_info['host'])

    def _handle_endofnames(self, msg: IrcMessage) -> None:
        """Capture RPL_ENDOFNAMES (366) for later replay."""
        channel = self._channel_from_numeric(msg, 1)
        if not channel:
            return
        self.state.channel_names.setdefault(channel, []).append(msg.raw)

    def _handle_channelmodeis(self, msg: IrcMessage) -> None:
        """Capture RPL_CHANNELMODEIS (324) for later replay."""
        channel = self._channel_from_numeric(msg, 1)
        if not channel:
            return
        self.state.channel_modes.setdefault(channel, []).append(msg.raw)

    def _handle_creationtime(self, msg: IrcMessage) -> None:
        """Capture RPL_CREATIONTIME (329) for later replay."""
        channel = self._channel_from_numeric(msg, 1)
        if not channel:
            return
        self.state.channel_modes.setdefault(channel, []).append(msg.raw)

    def _handle_whoreply(self, msg: IrcMessage) -> None:
        """Capture RPL_WHOREPLY (352) for later replay."""
        # Format: :server 352 <client> <channel> <ident> <host> <server> <nick> <status> :<hopcount> <realname>
        if len(msg.params) < 7:
            return
        channel = msg.params[1].lstrip(':').lower()
        self.state.channel_who.setdefault(channel, []).append(msg.raw)
        # Store ident/host for auto-op matching.
        nick = msg.params[5].lstrip(':')
        ident = msg.params[2]
        host = msg.params[3]
        nick_lower = nick.lower()
        self.state.users[nick_lower] = {
            'nick': nick,
            'ident': ident,
            'host': host,
        }

        # Some WHO replies (for example from a client-requested `WHO <nick>`)
        # report channel as "*".  In that case check every channel this nick
        # is known to be in for auto-op masks.
        if channel and channel.startswith('#'):
            self._check_auto_op(channel, nick, ident, host)
        else:
            for ch, users in self.state.channel_users.items():
                if nick_lower in users:
                    self._check_auto_op(ch, nick, ident, host)

    def _handle_endofwho(self, msg: IrcMessage) -> None:
        """Capture RPL_ENDOFWHO (315) for later replay."""
        channel = self._channel_from_numeric(msg, 1)
        if not channel:
            return
        self.state.channel_who.setdefault(channel, []).append(msg.raw)

    def _on_connected(self) -> None:
        """Called when successfully connected."""
        print(f"[IRC] {self.config.name}: Connected")
        for callback in self._on_connect:
            try:
                callback()
            except Exception as e:
                print(f"[ERROR] Connect callback: {e}")
    
    # Public API
    
    def join_channel(self, channel: str) -> None:
        """Join a channel."""
        if not channel.startswith('#'):
            channel = f"#{channel}"
        self._send(f"JOIN {channel}")
    
    def part_channel(self, channel: str, reason: str = "") -> None:
        """Part a channel."""
        if reason:
            self._send(f"PART {channel} :{reason}")
        else:
            self._send(f"PART {channel}")
    
    def send_message(self, target: str, message: str) -> None:
        """Send PRIVMSG."""
        self._send(f"PRIVMSG {target} :{message}")
        # Also buffer our own messages
        self.buffer.add_message(
            network=self.config.name,
            target=target,
            message=f"<{self.state.current_nick}> {message}",
            msg_type="PRIVMSG"
        )
    
    def send_action(self, target: str, action: str) -> None:
        """Send CTCP ACTION."""
        self._send(f"PRIVMSG {target} :\x01ACTION {action}\x01")

    def change_nick(self, new_nick: str) -> None:
        """Change nickname."""
        self._send(f"NICK {new_nick}")

    def set_away(self, message: Optional[str]) -> None:
        """Set away status."""
        if message:
            self._send(f"AWAY :{message}")
        else:
            self._send("AWAY")

    def get_channel_list(self) -> List[str]:
        """Get joined channels."""
        return list(self.state.channels.keys())

    def add_auto_op_masks(self, channel: str, masks: List[str]) -> None:
        """Register auto-op masks for a channel (from an attached BNC user)."""
        with self._auto_op_lock:
            self._auto_op_masks.setdefault(channel.lower(), set()).update(masks)

    def remove_auto_op_masks(self, channel: str, masks: List[str]) -> None:
        """Unregister auto-op masks for a channel."""
        with self._auto_op_lock:
            entry = self._auto_op_masks.get(channel.lower(), set())
            for m in masks:
                entry.discard(m)
            if not entry:
                self._auto_op_masks.pop(channel.lower(), None)

    def _check_auto_op(self, channel: str, nick: str, ident: str, host: str) -> None:
        """Send MODE +o if the user matches any registered auto-op mask."""
        from shared.auth import UserAccount
        channel_lower = channel.lower()
        with self._auto_op_lock:
            masks = list(self._auto_op_masks.get(channel_lower, set()))
        print(f"[IRC] auto-op check: {nick}!{ident}@{host} on {channel} masks={masks}")
        if not masks:
            return
        for mask in masks:
            match = UserAccount.mask_matches(mask, nick, ident, host)
            print(f"[IRC] auto-op mask={mask} match={match}")
            if match:
                print(f"[IRC] Auto-op: sending MODE {channel} +o {nick}")
                self._send(f"MODE {channel} +o {nick}")
                return

    def build_names_list(self, channel: str) -> List[str]:
        """Generate fresh 353/366 replies from the live channel user list.

        Returns a list with one 353 line and one 366 line. If the channel is
        unknown, returns empty list.
        """
        channel_lower = channel.lower()
        users = self.state.channel_users.get(channel_lower, {})
        if not users and channel_lower not in self.state.channels:
            return []
        server = self.state.server_name or "server"
        nick = self.state.current_nick or "bnc"
        # Build the names string, current nick first.
        names = []
        my_prefix = users.get(nick.lower(), "")
        names.append(f"{my_prefix}{nick}")
        for nick_lower, prefix in sorted(users.items()):
            if nick_lower == nick.lower():
                continue
            # Use the original casing if known, otherwise lower.
            display_nick = self.state.users.get(nick_lower, {}).get('nick') or nick_lower
            names.append(f"{prefix}{display_nick}")
        names_line = ' '.join(names)
        chan_type = '='
        return [
            f":{server} 353 {nick} {chan_type} {channel} :{names_line}",
            f":{server} 366 {nick} {channel} :End of /NAMES list.",
        ]

    def is_connected(self) -> bool:
        """Check if connected to IRC."""
        return self.state.registered and self.connection.is_connected()

    def add_message_callback(self, callback: Callable[[IrcMessage], None]) -> None:
        """Add message callback."""
        self._on_message.append(callback)

    def get_stats(self) -> dict:
        """Get client statistics."""
        stats = self.connection.get_stats()
        stats.update({
            'network': self.config.name,
            'nick': self.state.current_nick,
            'registered': self.state.registered,
            'channels': len(self.state.channels)
        })
        return stats

    def _buffer_message(self, raw_line: str, msg_type: str = "text") -> None:
        """Store a raw IRC line in the global message buffer.

        The buffer is keyed by network and a synthetic '*' target so that all
        traffic received while the user is detached can be replayed on attach.
        Per-channel/query copies are kept as well for targeted playback.
        """
        # Global network buffer for full replay
        self.buffer.add_message(
            network=self.config.name,
            target="*",
            message=raw_line,
            msg_type=msg_type,
        )

        # Also store in the specific channel/query buffer when possible.
        target = None
        parts = raw_line.split()
        if len(parts) >= 3 and parts[1].upper() in (
            'PRIVMSG', 'NOTICE', 'JOIN', 'PART', 'MODE', 'KICK', 'TOPIC'
        ):
            target = parts[2].lstrip(':').lower()
        if target and target.startswith('#'):
            self.buffer.add_message(
                network=self.config.name,
                target=target,
                message=raw_line,
                msg_type=msg_type,
            )