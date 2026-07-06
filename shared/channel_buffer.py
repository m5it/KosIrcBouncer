"""
Enhanced Channel Buffer System with Persistence
"""

import json
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import re


class MessageType(Enum):
    PRIVMSG = "privmsg"
    NOTICE = "notice"
    ACTION = "action"
    JOIN = "join"
    PART = "part"
    QUIT = "quit"
    NICK = "nick"
    MODE = "mode"
    TOPIC = "topic"
    KICK = "kick"


@dataclass
class ChannelMessage:
    """Represents a message in a channel buffer."""
    id: Optional[int] = None
    timestamp: datetime = None
    network: str = ""
    channel: str = ""
    nick: str = ""
    message: str = ""
    msg_type: MessageType = MessageType.PRIVMSG
    is_query: bool = False
    topic: Optional[str] = None
    modes: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'network': self.network,
            'channel': self.channel,
            'nick': self.nick,
            'message': self.message,
            'msg_type': self.msg_type.value,
            'is_query': self.is_query,
            'topic': self.topic,
            'modes': self.modes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ChannelMessage':
        """Create from dictionary."""
        return cls(
            id=data.get('id'),
            timestamp=datetime.fromisoformat(data['timestamp']),
            network=data['network'],
            channel=data['channel'],
            nick=data['nick'],
            message=data['message'],
            msg_type=MessageType(data.get('msg_type', 'privmsg')),
            is_query=data.get('is_query', False),
            topic=data.get('topic'),
            modes=data.get('modes')
        )
    
    def to_irc_format(self) -> str:
        """Convert to IRC protocol format."""
        if self.msg_type == MessageType.ACTION:
            return f":{self.nick}!user@host PRIVMSG {self.channel} :\x01ACTION {self.message}\x01"
        return f":{self.nick}!user@host PRIVMSG {self.channel} :{self.message}"


class ChannelBuffer:
    """Buffer for a single channel or query."""
    
    def __init__(self, network: str, channel: str, max_size: int = 500):
        self.network = network
        self.channel = channel
        self.max_size = max_size
        self.is_query = not channel.startswith(('#', '&', '+', '!'))
        
        self._messages: List[ChannelMessage] = []
        self._lock = threading.RLock()
        
        # Channel state
        self.topic: Optional[str] = None
        self.topic_set_by: Optional[str] = None
        self.topic_time: Optional[datetime] = None
        self.modes: Set[str] = set()
        self.users: Dict[str, Set[str]] = {}  # nick -> modes
        self.bans: List[Tuple[str, str, datetime]] = []  # mask, setter, time
        
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
    
    def add_message(self, nick: str, message: str, 
                    msg_type: MessageType = MessageType.PRIVMSG) -> ChannelMessage:
        """Add a message to buffer."""
        msg = ChannelMessage(
            network=self.network,
            channel=self.channel,
            nick=nick,
            message=message,
            msg_type=msg_type,
            is_query=self.is_query
        )
        
        with self._lock:
            self._messages.append(msg)
            self.last_activity = datetime.now()
            
            # Trim if needed
            while len(self._messages) > self.max_size:
                self._messages.pop(0)
        
        return msg
    
    def add_system_message(self, message: str, msg_type: MessageType) -> ChannelMessage:
        """Add system message (join, part, etc.)."""
        return self.add_message("*", message, msg_type)
    
    def get_messages(self, count: Optional[int] = None,
                     since: Optional[datetime] = None,
                     before: Optional[datetime] = None) -> List[ChannelMessage]:
        """Get messages with optional filtering."""
        with self._lock:
            messages = self._messages[:]
        
        if since:
            messages = [m for m in messages if m.timestamp >= since]
        if before:
            messages = [m for m in messages if m.timestamp < before]
        if count:
            messages = messages[-count:]
        
        return messages
    
    def search(self, query: str, case_sensitive: bool = False,
               nick_filter: Optional[str] = None,
               msg_type_filter: Optional[MessageType] = None) -> List[ChannelMessage]:
        """Search messages."""
        results = []
        
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)
        
        with self._lock:
            for msg in self._messages:
                if nick_filter and msg.nick != nick_filter:
                    continue
                if msg_type_filter and msg.msg_type != msg_type_filter:
                    continue
                if pattern.search(msg.message):
                    results.append(msg)
        
        return results
    
    def clear(self) -> int:
        """Clear buffer, return count cleared."""
        with self._lock:
            count = len(self._messages)
            self._messages.clear()
            return count
    
    def set_topic(self, topic: str, set_by: str):
        """Set channel topic."""
        self.topic = topic
        self.topic_set_by = set_by
        self.topic_time = datetime.now()
    
    def add_mode(self, mode: str):
        """Add channel mode."""
        self.modes.add(mode)
    
    def remove_mode(self, mode: str):
        """Remove channel mode."""
        self.modes.discard(mode)
    
    def add_user(self, nick: str, modes: Set[str] = None):
        """Add user to channel."""
        self.users[nick] = modes or set()
    
    def remove_user(self, nick: str):
        """Remove user from channel."""
        self.users.pop(nick, None)
    
    def add_ban(self, mask: str, setter: str):
        """Add ban."""
        self.bans.append((mask, setter, datetime.now()))
    
    def remove_ban(self, mask: str):
        """Remove ban."""
        self.bans = [(m, s, t) for m, s, t in self.bans if m != mask]
    
    def get_user_list(self) -> List[Tuple[str, Set[str]]]:
        """Get list of users with modes."""
        return list(self.users.items())
    
    def __len__(self) -> int:
        return len(self._messages)


