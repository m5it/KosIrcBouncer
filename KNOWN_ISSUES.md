# Known Issues / Remaining Work

Items found during pre-release review of `master` (after `v1.0.0`). Deferred items are not blockers for personal use behind a firewall.

## Deferred to next version

### Security hardening
- **Upstream TLS certificates not verified** (`client/connection.py:81-82`): `check_hostname = False` and `verify_mode = CERT_NONE`. Restore default verification, with an explicit opt-in to disable it.
- **Insecure defaults without `config.json`** (`main.py:49-53`): binds `0.0.0.0` with `require_auth=False`. Default to authentication on and bind locally.
- **BNC commands allowed before login** (`server/user_session.py:173-183`, `server/bnc_commands.py:112`): an unauthenticated client can run e.g. `BNC DISCONNECT <network>`. Only allow `BNC LOGIN` before authentication.

### Functionality
- **`max_users` is not enforced** (`server/bnc_server.py:_handle_connection`): config value is exposed in stats but sessions are never limited.
- **Multi-network attach behavior** (`server/bnc_commands.py:90-110`): `BNC CONNECT` may not attach the session as expected. Deferred until multi-network testing is complete; revisit with observed behavior before changing it.

### Deployment
- **Docker/systemd entrypoints reference a nonexistent `irc_bnc` package** (`Dockerfile:22`, `systemd/irc-bnc.service:15`). Use `python main.py --config ...`.
- **`BNC_DATA_DIR` is ignored** (`config/settings.py:64`, `main.py:65`): data always goes to `~/.irc_bnc`. Fine for personal use; matters only for Docker/systemd volumes. Read the env var or a `data_dir` config key.

## Release housekeeping
- Replace placeholder URLs `github.com/yourusername/irc-bnc` in `README.md:37` and `systemd/irc-bnc.service:3`.
- `PLAN.md` still lists tasks 9-12 as `pending` although `current_task.txt` reports 12/12 complete.

## Tests
- Several tests `return True` instead of using `assert`, causing `PytestReturnNotNoneWarning` (`test_bnc.py`, `test_buffer.py`, `test_client.py`, `test_commands.py`, `test_multinet.py`, `tests/test_integration.py`).
- `pytest` is not listed in `requirements.txt`; there is no CI configuration.
- Runtime artifacts (`background.log`, `terminal_audit.log`, `state.aiia`, `current_task.txt`, `plans/`) are tracked in git; consider `.gitignore`.
