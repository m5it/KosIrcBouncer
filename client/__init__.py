"""
IRC BNC Client Package
"""

from client.connection import IrcConnection
from .irc_client import IrcClient

__all__ = ['IrcConnection', 'IrcClient']
