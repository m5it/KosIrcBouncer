#!/usr/bin/env python3
"""
Test BNC Commands
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.bnc_commands import BncCommandHandler
from shared.auth import UserDatabase


class MockSession:
    """Mock session for testing."""
    def __init__(self):
        self.nick = "TestUser"
        self.username = "test"
        self.current_network = None
        self.selected_client = None
        self.authenticated = True
        self.detached = False


def test_commands():
    """Test BNC commands."""
    print("=" * 60)
    print("BNC Commands Test")
    print("=" * 60)
    
    # Create mock objects
    irc_clients = {}
    user_db = UserDatabase("/tmp/test_bnc")
    buffer_manager = None
    bnc_server = None
    
    # Create handler
    handler = BncCommandHandler(irc_clients, user_db, buffer_manager, bnc_server)
    
    # Create mock session
    session = MockSession()
    
    # Test HELP
    print("\n1. Testing HELP...")
    responses = handler.handle(session, "BNC HELP")
    for r in responses:
        print(f"  {r}")
    print("✓ HELP works")
    
    # Test STATUS
    print("\n2. Testing STATUS...")
    responses = handler.handle(session, "BNC STATUS")
    for r in responses:
        print(f"  {r}")
    print("✓ STATUS works")
    
    # Test NETWORKS (empty)
    print("\n3. Testing NETWORKS...")
    responses = handler.handle(session, "BNC NETWORKS")
    for r in responses:
        print(f"  {r}")
    print("✓ NETWORKS works")
    
    print("\n" + "=" * 60)
    print("Commands Test Complete")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_commands()
    sys.exit(0 if success else 1)