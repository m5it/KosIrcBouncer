"""
Shared utilities for the IRC BNC.
"""

from .buffer import BufferManager, BufferEntry
from .message import IrcMessage, ChannelMessage, UserConnection
from .auth import UserDatabase, PasswordHasher, UserAccount, RateLimiter, IPFilter
# Deferred import to avoid circular dependency with client.irc_client.
# MultiNetworkManager can be imported directly from .multi_network when needed.
# from .multi_network import MultiNetworkManager

__all__ = [
    'BufferManager',
    'BufferEntry',
    'IrcMessage',
    'ChannelMessage',
    'UserConnection',
    'UserDatabase',
    'PasswordHasher',
    'UserAccount',
    'RateLimiter',
    'IPFilter',
    'MultiNetworkManager'
]
