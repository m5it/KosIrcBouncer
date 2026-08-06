#!/usr/bin/env python3
"""Test BNC status messages by simulating an IRC client connection."""

import socket
import sys
import time
import threading

HOST = '127.0.0.1'
PORT = 6667
NICK = 'TestUser'
USER = 'testuser'

def receive_all(sock, timeout=5.0):
    """Receive data until timeout."""
    sock.settimeout(timeout)
    data = b''
    start = time.time()
    while time.time() - start < timeout:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    return data.decode('utf-8', errors='replace')

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
        print(f"[TEST] Connected to BNC at {HOST}:{PORT}")
        
        # Read initial welcome/status from BNC
        initial = receive_all(sock, 2.0)
        print("[TEST] Initial BNC output:")
        print(initial)
        print("---")
        
        # Send IRC registration
        sock.send(f"NICK {NICK}\r\n".encode())
        sock.send(f"USER {USER} 0 * :Test User\r\n".encode())
        
        # Read response after registration
        response = receive_all(sock, 2.0)
        print("[TEST] Output after NICK/USER:")
        print(response)
        print("---")
        
        # Check for expected status messages
        combined = initial + response
        expected = [
            'Welcome to IRC BNC',
            'Available networks',
            'Auto-attaching',
            'Welcome to BNC'
        ]
        
        missing = [e for e in expected if e not in combined]
        if missing:
            print(f"[TEST] MISSING expected messages: {missing}")
            return 1
        else:
            print("[TEST] All expected status messages found!")
            return 0
            
    except Exception as e:
        print(f"[TEST] Error: {e}")
        return 1
    finally:
        try:
            sock.close()
        except:
            pass

if __name__ == '__main__':
    sys.exit(main())
