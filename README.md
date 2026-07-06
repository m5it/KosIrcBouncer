# IRC BNC - IRC Bouncer System

A complete IRC bouncer with client-server architecture. Connect your IRC client (HexChat, irssi, etc.) to the BNC, and the BNC maintains persistent connections to IRC networks.

## Features

- **Multi-Network Support**: Connect to multiple IRC networks simultaneously (Libera, EFnet, OFTC, etc.)
- **Persistent Connections**: Bot stays connected when you disconnect
## Features

- **Multi-Network Support**: Connect to multiple IRC networks simultaneously (Libera, EFnet, OFTC, etc.)
- **IPv6 Support**: Full dual-stack IPv4/IPv6 support for connecting to modern IRC networks
- **Persistent Connections**: Bot stays connected when you disconnect
- **Message Buffering**: Full playback of missed messages when you reconnect
- **Web Dashboard**: Real-time monitoring and web-based IRC client
- **SSL/TLS Support**: Encrypted connections to IRC and BNC
- **Authentication**: Secure user management with hashed passwords
- **Admin Commands**: Full control via `/BNC` commands
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   HexChat   │────▶│  BNC Server │────▶│ IRC Network │
│  (Client)   │◀────│   (:6667)   │◀────│  (Libera)   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                    ┌─────────────┐
                    │  Web Dashboard │
                    │   (:8080)   │
                    └─────────────┘
```

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/irc-bnc.git
cd irc-bnc

# Install dependencies
Create `config.json`:

```json
{
  "bnc_server": {
    "bind_host": "::",
    "bind_port": 6667,
    "ssl_cert": null,
    "ssl_key": null,
    "require_auth": true,
    "ipv6_only": false
  },
  "networks": [
    {
      "name": "libera",
      "host": "irc.libera.chat",
      "port": 6697,
      "ssl": true,
      "nick": "MyBNCBot",
      "channels": ["#general", "#random"]
    }
  ],
  "users": [
    {
      "username": "admin",
      "password_hash": "$salt$hash",
      "is_admin": true
    }
  ]
}
```

**Note:** The default `bind_host` is now `"::"` which enables dual-stack IPv4/IPv6 support. Use `"0.0.0.0"` for IPv4-only or set `ipv6_only: true` for IPv6-only mode.
{
  "bnc_server": {
    "bind_host": "0.0.0.0",
    "bind_port": 6667,
    "ssl_cert": null,
    "ssl_key": null,
    "require_auth": true
  },
  "networks": [
    {
      "name": "libera",
      "host": "irc.libera.chat",
      "port": 6697,
      "ssl": true,
      "nick": "MyBNCBot",
      "channels": ["#general", "#random"]
    }
  ],
  "users": [
    {
      "username": "admin",
      "password_hash": "$salt$hash",
      "is_admin": true
    }
  ]
}
```

### Connect with HexChat

1. Open HexChat
2. Add new server: `/server add BNC localhost/6667`
3. Connect: `/connect BNC`
4. Authenticate:
   ```
   /PASS yourpassword
   /NICK YourNick
   /USER yourusername 0 * :Real Name
   ```

## BNC Commands

| Command | Description |
|---------|-------------|
| `/BNC CONNECT <network>` | Connect to IRC network |
| `/BNC DISCONNECT` | Disconnect from current network |
| `/BNC STATUS` | Show connection status |
| `/BNC JUMP` | Reconnect to server |
| `/BNC SAY <target> <msg>` | Send message as bot |
| `/BNC RAW <command>` | Send raw IRC command |
| `/BNC DETACH` | Detach (bot continues) |
| `/BNC ATTACH` | Reattach to session |
| `/BNC NETWORKS` | List available networks |
| `/BNC ADDUSER <user> <pass>` | Add user (admin) |
| `/BNC LISTUSERS` | List users (admin) |

## Web Dashboard
Update config:
```json
{
  "bnc_server": {
    "ssl_cert": "cert.pem",
    "ssl_key": "key.pem"
  }
}
```

## IPv6 Configuration

The BNC now supports full IPv6 connectivity:

### Server Bind Options
- **`bind_host: "::"`** (default) - Dual-stack mode, accepts both IPv4 and IPv6 connections
- **`bind_host: "0.0.0.0"`** - IPv4-only mode
- **`bind_host: "::1"`** - IPv6 localhost only
- **`ipv6_only: true`** - Force IPv6-only mode (disables IPv4-mapped addresses)

### Client Connection Behavior
When connecting to IRC networks, the BNC automatically:
1. Resolves both IPv4 and IPv6 addresses for the target server
2. Attempts connections in order (IPv6 preferred on most systems)
3. Falls back to IPv4 if IPv6 fails
4. Reports the connection type in status/logs (IPv4 or IPv6)

### Verify IPv6 Connection
Use the `/BNC STATUS` command to see your connection details including the address family (IPv4/IPv6).

## License

MIT License - See LICENSE file
# Run container
docker run -d \
  -p 6667:6667 \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  --name irc-bnc \
  irc-bnc
```

## Systemd Service

Create `/etc/systemd/system/irc-bnc.service`:

```ini
[Unit]
Description=IRC BNC Service
After=network.target

[Service]
Type=simple
User=ircbnc
WorkingDirectory=/opt/irc-bnc
ExecStart=/usr/bin/python3 -m irc_bnc.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable irc-bnc
sudo systemctl start irc-bnc
```

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python irc_bnc/test_client.py
python irc_bnc/test_bnc.py
python irc_bnc/test_buffer.py
```

## SSL/TLS Setup

Generate certificates:
```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem \
  -days 365 -nodes
```

Update config:
```json
{
  "bnc_server": {
    "ssl_cert": "cert.pem",
    "ssl_key": "key.pem"
  }
}
```

## License

MIT License - See LICENSE file