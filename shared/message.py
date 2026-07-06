"""
IRC Message representation and utilities
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import re


@dataclass
class IrcMessage:
    """Represents a parsed IRC message."""
    
    timestamp: datetime
    raw: str
    prefix: Optional[str] = None
    command: str = ""
    params: list = None
    trailing: Optional[str] = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = []
    
    @classmethod
    def parse(cls, raw_line: str) -> 'IrcMessage':
        """Parse a raw IRC message line."""
        timestamp = datetime.now()
        line = raw_line.strip()
        
        if not line:
            return cls(timestamp=datetime.now(), raw=line)
        
        prefix = None
        if line.startswith(':'):
            # Extract prefix
            space_idx = line.find(' ')
            if space_idx != -1:
                prefix = line[1:space_idx]
                line = line[space_idx + 1:].strip()
        
        # Split command and params
        parts = line.split(' :', 1)
        before_colon = parts[0].strip()
        trailing = parts[1] if len(parts) > 1 else None
        
        # Parse command and params
        tokens = before_colon.split()
        command = tokens[0].upper() if tokens else ""
        params = tokens[1:] if len(tokens) > 1 else []
        
        return cls(
            timestamp=timestamp,
            raw=raw_line,
            prefix=prefix,
            command=command,
            params=params,
            trailing=trailing
        )
    
    @property
    def nick(self) -> Optional[str]:
        """Extract nick from prefix."""
        if self.prefix and '!' in self.prefix:
            return self.prefix.split('!')[0]
        return self.prefix if self.prefix else None
    
    @property
    def host(self) -> Optional[str]:
        """Extract host from prefix."""
        if self.prefix and '!' in self.prefix:
            parts = self.prefix.split('!')
            if len(parts) > 1 and '@' in parts[1]:
                return parts[1].split('@')[1]
        return None
    
    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.command}: {self.params} :{self.trailing}"


@dataclass
class ChannelMessage:
    """Message in a channel buffer."""
    
    timestamp: datetime
    network: str
    channel: str
    nick: str
    message: str
    msg_type: str = "PRIVMSG"  # PRIVMSG, NOTICE, ACTION, etc.
    
    def to_irc_format(self) -> str:
        """Convert to IRC protocol format."""
        if self.msg_type == "ACTION":
            return f":{self.nick}!user@host PRIVMSG {self.channel} :\x01ACTION {self.message}\x01"
        return f":{self.nick}!user@host PRIVMSG {self.channel} :{self.message}"


@dataclass
class UserConnection:
    """Represents a connected BNC user."""
    
    socket: Any
    address: tuple
    username: Optional[str] = None
    authenticated: bool = False
    connected_network: Optional[str] = None
    capabilities: list = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []