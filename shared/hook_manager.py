"""
Hook Manager for IRC BNC

Executes user-provided external scripts when certain IRC events happen.
Hook files live in the 'hooks' directory and are named like:
    <event>.hook           (global hook for an event)
    <network>_<event>.hook  (network-specific hook)
    #channel_<event>.hook  (channel-specific hook)

Event names: PRIVMSG, NOTICE, JOIN, PART, KICK, MODE, OP, DEOP, VOICE, DEVOICE,
BAN, UNBAN, TOPIC, QUIT, NICK, CONNECT, DISCONNECT.

Hook scripts receive arguments as environment variables plus positional args:
    $1 = network name
    $2 = event name
    $3..$N = event-specific fields

Environment variables (all uppercase):
    IRC_NETWORK   - network name (e.g. libera)
    IRC_SERVER    - IRC server host (e.g. irc.libera.chat)
    IRC_EVENT     - event name
    IRC_CHANNEL   - channel name when relevant
    IRC_NICK      - nick that triggered the event
    IRC_IDENT     - ident of the user
    IRC_HOST      - host of the user
    IRC_TARGET    - target of the event (kicked nick, changed-to nick, etc.)
    IRC_TEXT      - message text / topic / reason / mode string
    IRC_MODE      - mode change string (e.g. +o-o+v)
    IRC_RAW       - full raw IRC line
    IRC_BOT_NICK  - current BNC bot nick on that network

Sending to IRC from a hook:
    Echo IRC commands to stdout. The BNC intercepts them and sends them
    upstream. Supported sending prefixes (case-insensitive):
        PRIVMSG <target> :<text>
        NOTICE <target> :<text>
        MODE <target> <modes> [args]
        KICK <channel> <nick> [:reason]
        TOPIC <channel> :<topic>
        INVITE <nick> <channel>
        Any raw IRC line (e.g. WHOIS, WHO, LIST, etc.)

    Examples from inside a hook:
        echo "PRIVMSG $IRC_CHANNEL :Thanks for joining, $IRC_NICK!"
        echo "NOTICE $IRC_NICK :You are welcome"
        echo "MODE $IRC_CHANNEL +o $IRC_NICK"
        echo "KICK $IRC_CHANNEL spammer :No spam here"
"""

import os
import re
import subprocess
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class HookEvent:
    """Container for hook event data."""
    network: str = ""
    server: str = ''
    event: str = ""
    channel: Optional[str] = None
    nick: Optional[str] = None
    ident: Optional[str] = None
    host: Optional[str] = None
    target: Optional[str] = None
    text: Optional[str] = None
    mode: Optional[str] = None
    raw: Optional[str] = None
    bot_nick: Optional[str] = None


# Commands that a hook may send to the IRC server by printing them to stdout.
SEND_COMMANDS = frozenset({
    'PRIVMSG', 'NOTICE', 'MODE', 'KICK', 'TOPIC', 'INVITE',
    'JOIN', 'PART', 'QUIT', 'NICK', 'AWAY', 'WHO', 'WHOIS',
    'LIST', 'NAMES', 'RAW',
})


class HookManager:
    """Discovers and runs external hook scripts."""

    def __init__(self, hooks_dir: str = "hooks", extra_hooks_dirs: Optional[List[str]] = None):
        self.hooks_dir = hooks_dir
        self.extra_hooks_dirs = extra_hooks_dirs or []
        self._lock = threading.Lock()
        # Optional callback to send raw IRC lines upstream (set by IrcClient)
        self.send_callback: Optional[Callable[[str], None]] = None

    def _hook_paths(self, network: str, event: str, channel: Optional[str] = None) -> List[str]:
        """Return hook scripts to try in priority order."""
        candidates = []
        all_dirs = [self.hooks_dir] + self.extra_hooks_dirs
        # Channel-specific: #channel_EVENT.hook (with # stripped for filename safety)
        if channel:
            safe_channel = channel.lstrip('#&+!').replace('/', '_').replace('\\', '_')
            for d in all_dirs:
                candidates.append(os.path.join(d, f"{safe_channel}_{event.upper()}.hook"))
        # Network-specific: network_EVENT.hook
        safe_network = network.replace('/', '_').replace('\\', '_')
        for d in all_dirs:
            candidates.append(os.path.join(d, f"{safe_network}_{event.upper()}.hook"))
        # Global event hook
        for d in all_dirs:
            candidates.append(os.path.join(d, f"{event.upper()}.hook"))
        return candidates

    def _is_send_command(self, line: str) -> Optional[str]:
        """Return the normalized IRC command if the line looks like a sendable command."""
        stripped = line.lstrip()
        if not stripped:
            return None
        cmd = stripped.split(None, 1)[0].upper().rstrip(':')
        # Allow explicit RAW: prefix to send any raw line verbatim
        if cmd == 'RAW':
            return 'RAW'
        if cmd in SEND_COMMANDS:
            return cmd
        return None

    def _is_executable(self, path: str) -> bool:
        return os.path.isfile(path) and os.access(path, os.X_OK)

    def run(self, event: HookEvent) -> None:
        """Run all matching hooks for an event in background threads."""
        paths = self._hook_paths(event.network, event.event, event.channel)
        for path in paths:
            if self._is_executable(path):
                threading.Thread(
                    target=self._execute_hook,
                    args=(path, event),
                    daemon=True
                ).start()

    def _execute_hook(self, path: str, event: HookEvent) -> None:
        """Execute a single hook script."""
        env = os.environ.copy()
        env.update({
            'IRC_NETWORK': event.network or '',
            'IRC_SERVER': event.server or '',
            'IRC_EVENT': event.event or '',
            'IRC_CHANNEL': event.channel or '',
            'IRC_NICK': event.nick or '',
            'IRC_IDENT': event.ident or '',
            'IRC_HOST': event.host or '',
            'IRC_TARGET': event.target or '',
            'IRC_TEXT': event.text or '',
            'IRC_MODE': event.mode or '',
            'IRC_RAW': event.raw or '',
            'IRC_BOT_NICK': event.bot_nick or '',
        })

        # Positional args: network event [channel] [nick] [target] [text]
        args = [
            event.network or '',
            event.event or '',
        ]
        if event.channel:
            args.append(event.channel)
        if event.nick:
            args.append(event.nick)
        if event.target:
            args.append(event.target)
        if event.text:
            args.append(event.text)

        try:
            result = subprocess.run(
                [path] + args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                text=True,
            )
            if result.returncode != 0:
                print(f"[Hook] {path} exited {result.returncode}: {result.stderr.strip()}")
            # Hook stdout: non-command lines are just logged, command lines are sent to IRC
            if result.stdout:
                self._handle_hook_output(path, result.stdout)
        except Exception as e:
            print(f"[Hook] {path} failed: {e}")

    def _handle_hook_output(self, path: str, stdout: str) -> None:
        """Inspect hook stdout: send IRC commands, log informational lines."""
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            cmd = self._is_send_command(line)
            if cmd and self.send_callback:
                # RAW: prefix means send the rest verbatim (e.g. RAW WHOIS nick)
                if cmd == 'RAW':
                    line = line.split(None, 1)[1] if ' ' in line else ''
                    if not line:
                        continue
                try:
                    self.send_callback(line)
                    print(f"[Hook] {path} -> {line}")
                except Exception as e:
                    print(f"[Hook] {path} send failed for '{line}': {e}")
            elif cmd and not self.send_callback:
                print(f"[Hook] {path}: cannot send '{line}' (no send callback configured)")
            else:
                print(f"[Hook] {path}: {line}")
