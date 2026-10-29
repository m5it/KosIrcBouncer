#!/usr/bin/env python3
"""
Test that outgoing upstream messages are rate-limited.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Avoid triggering circular imports in the package by importing the module
# directly instead of the package __init__.
from client.connection import IrcConnection


class FakeSocket:
    """Captures sendall calls."""
    def __init__(self):
        self.sent = []
        self.closed = False

    def sendall(self, data):
        self.sent.append((time.time(), data))

    def close(self):
        self.closed = True

    def settimeout(self, *args):
        pass


def test_rate_limiting():
    conn = IrcConnection("localhost", 6667, use_ssl=False)
    conn.connected = True
    fake = FakeSocket()
    conn.socket = fake
    conn.last_activity = time.time()

    start = time.time()
    for i in range(5):
        conn.send(f"PRIVMSG #test :message {i}")
    elapsed = time.time() - start

    assert len(fake.sent) == 5, f"Expected 5 sends, got {len(fake.sent)}"
    # With min interval 0.35s and window max 3, 5 messages should take > 1s
    assert elapsed >= 1.0, f"Rate limiting too fast: {elapsed:.2f}s"

    # Verify intervals are sane
    for i in range(1, len(fake.sent)):
        delta = fake.sent[i][0] - fake.sent[i-1][0]
        assert delta >= 0.33, f"Interval too small: {delta:.3f}s"

    print(f"✓ 5 messages took {elapsed:.2f}s (rate limited)")


if __name__ == "__main__":
    test_rate_limiting()
    print("All rate-limit tests passed!")
