"""
Authentication and security module for IRC BNC.
"""

import hashlib
import secrets
import time
import ipaddress
from typing import Optional, Set, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading


class PasswordHasher:
    """Secure password hashing using PBKDF2."""
    
    @staticmethod
    def hash(password: str) -> str:
        """Hash password with salt."""
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 100k iterations
        ).hex()
        return f"{salt}${hashed}"
    
    @staticmethod
    def verify(password: str, hashed: str) -> bool:
        """Verify password against hash."""
        try:
            salt, stored_hash = hashed.split('$', 1)
            computed = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            ).hex()
            return secrets.compare_digest(computed, stored_hash)
        except ValueError:
            return False


@dataclass
class UserAccount:
    """User account with credentials and permissions."""
    username: str
    password_hash: str
    is_admin: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    failed_logins: int = 0
    locked_until: Optional[datetime] = None
    allowed_networks: Set[str] = field(default_factory=set)
    allowed_ips: Set[str] = field(default_factory=set)  # CIDR notation
    saved_channels: Dict[str, Set[str]] = field(default_factory=dict)  # network -> channels
    # network -> channel -> list of nick!user@host masks to auto-op on join
    auto_op: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    
    def check_password(self, password: str) -> bool:
        """Verify password."""
        if self.locked_until and datetime.now() < self.locked_until:
            return False
        
        if PasswordHasher.verify(password, self.password_hash):
            self.failed_logins = 0
            self.last_login = datetime.now()
            return True
        else:
            self.failed_logins += 1
            if self.failed_logins >= 5:
                self.locked_until = datetime.now() + timedelta(minutes=30)
            return False
    
    def is_locked(self) -> bool:
        """Check if account is locked."""
        if self.locked_until and datetime.now() < self.locked_until:
            return True
        return False
    
    def ip_allowed(self, ip: str) -> bool:
        """Check if IP is allowed."""
        if not self.allowed_ips:
            return True  # No restrictions
        
        client_ip = ipaddress.ip_address(ip)
        for cidr in self.allowed_ips:
            if client_ip in ipaddress.ip_network(cidr):
                return True
        return False

    def get_auto_op_masks(self, network: str, channel: str) -> List[str]:
        """Return auto-op masks for a network and channel."""
        return self.auto_op.get(network, {}).get(channel.lower(), [])

    @staticmethod
    def mask_matches(mask: str, nick: str, ident: str, host: str) -> bool:
        """Check if nick!ident@host matches a wildcard mask."""
        if '!' not in mask or '@' not in mask:
            return False
        m_nick, rest = mask.split('!', 1)
        m_ident, m_host = rest.split('@', 1)

        def wc_match(pattern: str, text: str) -> bool:
            if pattern == '*':
                return True
            # Simple * wildcard matching.
            parts = pattern.lower().split('*')
            if parts[0] and not text.lower().startswith(parts[0]):
                return False
            if parts[-1] and not text.lower().endswith(parts[-1]):
                return False
            pos = 0
            for part in parts:
                if not part:
                    continue
                idx = text.lower().find(part, pos)
                if idx == -1:
                    return False
                pos = idx + len(part)
            return True

        return wc_match(m_nick, nick) and wc_match(m_ident, ident) and wc_match(m_host, host)


