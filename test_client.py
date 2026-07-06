#!/usr/bin/env python3
"""
Test script for IRC Client
"""

import sys
import time
from config import Config, IrcNetworkConfig
from shared import BufferManager
from client import IrcClient


def test_connection():
    """Test IRC client connection."""
    print("=" * 60)
    print("IRC Client Test")
    print("=" * 60)
    
    # Create config for Libera Chat
    config = IrcNetworkConfig(
        name="libera",
        host="irc.libera.chat",
        port=6697,
        ssl=True,
        nick="TestBNC123",
        user="bnc",
        realname="IRC BNC Bot",
        channels=["#test"],
        auto_reconnect=True,
        reconnect_delay=10
    )
    
    # Buffer manager
    buffer = BufferManager()
    
    # Create client
    client = IrcClient(config, buffer)
    
    # Add message callback
    def on_message(msg):
        print(f"[MSG] {msg.command}: {msg.params} :{msg.trailing}")
    
    client.add_message_callback(on_message)
    
    # Start connection
    print(f"\nConnecting to {config.host}:{config.port}...")
    client.start()
    
    # Wait for connection
    print("Waiting for connection (30s timeout)...")
    for i in range(30):
        if client.is_connected():
            print(f"\n✓ Connected as {client.state.current_nick}")
            print(f"  Joined channels: {client.get_channel_list()}")
            break
        time.sleep(1)
    else:
        print("\n✗ Connection timeout")
        client.stop()
        return False
    
    # Run for a bit
    print("\nListening for messages (10 seconds)...")
    time.sleep(10)
    
    # Show stats
    stats = client.get_stats()
    print(f"\nStats:")
    print(f"  Connected: {stats['registered']}")
    print(f"  Nick: {stats['nick']}")
    print(f"  Bytes sent: {stats['bytes_sent']}")
    print(f"  Bytes received: {stats['bytes_received']}")
    
    # Disconnect
    print("\nDisconnecting...")
    client.stop()
    print("✓ Disconnected")
    
    return True


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)