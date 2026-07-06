# Changelog

All notable changes to the IRC BNC project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Technical Details
- Modified `IrcConnection` class to use `socket.getaddrinfo()` instead of hardcoded `AF_INET`
- Added `_addr_family` tracking to connection statistics
- Added dual-stack socket option setting for IPv6 sockets
- Updated configuration dataclass with `ipv6_only` option

## [1.0.0] - 2024-XX-XX

### Added
- Initial release of IRC BNC
- Multi-network support
- Persistent connections
- Message buffering
- Web dashboard
- SSL/TLS support
- User authentication
- Admin commands
- Docker support
- Systemd service support