class UserDatabase:
    """Persistent user storage."""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.users: Dict[str, UserAccount] = {}
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        """Load users from JSON."""
        import os
        import json
        
        filepath = os.path.join(self.data_dir, 'users.json')
        if not os.path.exists(filepath):
            return
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                for username, user_data in data.items():
                    self.users[username] = UserAccount(
                        username=user_data['username'],
                        password_hash=user_data['password_hash'],
                        is_admin=user_data.get('is_admin', False),
                        allowed_networks=set(user_data.get('allowed_networks', [])),
                        allowed_ips=set(user_data.get('allowed_ips', [])),
                        saved_channels={
                            net: set(chans)
                            for net, chans in user_data.get('saved_channels', {}).items()
                        },
                        auto_op={
                            net: {
                                ch.lower(): list(masks)
                                for ch, masks in channels.items()
                            }
                            for net, channels in user_data.get('auto_op', {}).items()
                        }
                    )
        except Exception as e:
            print(f"[Auth] Failed to load users: {e}")
    
    def save(self):
        """Save users to JSON."""
        import os
        import json
        
        os.makedirs(self.data_dir, exist_ok=True)
        filepath = os.path.join(self.data_dir, 'users.json')
        
        data = {}
        for username, user in self.users.items():
            data[username] = {
                'username': user.username,
                'password_hash': user.password_hash,
                'is_admin': user.is_admin,
                'allowed_networks': list(user.allowed_networks),
                'allowed_ips': list(user.allowed_ips),
                'saved_channels': {
                    net: list(chans) for net, chans in user.saved_channels.items()
                },
                'auto_op': {
                    net: {
                        ch: list(masks) for ch, masks in channels.items()
                    }
                    for net, channels in user.auto_op.items()
                },
            }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_user(self, username: str, password: str, is_admin: bool = False) -> bool:
        """Add new user."""
        with self._lock:
            if username in self.users:
                return False
            
            hashed = PasswordHasher.hash(password)
            self.users[username] = UserAccount(
                username=username,
                password_hash=hashed,
                is_admin=is_admin
            )
            self.save()
            return True
    
    def authenticate(self, username: str, password: str, ip: str) -> Optional[UserAccount]:
        """Authenticate user."""
        with self._lock:
            user = self.users.get(username)
            if not user:
                return None
            
            if not user.ip_allowed(ip):
                return None
            
            if user.check_password(password):
                return user
            else:
                self.save()  # Update failed login count
                return None
    
    def get_user(self, username: str) -> Optional[UserAccount]:
        """Get user by username."""
        return self.users.get(username)
    
    def delete_user(self, username: str) -> bool:
        """Delete user."""
        with self._lock:
            if username in self.users:
                del self.users[username]
                self.save()
                return True
            return False


class RateLimiter:
    """Rate limiting for connections."""
    
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self.attempts: Dict[str, List[datetime]] = {}
        self._lock = threading.Lock()
    
    def is_allowed(self, ip: str) -> bool:
        """Check if IP is allowed to attempt connection."""
        with self._lock:
            now = datetime.now()
            ip_attempts = self.attempts.get(ip, [])
            
            # Remove old attempts
            ip_attempts = [t for t in ip_attempts if now - t < self.window]
            self.attempts[ip] = ip_attempts
            
            return len(ip_attempts) < self.max_attempts
    
    def record_attempt(self, ip: str):
        """Record connection attempt."""
        with self._lock:
            if ip not in self.attempts:
                self.attempts[ip] = []
            self.attempts[ip].append(datetime.now())


class IPFilter:
    """IP whitelist/blacklist filtering."""
    
    def __init__(self):
        self.whitelist: Set[str] = set()  # CIDR notation
        self.blacklist: Set[str] = set()  # CIDR notation
        self._lock = threading.Lock()
    
    def add_to_whitelist(self, cidr: str):
        """Add CIDR to whitelist."""
        with self._lock:
            self.whitelist.add(cidr)
    
    def add_to_blacklist(self, cidr: str):
        """Add CIDR to blacklist."""
        with self._lock:
            self.blacklist.add(cidr)
    
    def is_allowed(self, ip: str) -> bool:
        """Check if IP is allowed."""
        client_ip = ipaddress.ip_address(ip)
        
        with self._lock:
            # Check blacklist first
            for cidr in self.blacklist:
                if client_ip in ipaddress.ip_network(cidr):
                    return False
            
            # If whitelist exists, must be in it
            if self.whitelist:
                for cidr in self.whitelist:
                    if client_ip in ipaddress.ip_network(cidr):
                        return True
                return False
            
            return True
    
    def remove_from_whitelist(self, cidr: str):
        """Remove from whitelist."""
        with self._lock:
            self.whitelist.discard(cidr)
    
    def remove_from_blacklist(self, cidr: str):
        """Remove from blacklist."""
        with self._lock:
            self.blacklist.discard(cidr)