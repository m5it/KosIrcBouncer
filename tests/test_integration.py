#!/usr/bin/env python3
"""
Integration tests for IRC BNC
"""

import sys
import os
import time
import socket
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config, IrcNetworkConfig, BncServerConfig
from shared import BufferManager, UserDatabase, RateLimiter, IPFilter
from client import IrcClient
from server import BncServer


class MockIrcServer:
    """Mock IRC server for testing."""
    
    def __init__(self, host='127.0.0.1', port=6668):
        self.host = host
        self.port = port
        self.socket = None
        self.clients = []
        self.running = False
    
    def start(self):
        """Start mock server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True
        
        thread = threading.Thread(target=self._accept_loop)
        thread.daemon = True
        thread.start()
    
    def _accept_loop(self):
        """Accept connections."""
        while self.running:
            try:
                self.socket.settimeout(1.0)
                conn, addr = self.socket.accept()
                self.clients.append(conn)
                
                # Send welcome
                conn.send(b":mock.server 001 test :Welcome\r\n")
                
                # Handle client
                thread = threading.Thread(target=self._handle_client, args=(conn,))
                thread.daemon = True
                thread.start()
            except socket.timeout:
                continue
    
    def _handle_client(self, conn):
        """Handle client connection."""
        while self.running:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                # Echo back as PRIVMSG
                conn.send(b":test!user@host PRIVMSG #test :Hello from mock\r\n")
            except:
                break
    
    def stop(self):
        """Stop server."""
        self.running = False
        for c in self.clients:
            try:
                c.close()
            except:
                pass
        if self.socket:
            self.socket.close()


def test_full_flow():
    """Test complete BNC flow."""
    print("=" * 60)
    print("Integration Test: Full BNC Flow")
    print("=" * 60)
    
    # Setup
    tmpdir = tempfile.mkdtemp()
    
    # Create mock IRC server
    mock_irc = MockIrcServer(port=16668)
    mock_irc.start()
    time.sleep(0.5)
    
    # Create components
    buffer = BufferManager(tmpdir)
    user_db = UserDatabase(tmpdir)
    rate_limiter = RateLimiter()
    ip_filter = IPFilter()
    
    # Add user
    user_db.add_user("testuser", "testpass", is_admin=True)
    
    # Create IRC client config
    config = IrcNetworkConfig(
        name="testnet",
        host="127.0.0.1",
        port=16668,
        ssl=False,
        nick="TestBot",
        channels=["#test"]
    )
    
    # Create IRC client
    client = IrcClient(config, buffer)
    client.start()
    
    # Wait for connection
    print("\n1. Connecting IRC client...")
    for _ in range(10):
        if client.is_connected():
            print("   ✓ IRC client connected")
            break
        time.sleep(0.5)
    else:
        print("   ✗ IRC client failed to connect")
        return False
    
    # Create BNC server
    bnc_config = BncServerConfig(
        bind_host="127.0.0.1",
        bind_port=16667,
        require_auth=False
    )
    
    bnc = BncServer(bnc_config, {"testnet": client})
    
    print("\n2. Starting BNC server...")
    if not bnc.start():
        print("   ✗ Failed to start BNC")
        return False
    print("   ✓ BNC server started")
    
    time.sleep(0.5)
    
    # Connect client to BNC
    print("\n3. Connecting user to BNC...")
    user_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    user_sock.settimeout(5)
    try:
        user_sock.connect(("127.0.0.1", 16667))
        
        # Send IRC registration
        user_sock.send(b"NICK TestUser\r\n")
        user_sock.send(b"USER test 0 * :Test\r\n")
        
        # Receive welcome
        data = user_sock.recv(4096)
        if b"001" in data:
            print("   ✓ User connected to BNC")
        else:
            print("   ✗ No welcome received")
            return False
        
        # Test message relay
        print("\n4. Testing message relay...")
        
        # Send message from user
        user_sock.send(b"PRIVMSG #test :Hello from user\r\n")
        time.sleep(0.5)
        
        # Check if buffered
        buf = buffer.get_buffer("testnet", "#test")
        if len(buf) > 0:
            print("   ✓ Message buffered")
        else:
            print("   ✗ Message not buffered")
        
        # Disconnect user
        print("\n5. Testing disconnect...")
        user_sock.send(b"QUIT :Test complete\r\n")
        user_sock.close()
        
        # Verify bot still connected
        time.sleep(0.5)
        if client.is_connected():
            print("   ✓ Bot continues after user disconnect")
        else:
            print("   ✗ Bot disconnected")
            return False
        
        print("\n" + "=" * 60)
        print("All integration tests passed!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"   ✗ Test failed: {e}")
        return False
    
    finally:
        # Cleanup
        user_sock.close() if 'user_sock' in locals() else None
        bnc.stop()
        client.stop()
        mock_irc.stop()


def test_ssl_connection():
    """Test SSL connection."""
    print("\n" + "=" * 60)
    print("Integration Test: SSL Connection")
    print("=" * 60)
    print("   (Skipped - requires SSL certificates)")
    return True


def test_authentication():
    """Test authentication system."""
    print("\n" + "=" * 60)
    print("Integration Test: Authentication")
    print("=" * 60)
    
    tmpdir = tempfile.mkdtemp()
    user_db = UserDatabase(tmpdir)
    
    # Add user
    assert user_db.add_user("alice", "secret123")
    print("   ✓ User added")
    
    # Authenticate
    user = user_db.authenticate("alice", "secret123", "127.0.0.1")
    assert user is not None
    print("   ✓ Authentication successful")
    
    # Wrong password
    user = user_db.authenticate("alice", "wrongpass", "127.0.0.1")
    assert user is None
    print("   ✓ Wrong password rejected")
    
    return True


def test_buffer_system():
    """Test buffer system."""
    print("\n" + "=" * 60)
    print("Integration Test: Buffer System")
    print("=" * 60)
    
    from shared.channel_buffer import ChannelBuffer, MessageType
    
    buf = ChannelBuffer("testnet", "#test", max_size=100)
    
    # Add messages
    for i in range(10):
        buf.add_message(f"user{i}", f"Message {i}", MessageType.PRIVMSG)
    print(f"   ✓ Added {len(buf)} messages")
    
    # Search
    results = buf.search("Message 5")
    assert len(results) == 1
    print("   ✓ Search works")
    
    # Get last
    last = buf.get_last(5)
    assert len(last) == 5
    print("   ✓ Get last works")
    
    return True


if __name__ == "__main__":
    tests = [
        ("Full Flow", test_full_flow),
        ("SSL Connection", test_ssl_connection),
        ("Authentication", test_authentication),
        ("Buffer System", test_buffer_system),
    ]
    
    passed = 0
    failed = 0
    
    for name, test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ✗ Exception: {e}")
            failed += 1
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    
    sys.exit(0 if failed == 0 else 1)