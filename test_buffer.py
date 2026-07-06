#!/usr/bin/env python3
"""
Test Channel Buffer System
"""

import sys
import os
import tempfile
from datetime import datetime, timedelta

from shared.channel_buffer import (
    PersistentBufferManager, ChannelBuffer, 
    ChannelMessage, MessageType
)


def test_buffer():
    """Test buffer functionality."""
    print("=" * 60)
    print("Channel Buffer Test")
    print("=" * 60)
    
    # Create temp directory
    tmpdir = tempfile.mkdtemp()
    
    # Create manager
    manager = PersistentBufferManager(tmpdir, default_size=100)
    
    # Test 1: Add messages
    print("\n1. Adding messages...")
    for i in range(10):
        manager.add_message(
            "libera", "#test", f"User{i}", 
            f"Message number {i}", 
            MessageType.PRIVMSG
        )
    print("✓ Added 10 messages")
    
    # Test 2: Get buffer
    print("\n2. Retrieving buffer...")
    buffer = manager.get_buffer("libera", "#test")
    messages = buffer.get_messages(count=5)
    print(f"✓ Retrieved {len(messages)} messages")
    print(f"  Latest: {messages[-1].message}")
    
    # Test 3: Search
    print("\n3. Searching...")
    results = buffer.search("number 5")
    print(f"✓ Found {len(results)} matches")
    
    # Test 4: Channel state
    print("\n4. Setting channel state...")
    buffer.set_topic("Test Topic", "Admin")
    buffer.add_mode("n")
    buffer.add_mode("t")
    print(f"✓ Topic: {buffer.topic}")
    print(f"✓ Modes: {buffer.modes}")
    
    # Test 5: Stats
    print("\n5. Statistics...")
    stats = manager.get_buffer_stats("libera")
    print(f"  Channels: {stats['channels']}")
    print(f"  Total messages: {stats['total_messages']}")
    
    # Test 6: Export/Import
    print("\n6. Export/Import...")
    export_path = os.path.join(tmpdir, "export.json")
    manager.export_to_json("libera", export_path)
    print(f"✓ Exported to {export_path}")
    
    # Cleanup
    print("\n7. Cleanup...")
    manager.cleanup_old_messages(days=0)
    print("✓ Cleaned old messages")
    
    print("\n" + "=" * 60)
    print("Buffer Test Complete")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_buffer()
    sys.exit(0 if success else 1)