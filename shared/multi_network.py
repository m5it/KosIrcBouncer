"""
Multi-Network Manager for IRC BNC
Handles multiple IRC networks simultaneously.
"""

import threading
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from ..config import IrcNetworkConfig
from ..client import IrcClient
from .buffer import BufferManager


@dataclass
class NetworkStatus:
    """Status of an IRC network connection."""
    name: str
    connected: bool = False
    nick: str = ""
    server: str = ""
    channels: List[str] = field(default_factory=list)
    lag: float = 0.0
    last_activity: Optional[datetime] = None


class MultiNetworkManager:
    """
    Manages multiple IRC network connections.
    Each network has its own IrcClient and buffers.
    """
    
    def __init__(self, buffer_manager: BufferManager):
        self.buffer = buffer_manager
        self.clients: Dict[str, IrcClient] = {}
        self.configs: Dict[str, IrcNetworkConfig] = {}
        self._lock = threading.RLock()
        
        # Network aliases
        self.aliases: Dict[str, str] = {}  # alias -> network name
        
        # Current network per user session
        self.user_networks: Dict[str, str] = {}  # session_id -> network
        
        # Cross-network relay
        self.relay_enabled: bool = False
        self.relay_networks: Set[str] = set()
    
    def add_network(self, config: IrcNetworkConfig) -> bool:
        """Add a new IRC network."""
        with self._lock:
            if config.name in self.clients:
                print(f"[MultiNet] Network {config.name} already exists")
                return False
            
            # Create client
            client = IrcClient(config, self.buffer)
            self.clients[config.name] = client
            self.configs[config.name] = config
            
            print(f"[MultiNet] Added network: {config.name}")
            return True
    
    def remove_network(self, name: str) -> bool:
        """Remove a network."""
        with self._lock:
            client = self.clients.get(name)
            if not client:
                return False
            
            # Stop client
            client.stop()
            
            del self.clients[name]
            del self.configs[name]
            
            # Remove aliases
            self.aliases = {k: v for k, v in self.aliases.items() if v != name}
            
            print(f"[MultiNet] Removed network: {name}")
            return True
    
    def start_network(self, name: str) -> bool:
        """Start a network connection."""
        client = self.clients.get(name)
        if not client:
            return False
        
        if client.is_connected():
            return True
        
        client.start()
        return True
    
    def stop_network(self, name: str) -> bool:
        """Stop a network connection."""
        client = self.clients.get(name)
        if not client:
            return False
        
        client.stop()
        return True
    
    def start_all(self):
        """Start all networks."""
        for name in self.clients:
            self.start_network(name)
    
    def stop_all(self):
        """Stop all networks."""
        for name, client in self.clients.items():
            client.stop()
    
    def get_client(self, name: str) -> Optional[IrcClient]:
        """Get client by network name."""
        # Check aliases first
        actual_name = self.aliases.get(name, name)
        return self.clients.get(actual_name)
    
    def get_status(self, name: str) -> Optional[NetworkStatus]:
        """Get network status."""
        client = self.get_client(name)
        if not client:
            return None
        
        stats = client.get_stats()
        return NetworkStatus(
            name=name,
            connected=stats.get('registered', False),
            nick=stats.get('nick', ''),
            server=f"{client.config.host}:{client.config.port}",
            channels=client.get_channel_list(),
            last_activity=datetime.now() if client.is_connected() else None
        )
    
    def get_all_status(self) -> List[NetworkStatus]:
        """Get status of all networks."""
        return [self.get_status(name) for name in self.clients.keys()]
    
    def set_user_network(self, session_id: str, network: str) -> bool:
        """Set current network for a user session."""
        if network not in self.clients:
            return False
        
        self.user_networks[session_id] = network
        return True
    
    def get_user_network(self, session_id: str) -> Optional[str]:
        """Get current network for a user session."""
        return self.user_networks.get(session_id)
    
    def send_message(self, network: str, target: str, message: str) -> bool:
        """Send message on specific network."""
        client = self.get_client(network)
        if not client or not client.is_connected():
            return False
        
        client.send_message(target, message)
        return True
    
    def broadcast_message(self, target: str, message: str, 
                         exclude_network: Optional[str] = None) -> Dict[str, bool]:
        """Send message to same target on all networks."""
        results = {}
        for name, client in self.clients.items():
            if name == exclude_network:
                continue
            if client.is_connected():
                client.send_message(target, message)
                results[name] = True
            else:
                results[name] = False
        return results
    
    def relay_message(self, from_network: str, to_networks: List[str],
                      target: str, message: str) -> bool:
        """Relay message from one network to others."""
        for net_name in to_networks:
            if net_name == from_network:
                continue
            
            client = self.get_client(net_name)
            if client and client.is_connected():
                client.send_message(target, f"[{from_network}] {message}")
        
        return True
    
    def get_network_list(self) -> List[str]:
        """Get list of network names."""
        return list(self.clients.keys())
    
    def is_connected(self, name: str) -> bool:
        """Check if network is connected."""
        client = self.get_client(name)
        return client.is_connected() if client else False
    
    def add_alias(self, alias: str, network: str) -> bool:
        """Add alias for network."""
        if network not in self.clients:
            return False
        
        self.aliases[alias] = network
        return True
    
    def get_connected_networks(self) -> List[str]:
        """Get list of connected networks."""
        return [name for name, client in self.clients.items() if client.is_connected()]
    
    def get_disconnected_networks(self) -> List[str]:
        """Get list of disconnected networks."""
        return [name for name, client in self.clients.items() if not client.is_connected()]