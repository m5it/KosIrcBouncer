"""
IRC BNC Configuration Settings
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import os


@dataclass
class IrcNetworkConfig:
    """Configuration for an IRC network connection."""
    name: str
    host: str
    port: int = 6667
    ssl: bool = True
    nick: str = "BNCBot"
    user: str = "bnc"
    realname: str = "IRC BNC Bot"
    password: Optional[str] = None
    sasl_enabled: bool = False
    sasl_user: Optional[str] = None
    sasl_pass: Optional[str] = None
    channels: List[str] = field(default_factory=list)
    auto_reconnect: bool = True
    reconnect_delay: int = 30

@dataclass
class BncServerConfig:
    """Configuration for the BNC server."""
    # Use "::" for dual-stack (IPv4 and IPv6) support
    # Use "0.0.0.0" for IPv4 only
    # Use specific IPv6 address like "::1" for localhost only
    bind_host: str = "::"
    bind_port: int = 6667
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    max_users: int = 10
    require_auth: bool = True
    buffer_size: int = 500
    # Set to True to disable IPv4 when using IPv6 (IPV6_V6ONLY)
    # False enables dual-stack mode on most systems
    ipv6_only: bool = False


@dataclass
class UserConfig:
    """User authentication configuration."""
    username: str
    password_hash: str
    allowed_networks: List[str] = field(default_factory=list)
    is_admin: bool = False


class Config:
    """Main configuration container."""
    
    def __init__(self):
        self.bnc_server = BncServerConfig()
        self.networks: Dict[str, IrcNetworkConfig] = {}
        self.users: Dict[str, UserConfig] = {}
        self.data_dir: str = os.path.expanduser("~/.irc_bnc")
        self.log_level: str = "INFO"
    
    def add_network(self, network: IrcNetworkConfig):
        """Add an IRC network configuration."""
        self.networks[network.name] = network
    
    def add_user(self, user: UserConfig):
        """Add a user configuration."""
        self.users[user.username] = user
    
    def get_network(self, name: str) -> Optional[IrcNetworkConfig]:
        """Get network configuration by name."""
        return self.networks.get(name)
    
    def load_from_file(self, filepath: str):
        """Load configuration from JSON file."""
        import json
        with open(filepath, 'r') as f:
            data = json.load(f)
            # Parse and populate config
            self._parse_config(data)
    
    def _parse_config(self, data: dict):
        """Parse configuration dictionary."""
        if 'bnc_server' in data:
            self.bnc_server = BncServerConfig(**data['bnc_server'])
        if 'networks' in data:
            for net_data in data['networks']:
                network = IrcNetworkConfig(**net_data)
                self.add_network(network)
        if 'users' in data:
            for user_data in data['users']:
                user = UserConfig(**user_data)
                self.add_user(user)


# Default configuration instance
default_config = Config()