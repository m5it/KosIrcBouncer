"""
IRC BNC - IRC Bouncer System

A complete IRC bouncer with client-server architecture.
"""

__version__ = "1.0.0"
__author__ = "IRC BNC Team"

from .config import Config
from .client import IrcClient
from .server import BncServer

__all__ = ['Config', 'IrcClient', 'BncServer']