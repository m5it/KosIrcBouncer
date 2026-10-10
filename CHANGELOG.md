# Changelog

All notable changes to the IRC BNC project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Real IRC session replay on attach**: When an IRC client reconnects, the BNC now replays the upstream server's actual registration burst (001, 002, 003, MOTD, NickServ notices, etc.) instead of fake BNC welcome messages.
- **Persistent channels**: Channels joined by the user are saved per-network in `users.json` and automatically rejoined on the next login.
- **Live channel state replay**: Re-joining a channel replays channel modes, creation time, a freshly generated `353 RPL_NAMREPLY`/`366 RPL_ENDOFNAMES` user list, and cached `352 RPL_WHOREPLY`/`315 RPL_ENDOFWHO` replies.
- **Live channel user tracking**: `IrcClient` now maintains per-channel user lists updated from `JOIN`, `PART`, `QUIT`, `KICK`, `NICK` and `MODE +/-o/v/h/a/q` events.
- **Message buffering**: All IRC traffic received while the user is detached is buffered and replayed when the user re-attaches.
- **`/BNC LOGIN <username> <password>` command**: Manual BNC authentication for clients that do not send a server password.
- **`generate_hashed_password.py` helper**: Convenient script to produce PBKDF2 password hashes for `config.json`.
- **IPv6 Support**: Full dual-stack IPv4/IPv6 support for IRC connections
  - Automatic address resolution using `socket.getaddrinfo()` for both IPv4 and IPv6
  - Automatic fallback from IPv6 to IPv4 when IPv6 is unavailable
  - Dual-stack socket support with `IPV6_V6ONLY` disabled for maximum compatibility
  - Connection statistics now report address family (IPv4/IPv6)
  - New configuration option `ipv6_only` to force IPv6-only mode
  - Default bind address changed from `0.0.0.0` to `::` (dual-stack)

### Changed
- **Configuration**: Default `bind_host` in `BncServerConfig` changed from `"0.0.0.0"` to `"::"` to enable dual-stack support by default
- **Connection handling**: Improved connection resilience with multiple address family attempts
- **Authentication**: User accounts from `config.json` are now loaded into `UserDatabase` at startup and used to validate `PASS` and `/BNC LOGIN`.
- **Channel metadata handling**: Per-channel numerics (324/329/352/353/366/315) are no longer buffered globally, preventing duplication and preserving correct message order on replay.

### Fixed
- Fixed upstream IRC reconnect after ping timeout: `IrcConnection` is now recreated on every reconnect and the IRC client sends keepalive PINGs / detects dead connections after 180s of inactivity.
- Fixed `/NAMES` re-attach to include `366 RPL_ENDOFNAMES`.
- Fixed comma-separated `JOIN #chan1,#chan2` being stored as a single corrupted channel name.
- Fixed `BNC LOGIN` being rejected before authentication.
- Fixed `WHO`/`MODE` pass-through so the IRC client receives live server replies.
- Fixed `WHOIS` to forward to the IRC server and return real replies.
- Fixed auto-op for users joining after the BNC is already in a channel by using the hostmask directly from the JOIN message prefix instead of waiting for WHO replies.
- Fixed auto-op handling of WHO replies with channel `*`: the BNC now checks every channel the nick is known to be in when the reply channel is not a real channel name.
- Fixed re-attach hostmask detection using the wrong `WHO` reply parameter for the user's own nick (status field was used instead of the nick field).
- Fixed wildcard matching in auto-op masks by replacing the hand-rolled matcher with `fnmatch.fnmatchcase`, correctly supporting `*`, `?` and multi-part wildcards such as `realt3ch!*@*.example.com`.
- Removed proactive `WHO` requests from auto-op: the BNC no longer sends extra WHO traffic; it relies on hostmasks already present in normal IRC traffic (JOIN prefixes, NAMES, client-requested WHO).

### Technical Details
- Added `registration_burst`, `channel_users`, `channel_names`, `channel_who`, `channel_modes` and `hostmask` to `IrcState`.
- Added `saved_channels` and `auto_op` to `UserAccount` for persistent channel storage and auto-op masks.
- Implemented `IrcClient.build_names_list()` to generate fresh `353/366` replies from the live tracked user list.
- Updated `UserSession` to delegate all `/BNC` commands through `BncCommandHandler`.
- Modified `IrcConnection` class to use `socket.getaddrinfo()` instead of hardcoded `AF_INET`
- Added `_addr_family` tracking to connection statistics
- Added dual-stack socket option setting for IPv6 sockets
- Updated configuration dataclass with `ipv6_only` option

## [1.0.0] - 2024-XX-XX

### Added
- Initial release of IRC BNC
- Multi-network support
- Persistent connections
- Basic message buffering
- Web dashboard
- SSL/TLS support
- User authentication
- Admin commands
- Docker support
- Systemd service support