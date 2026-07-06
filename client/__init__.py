"""
IRC Client module - Bot connection to IRC networks
"""

from .irc_client import IrcClient
from .connection import IrcConnection

__all__ = ['IrcClient', 'IrcConnection']