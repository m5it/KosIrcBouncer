#!/usr/bin/env python3
"""
Test BNC Server
"""

import sys
import socket
import time
import threading

from config import Config, IrcNetworkConfig, BncServerConfig
from shared import BufferManager
from client import IrcClient
from server import BncServer


def test_bnc_server():
    """Test BNC server accepts connections."""
    print("=" * 60)
    print("BNC Server Test")
    print("=" * 60)
    
    # Setup
    buffer = BufferManager()
    
    # Mock IRC client (not connected)
    mock_config = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        nick="TestBot"
    )
    mock_client = IrcClient(mock_config, buffer)
    
    # BNC server
    bnc_config = BncServerConfig(
        bind_host="127.0.0.1",
        bind_port=16667,  # High port for testing
        require_auth=False
    )
    
    server = BncServer(bnc_config, {"testnet": mock_client})
    
    # Start server
    print(f"\nStarting BNC server on {bnc_config.bind_host}:{bnc_config.bind_port}...")
    if not server.start():
        print("✗ Failed to start server")
        return False
    
    print("✓ Server started")
    
    # Test connection
    time.sleep(0.5)
    
    print(f"\nConnecting test client...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((bnc_config.bind_host, bnc_config.bind_port))
        
        # Send IRC registration
        sock.send(b"NICK TestUser\r\n")
        sock.send(b"USER test 0 * :Test User\r\n")
        
        # Receive welcome
        data = sock.recv(4096)
        response = data.decode('utf-8', errors='replace')
        
        print(f"\nServer response:\n{response}")
        
        if "001" in response:  # RPL_WELCOME
            print("✓ Received welcome message")
        else:
            print("✗ No welcome message")
            return False
        
        # Send BNC command
        sock.send(b"BNC STATUS\r\n")
        time.sleep(0.5)
        
        data = sock.recv(4096)
        response = data.decode('utf-8', errors='replace')
        print(f"\nBNC STATUS response:\n{response}")
        
        if "BNC Status" in response:
            print("✓ BNC commands working")
        else:
            print("✗ BNC commands not working")
        
        # Disconnect
        sock.send(b"QUIT :Test complete\r\n")
        sock.close()
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        server.stop()
        return False
    
    # Stop server
    print("\nStopping server...")
    server.stop()
    
    # Check stats
    stats = server.get_stats()
    print(f"\nServer stats:")
    print(f"  Total connections: {stats['total_connections']}")
    print(f"  Active sessions: {stats['active_sessions']}")
    
    print("\n" + "=" * 60)
    print("BNC Server Test Complete")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_bnc_server()
    sys.exit(0 if success else 1)