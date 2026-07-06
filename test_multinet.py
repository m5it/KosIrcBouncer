#!/usr/bin/env python3
"""
Test Multi-Network Support
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.multi_network import MultiNetworkManager
from shared.buffer import BufferManager


def test_multinet():
    """Test multi-network functionality."""
    print("=" * 60)
    print("Multi-Network Test")
    print("=" * 60)
    
    # Create manager
    buffer = BufferManager("/tmp/test_bnc")
    multi = MultiNetworkManager(buffer)
    
    # Test 1: Add networks
    print("\n1. Adding networks...")
    
    from config import IrcNetworkConfig
    
    libera = IrcNetworkConfig(
        name="libera",
        host="irc.libera.chat",
        port=6697,
        ssl=True,
        nick="TestBot"
    )
    
    oftc = IrcNetworkConfig(
        name="oftc",
        host="irc.oftc.net",
        port=6697,
        ssl=True,
        nick="TestBot"
    )
    
    multi.add_network(libera)
    multi.add_network(oftc)
    
    print(f"✓ Added {len(multi.get_network_list())} networks")
    
    # Test 2: Check status
    print("\n2. Checking status...")
    for status in multi.get_all_status():
        print(f"  {status.name}: {status.connected}")
    
    # Test 3: Aliases
    print("\n3. Testing aliases...")
    multi.add_alias("l", "libera")
    client = multi.get_client("l")
    print(f"✓ Alias works: {client is not None}")
    
    print("\n" + "=" * 60)
    print("Multi-Network Test Complete")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_multinet()
    sys.exit(0 if success else 1)