# IRC BNC - IRC Bouncer System

A complete IRC bouncer with client-server architecture. Connect your IRC client (HexChat, irssi, weechat, etc.) to the BNC, and the BNC maintains persistent connections to IRC networks on your behalf.

## Features

- **Multi-Network Support**: Connect to multiple IRC networks simultaneously (Libera, EFnet, OFTC, etc.)
- **IPv6 Support**: Full dual-stack IPv4/IPv6 support for connecting to modern IRC networks
- **Persistent Connections**: The bot stays connected to IRC while your client is offline
- **Message Buffering**: Full playback of missed channel/query traffic when you reconnect
- **Channel State Replay**: Rejoins saved channels, restores user lists, modes and topics on re-attachment
- **Web Dashboard**: Real-time monitoring and web-based IRC client
- **SSL/TLS Support**: Encrypted connections to IRC and BNC
- **Authentication**: Secure user management with PBKDF2-hashed passwords
- **Admin Commands**: Full control via `/BNC` commands

## Architecture

```
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
pip install -r requirements.txt

# Run BNC
python main.py
```

### Configuration

Create `config.json` in the project root:

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
      "password_hash": "$2a$12$...",
      "is_admin": true
    }
  ]
}
```

**Note:** The default `bind_host` is `"::"` which enables dual-stack IPv4/IPv6 support. Use `"0.0.0.0"` for IPv4-only or set `ipv6_only: true` for IPv6-only mode.

### Password Generation

Passwords must be **pre-hashed** before being placed in `config.json`. Do **not** write plain-text passwords in the config file.

Generate a password hash using the helper script:

```bash
python generate_hashed_password.py yourpassword
```

Or interactively:

```bash
python generate_hashed_password.py
```

Example output:

```
a3f5c8e9d2b1...$7a8b9c0d1e2f...
```

Then copy the full hash into your user's `password_hash` field:

```json
{
  "username": "admin",
  "password_hash": "a3f5c8e9d2b1...$7a8b9c0d1e2f...",
  "is_admin": true
}
```

When connecting with your IRC client, use the **plain password** (the original `yourpassword`), not the hash.

### Connect with HexChat

1. Open HexChat
2. Add new server: `/server add BNC localhost/6667`
3. Set the server password to your plain BNC password (Network list → Edit → Server password)
4. Connect: `/connect BNC`
5. The BNC will authenticate you automatically and attach to the configured IRC network.

You can also authenticate manually after connecting without a server password:

```
/BNC LOGIN yourusername yourpassword
```

## BNC Commands

| Command | Description |
|---------|-------------|
| `/BNC LOGIN <username> <password>` | Authenticate with the BNC |
| `/BNC CONNECT <network>` | Attach to an IRC network |
| `/BNC DISCONNECT` | Disconnect from current network |
| `/BNC STATUS` | Show connection status |
| `/BNC JUMP` | Reconnect to server |
| `/BNC SAY <target> <msg>` | Send message as bot |
| `/BNC RAW <command>` | Send raw IRC command to IRC server |
| `/BNC DETACH` | Detach (bot continues running) |
| `/BNC ATTACH` | Reattach to session |
| `/BNC NETWORKS` | List available networks |
| `/BNC ADDUSER <user> <pass> [admin]` | Add user (admin) |
| `/BNC DELUSER <user>` | Delete user (admin) |
| `/BNC LISTUSERS` | List users (admin) |
| `/BNC SETPASS <user> <password>` | Change user password (admin) |

## Persistent Channels and Replay

When you `/JOIN` a channel through the BNC, the channel is saved to your user account. When you log back in later:

- The BNC automatically rejoins your saved channels
- The original IRC server registration burst (001, 002, 003, MOTD, etc.) is replayed
- Channel modes, topics and live user lists are replayed
- Missed channel messages and notices are replayed from the buffer

Channels you `/PART` are removed from your saved list automatically.

## Web Dashboard

Access at `http://localhost:8080`

Features:
- Real-time connection status
- Message buffer viewer
- Network management
- User monitoring
- Web-based IRC client (WebSocket)

## Docker Deployment

```bash
# Build image
docker build -t irc-bnc .

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

## IPv6 Configuration

The BNC supports full IPv6 connectivity:

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
