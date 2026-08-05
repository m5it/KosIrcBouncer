#!/usr/bin/env python3
"""
IRC BNC - Main Entry Point
"""

import sys
import signal
import time
import threading
import argparse

from config import Config, IrcNetworkConfig, BncServerConfig
from shared import BufferManager
from client import IrcClient
from server import BncServer


class IrcBnc:
    """Main IRC BNC application."""
    
    def __init__(self):
        self.config = Config()
        self.buffer_manager = BufferManager()
        
        self.irc_clients: dict = {}
        self.bnc_server: BncServer = None
        
        self.running = False
    
    def setup(self):
        """Setup default configuration."""
        # Add Libera Chat
        libera = IrcNetworkConfig(
            name="libera",
            host="irc.libera.chat",
            port=6697,
            ssl=True,
            nick="MyBNCBot",
            user="bnc",
            realname="IRC BNC",
            channels=["#test"],
            auto_reconnect=True
        )
        self.config.add_network(libera)
        
        # BNC server config
        bnc_config = BncServerConfig(
            bind_host="0.0.0.0",
            bind_port=6667,
            require_auth=False  # For testing
        )
        self.config.bnc_server = bnc_config
    
    def start(self):
        """Start BNC."""
        print("=" * 60)
        print("IRC BNC - Starting...")
        print("=" * 60)
        
        # Start IRC clients
        for name, net_config in self.config.networks.items():
            print(f"\n[Setup] Creating IRC client for {name}...")
            client = IrcClient(net_config, self.buffer_manager)
            client.start()
            self.irc_clients[name] = client
        
        # Wait a bit for connections
        time.sleep(2)
        
        # Start BNC server
        print(f"\n[Setup] Starting BNC server...")
        self.bnc_server = BncServer(
            self.config.bnc_server,
            self.irc_clients
        )
        
        if not self.bnc_server.start():
            print("[ERROR] Failed to start BNC server")
            self.stop()
            return False
        
        self.running = True
        print("\n" + "=" * 60)
        print("IRC BNC is running!")
        print(f"Connect with: nc localhost {self.config.bnc_server.bind_port}")
        print("Or use HexChat: /server localhost {port}")
        print("=" * 60)
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        return True
    
    def stop(self):
        """Stop BNC."""
        print("\n[Shutdown] Stopping IRC BNC...")
        self.running = False
        
        # Stop BNC server
        if self.bnc_server:
            self.bnc_server.stop()
        
        # Stop IRC clients
        for name, client in self.irc_clients.items():
            print(f"[Shutdown] Stopping {name}...")
            client.stop()
        
        print("[Shutdown] Complete")
    
    def _signal_handler(self, signum, frame):
        """Handle signals."""
        print(f"\n[Signal] Received {signum}")
        self.stop()
        sys.exit(0)
    
    def run(self):
        """Main loop."""
        if not self.start():
            return 1
        
        try:
            while self.running:
                # Show stats periodically
                time.sleep(30)
                
                # IRC stats
                for name, client in self.irc_clients.items():
                    if client.is_connected():
                        print(f"[Status] {name}: Connected as {client.state.current_nick}")
                    else:
                        print(f"[Status] {name}: Connecting...")
                
                # BNC stats
                if self.bnc_server:
                    stats = self.bnc_server.get_stats()
                    print(f"[Status] BNC: {stats['active_sessions']} users connected")
                
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        
        return 0


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description='IRC BNC - IRC Bouncer System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Examples:
  python main.py           # Start the BNC
  python main.py --help    # Show this help message
        '''
    )
    parser.add_argument('--version', action='version', version='IRC BNC 1.0')
    args = parser.parse_args()
    
    bnc = IrcBnc()
    bnc.setup()
    return bnc.run()


if __name__ == "__main__":
    sys.exit(main())