class PersistentBufferManager:
    """Buffer manager with SQLite persistence."""
    
    def __init__(self, data_dir: str, default_size: int = 500):
        self.data_dir = data_dir
        self.default_size = default_size
        self._buffers: Dict[str, ChannelBuffer] = {}
        self._lock = threading.RLock()
        
        # Ensure directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize database
        self.db_path = os.path.join(data_dir, 'buffers.db')
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    network TEXT,
                    channel TEXT,
                    nick TEXT,
                    message TEXT,
                    msg_type TEXT,
                    is_query INTEGER
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    network TEXT,
                    channel TEXT,
                    topic TEXT,
                    topic_set_by TEXT,
                    topic_time TEXT,
                    modes TEXT,
                    created_at TEXT,
                    last_activity TEXT,
                    PRIMARY KEY (network, channel)
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_time 
                ON messages(timestamp)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_channel 
                ON messages(network, channel)
            ''')
    
    def _get_key(self, network: str, channel: str) -> str:
        """Generate buffer key."""
        return f"{network.lower()}:{channel.lower()}"
    
    def get_buffer(self, network: str, channel: str) -> ChannelBuffer:
        """Get or create buffer."""
        key = self._get_key(network, channel)
        
        with self._lock:
            if key not in self._buffers:
                self._buffers[key] = ChannelBuffer(
                    network=network,
                    channel=channel,
                    max_size=self.default_size
                )
                # Load from DB
                self._load_buffer(self._buffers[key])
            
            return self._buffers[key]
    
    def _load_buffer(self, buffer: ChannelBuffer):
        """Load buffer from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Load channel info
                cursor = conn.execute(
                    'SELECT topic, topic_set_by, topic_time, modes, created_at, last_activity '
                    'FROM channels WHERE network = ? AND channel = ?',
                    (buffer.network, buffer.channel)
                )
                row = cursor.fetchone()
                if row:
                    buffer.topic = row[0]
                    buffer.topic_set_by = row[1]
                    buffer.topic_time = datetime.fromisoformat(row[2]) if row[2] else None
                    buffer.modes = set(row[3].split(',')) if row[3] else set()
                    buffer.created_at = datetime.fromisoformat(row[4])
                    buffer.last_activity = datetime.fromisoformat(row[5])
                
                # Load recent messages
                cursor = conn.execute(
                    'SELECT timestamp, nick, message, msg_type, is_query '
                    'FROM messages '
                    'WHERE network = ? AND channel = ? '
                    'ORDER BY timestamp DESC '
                    'LIMIT ?',
                    (buffer.network, buffer.channel, buffer.max_size)
                )
                
                for row in reversed(cursor.fetchall()):
                    msg = ChannelMessage(
                        timestamp=datetime.fromisoformat(row[0]),
                        network=buffer.network,
                        channel=buffer.channel,
                        nick=row[1],
                        message=row[2],
                        msg_type=MessageType(row[3]),
                        is_query=bool(row[4])
                    )
                    buffer._messages.append(msg)
                    
        except Exception as e:
            print(f"[Buffer] Failed to load: {e}")
    
    def save_message(self, msg: ChannelMessage):
        """Save message to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT INTO messages (timestamp, network, channel, nick, message, msg_type, is_query) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (
                        msg.timestamp.isoformat(),
                        msg.network,
                        msg.channel,
                        msg.nick,
                        msg.message,
                        msg.msg_type.value,
                        int(msg.is_query)
                    )
                )
        except Exception as e:
            print(f"[Buffer] Failed to save message: {e}")
    
    def save_channel_info(self, buffer: ChannelBuffer):
        """Save channel info to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO channels '
                    '(network, channel, topic, topic_set_by, topic_time, modes, created_at, last_activity) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (
                        buffer.network,
                        buffer.channel,
                        buffer.topic,
                        buffer.topic_set_by,
                        buffer.topic_time.isoformat() if buffer.topic_time else None,
                        ','.join(buffer.modes),
                        buffer.created_at.isoformat(),
                        buffer.last_activity.isoformat()
                    )
                )
        except Exception as e:
            print(f"[Buffer] Failed to save channel: {e}")
    
    def add_message(self, network: str, channel: str, nick: str, 
                    message: str, msg_type: MessageType = MessageType.PRIVMSG):
        """Add message and persist."""
        buffer = self.get_buffer(network, channel)
        msg = buffer.add_message(nick, message, msg_type)
        self.save_message(msg)
        return msg
    
    def get_buffer_stats(self, network: str) -> Dict[str, any]:
        """Get statistics for a network."""
        stats = {
            'channels': 0,
            'queries': 0,
            'total_messages': 0
        }
        
        with self._lock:
            for key, buf in self._buffers.items():
                if buf.network.lower() == network.lower():
                    if buf.is_query:
                        stats['queries'] += 1
                    else:
                        stats['channels'] += 1
                    stats['total_messages'] += len(buf)
        
        return stats
    
    def export_to_json(self, network: str, filepath: str):
        """Export network buffers to JSON."""
        data = {
            'network': network,
            'exported_at': datetime.now().isoformat(),
            'channels': []
        }
        
        with self._lock:
            for key, buf in self._buffers.items():
                if buf.network.lower() == network.lower():
                    channel_data = {
                        'name': buf.channel,
                        'topic': buf.topic,
                        'modes': list(buf.modes),
                        'users': {nick: list(modes) for nick, modes in buf.users.items()},
                        'messages': [m.to_dict() for m in buf.get_messages()]
                    }
                    data['channels'].append(channel_data)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def import_from_json(self, filepath: str):
        """Import buffers from JSON."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for ch_data in data.get('channels', []):
            buffer = self.get_buffer(data['network'], ch_data['name'])
            buffer.topic = ch_data.get('topic')
            buffer.modes = set(ch_data.get('modes', []))
            
            for msg_data in ch_data.get('messages', []):
                msg = ChannelMessage.from_dict(msg_data)
                buffer._messages.append(msg)
                self.save_message(msg)
    
    def cleanup_old_messages(self, days: int = 30):
        """Remove messages older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'DELETE FROM messages WHERE timestamp < ?',
                    (cutoff.isoformat(),)
                )
                deleted = conn.rowcount
                print(f"[Buffer] Cleaned up {deleted} old messages")
                return deleted
        except Exception as e:
            print(f"[Buffer] Cleanup failed: {e}")
            return 0