# Changelog

All notable changes to the IRC BNC project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-11-01

### Added
- **External hook system**: Run user-provided shell scripts on IRC events. Hook files live in `hooks/` (or `$BNC_DATA_DIR/hooks`) and are discovered at runtime without requiring a restart.
  - Global hooks (`PRIVMSG.hook`), network-specific hooks (`libera_PRIVMSG.hook`) and channel-specific hooks (`grandekos.com_JOIN.hook`) are resolved in priority order across `hooks/` and extra hooks directories.
  - 17 event types: `PRIVMSG`, `NOTICE`, `JOIN`, `PART`, `KICK`, `MODE`, `OP`, `DEOP`, `VOICE`, `DEVOICE`, `BAN`, `UNBAN`, `TOPIC`, `QUIT`, `NICK`, `CONNECT`, `DISCONNECT` (mode sub-events `HOP`/`DEHOP`, `ADMIN`/`DEADMIN`, `OWNER`/`DEOWNER` also fire from MODE changes).
  - Every hook receives context via environment variables (`IRC_NETWORK`, `IRC_SERVER`, `IRC_EVENT`, `IRC_CHANNEL`, `IRC_NICK`, `IRC_IDENT`, `IRC_HOST`, `IRC_TARGET`, `IRC_TEXT`, `IRC_MODE`, `IRC_RAW`, `IRC_BOT_NICK`) and positional args `$1=network $2=event [$3=channel $4=nick $5=target $6=text]`.
  - Hooks execute in background daemon threads with a 30s timeout; non-zero exits and stderr are logged.
  - Example hooks: `hooks/example_PRIVMSG.hook`, `hooks/example_OP.hook`, `hooks/grandekos.com_JOIN.hook`.
- **Hook-to-IRC bridge**: Hooks can send IRC commands upstream by echoing them to stdout. The BNC intercepts lines whose first word is a supported command and forwards them via the rate-limited upstream send path.
  - Supported send prefixes: `PRIVMSG`, `NOTICE`, `MODE`, `KICK`, `TOPIC`, `INVITE`, `JOIN`, `PART`, `QUIT`, `NICK`, `AWAY`, `WHO`, `WHOIS`, `LIST`, `NAMES`, `RAW` (case-insensitive). `RAW <line>` sends the remainder verbatim for arbitrary IRC commands. Non-command stdout is only logged.
  - Example: `echo "PRIVMSG $IRC_CHANNEL :Hello $IRC_NICK from hook!"` / `echo "MODE $IRC_CHANNEL +v $IRC_NICK"` / `echo "NOTICE $IRC_NICK :Got your message"`.

### Changed
- **Upstream MODE handling**: `IrcClient._handle_mode` now requires only 2 params, tracks `+/-o/v/h/a/q` with prefix accumulation, and fires dedicated `OP`/`DEOP`/`VOICE`/`DEVOICE`/`HOP`/`DEHOP`/`ADMIN`/`DEADMIN`/`OWNER`/`DEOWNER` hooks plus a generic `MODE` hook.
- **TOPIC tracking**: Added `IrcClient._handle_topic` to fire `TOPIC` hooks.
- **NOTICE/PRIVMSG hooks**: `PRIVMSG` and `NOTICE` now fire hook events with full context; `QUIT`, `PART`, `JOIN`, `KICK`, `NICK` hooks also carry reason/target info.
- **Connection lifecycle hooks**: `CONNECT` fires in `_on_connected`, `DISCONNECT` fires in `_on_disconnected` (called after keepalive loop exits).
- **Buffer resilience**: `IrcClient` methods now guard against `buffer_manager=None` to support test/embedded usage.
- **BNC startup**: `main.py` wires a `HookManager` (data-dir hooks + project `hooks/` as fallback) into each `IrcClient` at startup.

### Fixed
- Fixed `KICK` channel lookup using lowercased keys consistently.

## [1.1.1] - 2026-10-31

### Added
- **Upstream rate limiting**: Added throttling on all outgoing upstream IRC traffic to avoid "Excess Flood" disconnects.
- **Nickname sync on attach**: If the upstream IRC client ends up with a different nick (e.g. `t3ch_`), the BNC tells the downstream client its real nick before replaying JOIN/NAMES.
- **Replay line rewriting**: Cached numeric replies, NAMES, WHO, and buffered messages are rewritten so a nickname change does not leave stale nicknames in replayed traffic.

### Changed
- **Attach channel handling**: Only channels already joined upstream are replayed as "JOINed" immediately. Channels in the saved list that are not yet joined get a real upstream JOIN request; fake JOINs are no longer sent for failed or pending joins.

### Fixed
- Fixed Excess Flood disconnects caused by rapid auto-joins, attach replay, and auto-op MODE commands.
- Fixed channels not appearing joined in the IRC client when the upstream nick differs from the session nick.
- Fixed persistent nickname changes being lost on upstream reconnect.
- Fixed user disconnect killing the upstream IRC client.

## [1.1.0] - 2026-10-30

### Added
- **Per-user auto-op**: Configure hostmask patterns per network and channel to automatically grant operator status when matching users join.
- **BNC debug command**: Added a debug command for inspecting BNC state.
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
- **Auto-join channel persistence**: Explicitly parting a channel removes it from the saved auto-join list so it is not rejoined after a restart.

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
- Fixed disconnect handling so a detached IRC client does not leave its session in an inconsistent state.
- Fixed nickname-change handling to keep tracked channel and session state in sync.

### Technical Details
- Added `registration_burst`, `channel_users`, `channel_names`, `channel_who`, `channel_modes` and `hostmask` to `IrcState`.
- Added `saved_channels` and `auto_op` to `UserAccount` for persistent channel storage and auto-op masks.
- Implemented `IrcClient.build_names_list()` to generate fresh `353/366` replies from the live tracked user list.
- Updated `UserSession` to delegate all `/BNC` commands through `BncCommandHandler`.
- Modified `IrcConnection` class to use `socket.getaddrinfo()` instead of hardcoded `AF_INET`
- Added `_addr_family` tracking to connection statistics
- Added dual-stack socket option setting for IPv6 sockets
- Updated configuration dataclass with `ipv6_only` option

## [1.0.0] - 2026-10-10

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