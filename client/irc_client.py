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

from ..config import IrcNetworkConfig
from ..shared import IrcMessage, ChannelMessage, BufferManager
from .connection import IrcConnection


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
        self.state = IrcState()
        self.state.nick = self.config.nick
        self.state.current_nick = self.config.nick
        
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
                # Connected successfully
                self._on_connected()
                # Keep running until disconnect
                while self._running and self.connection.is_connected():
                    time.sleep(0.1)
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
        
        if code == 1:  # RPL_WELCOME
            self.state.registered = True
            print(f"[IRC] Connected as {self.state.current_nick}")
        
        elif code == 433:  # ERR_NICKNAMEINUSE
            # Try alternative nick
            self.state.current_nick = f"{self.state.nick}_"
            self._send(f"NICK {self.state.current_nick}")
        
        elif code == 376:  # RPL_ENDOFMOTD
            # Join configured channels
            for channel in self.config.channels:
                self.join_channel(channel)
    
    def _handle_command(self, msg: IrcMessage) -> None:
        """Handle IRC commands."""
        handlers = {
            'PING': self._handle_ping,
            'PRIVMSG': self._handle_privmsg,
            'NOTICE': self._handle_notice,
            'JOIN': self._handle_join,
            'PART': self._handle_part,
            'QUIT': self._handle_quit,
            'NICK': self._handle_nick,
            'MODE': self._handle_mode,
        }
        
        handler = handlers.get(msg.command)
        if handler:
            handler(msg)
    
    def _handle_ping(self, msg: IrcMessage) -> None:
        """Respond to PING."""
        if msg.trailing:
            self._send(f"PONG :{msg.trailing}")
    
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
        if msg.nick == self.state.current_nick:
            channel = msg.trailing or (msg.params[0] if msg.params else "")
            if channel:
                self.state.channels[channel.lower()] = {
                    'name': channel,
                    'joined': True
                }
                print(f"[IRC] Joined {channel}")
    
    def _handle_part(self, msg: IrcMessage) -> None:
        """Handle PART."""
        if msg.nick == self.state.current_nick:
            channel = msg.params[0] if msg.params else ""
            if channel:
                self.state.channels.pop(channel.lower(), None)
    
    def _handle_quit(self, msg: IrcMessage) -> None:
        """Handle QUIT."""
        pass  # User quit
    
    def _handle_nick(self, msg: IrcMessage) -> None:
        """Handle NICK change."""
        if msg.nick == self.state.current_nick:
            new_nick = msg.trailing or (msg.params[0] if msg.params else "")
            self.state.current_nick = new_nick
    
    def _handle_mode(self, msg: IrcMessage) -> None:
        """Handle MODE."""
        pass
    
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