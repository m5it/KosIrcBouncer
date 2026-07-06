"""
Message buffer management for channels and queries
"""

from collections import deque
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass, field
import threading


@dataclass
class BufferEntry:
    """Single entry in a message buffer."""
    timestamp: datetime
    message: str
    msg_type: str = "text"  # text, join, part, quit, nick, mode, etc.


class MessageBuffer:
    """Circular buffer for IRC messages."""
    
    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()
    
    def add(self, message: str, msg_type: str = "text") -> None:
        """Add a message to the buffer."""
        entry = BufferEntry(
            timestamp=datetime.now(),
            message=message,
            msg_type=msg_type
        )
        with self._lock:
            self._buffer.append(entry)
    
    def get_since(self, timestamp: datetime) -> List[BufferEntry]:
        """Get all messages since a given timestamp."""
        with self._lock:
            return [entry for entry in self._buffer if entry.timestamp > timestamp]
    
    def get_last(self, count: int = 50) -> List[BufferEntry]:
        """Get last N messages."""
        with self._lock:
            return list(self._buffer)[-count:]
    
    def clear(self) -> None:
        """Clear the buffer."""
        with self._lock:
            self._buffer.clear()
    
    def __len__(self) -> int:
        return len(self._buffer)


class BufferManager:
    """Manages buffers for all channels and queries."""
    
    def __init__(self, default_size: int = 500):
        self.default_size = default_size
        self._buffers: Dict[str, MessageBuffer] = {}
        self._lock = threading.Lock()
    
    def _get_key(self, network: str, target: str) -> str:
        """Generate buffer key."""
        return f"{network}:{target.lower()}"
    
    def get_buffer(self, network: str, target: str) -> MessageBuffer:
        """Get or create buffer for a channel/query."""
        key = self._get_key(network, target)
        with self._lock:
            if key not in self._buffers:
                self._buffers[key] = MessageBuffer(self.default_size)
            return self._buffers[key]
    
    def add_message(self, network: str, target: str, message: str, msg_type: str = "text") -> None:
        """Add message to appropriate buffer."""
        buffer = self.get_buffer(network, target)
        buffer.add(message, msg_type)
    
    def get_channel_buffers(self, network: str) -> Dict[str, MessageBuffer]:
        """Get all buffers for a network."""
        prefix = f"{network}:"
        with self._lock:
            return {
                key.split(":", 1)[1]: buf 
                for key, buf in self._buffers.items() 
                if key.startswith(prefix)
            }
    
    def clear_network(self, network: str) -> None:
        """Clear all buffers for a network."""
        with self._lock:
            keys_to_remove = [
                key for key in self._buffers.keys() 
                if key.startswith(f"{network}:")
            ]
            for key in keys_to_remove:
                del self._buffers[key]