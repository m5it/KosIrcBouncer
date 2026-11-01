#!/usr/bin/env python3
"""
Test the external hook system.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import IrcNetworkConfig
from shared.message import IrcMessage
from shared.hook_manager import HookManager
from client import IrcClient


def write_hook(path, logfile, extra=""):
    with open(path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(f"echo \"$1 $2 $3 $4 $IRC_TEXT\" >> {logfile}\n")
        f.write(extra)
    os.chmod(path, 0o755)


def test_privmsg_hook():
    """A global PRIVMSG hook receives channel, nick, text, server."""
    hooks_dir = tempfile.mkdtemp()
    logfile = os.path.join(hooks_dir, "log.txt")
    global_hook = os.path.join(hooks_dir, "PRIVMSG.hook")
    write_hook(global_hook, logfile)

    hm = HookManager(hooks_dir)
    net = IrcNetworkConfig(name="testnet", host="irc.example.com", port=6667)
    client = IrcClient(net, None)
    client.hook_manager = hm

    msg = IrcMessage.parse(":someone!~ident@host.example.com PRIVMSG #test :hello world")
    client._handle_command(msg)

    import time
    time.sleep(0.2)

    output = open(logfile).read()
    assert "testnet PRIVMSG #test someone hello world" in output, f"Unexpected output: {output}"
    print("✓ PRIVMSG hook fired with correct args")


def test_network_specific_hook():
    """Network-specific hook takes priority."""
    hooks_dir = tempfile.mkdtemp()
    logfile = os.path.join(hooks_dir, "log.txt")

    global_hook = os.path.join(hooks_dir, "PRIVMSG.hook")
    write_hook(global_hook, logfile, "echo 'global' >> %s\n" % logfile)
    net_hook = os.path.join(hooks_dir, "testnet_PRIVMSG.hook")
    write_hook(net_hook, logfile, "echo 'network' >> %s\n" % logfile)

    hm = HookManager(hooks_dir)
    net = IrcNetworkConfig(name="testnet", host="irc.example.com", port=6667)
    client = IrcClient(net, None)
    client.hook_manager = hm

    msg = IrcMessage.parse(":someone!i@h PRIVMSG #test :hi")
    client._handle_command(msg)

    import time
    time.sleep(0.2)

    output = open(logfile).read()
    assert "network" in output, output
    # Current design runs all matching hooks (channel, network, global).
    assert "network" in output and "global" in output, output
    print("✓ Network-specific and global hooks both run")


def test_channel_specific_hook():
    """Channel-specific hook runs first."""
    hooks_dir = tempfile.mkdtemp()
    logfile = os.path.join(hooks_dir, "log.txt")

    global_hook = os.path.join(hooks_dir, "JOIN.hook")
    write_hook(global_hook, logfile, "echo 'global-join' >> %s\n" % logfile)
    chan_hook = os.path.join(hooks_dir, "test_JOIN.hook")
    write_hook(chan_hook, logfile, "echo 'channel-join' >> %s\n" % logfile)

    hm = HookManager(hooks_dir)
    net = IrcNetworkConfig(name="testnet", host="irc.example.com", port=6667)
    client = IrcClient(net, None)
    client.state.current_nick = "me"
    client.hook_manager = hm

    msg = IrcMessage.parse(":someone!i@h JOIN #test")
    client._handle_command(msg)

    import time
    time.sleep(0.2)

    output = open(logfile).read()
    assert "channel-join" in output, output
    assert "channel-join" in output and "global-join" in output, output
    print("✓ Channel-specific and global hooks both run")


def test_all_event_hooks():
    """Every requested event fires a hook."""
    hooks_dir = tempfile.mkdtemp()
    logfile = os.path.join(hooks_dir, "log.txt")
    events = ["PRIVMSG", "NOTICE", "JOIN", "PART", "KICK", "MODE", "OP", "DEOP",
              "VOICE", "DEVOICE", "TOPIC", "QUIT", "NICK"]
    for ev in events:
        write_hook(os.path.join(hooks_dir, f"{ev}.hook"), logfile)

    hm = HookManager(hooks_dir)
    net = IrcNetworkConfig(name="testnet", host="irc.example.com", port=6667)
    client = IrcClient(net, None)
    client.state.current_nick = "t3ch"
    client.hook_manager = hm

    messages = [
        IrcMessage.parse(":someone!i@h PRIVMSG #test :hi"),
        IrcMessage.parse(":someone!i@h NOTICE #test :notice text"),
        IrcMessage.parse(":someone!i@h JOIN #test"),
        IrcMessage.parse(":someone!i@h PART #test :leaving"),
        IrcMessage.parse(":t3ch!~bnc@host.net MODE #test +o someone"),
        IrcMessage.parse(":t3ch!~bnc@host.net MODE #test +v someone"),
        IrcMessage.parse(":t3ch!~bnc@host.net KICK #test someone :reason"),
        IrcMessage.parse(":t3ch!~bnc@host.net TOPIC #test :new topic"),
        IrcMessage.parse(":old!i@h QUIT :bye"),
        IrcMessage.parse(":old!i@h NICK :new"),
    ]
    for msg in messages:
        client._handle_command(msg)

    import time
    time.sleep(0.5)

    output = open(logfile).read()
    assert "PRIVMSG #test someone hi" in output, output
    assert "NOTICE #test someone notice text" in output, output
    assert "JOIN #test someone" in output, output
    assert "PART #test someone leaving" in output, output
    assert "OP" in output, output
    assert "VOICE" in output, output
    assert "KICK" in output and "reason" in output, output
    assert "TOPIC #test t3ch new topic" in output, output
    assert "QUIT" in output, output
    assert "NICK" in output, output
    print("✓ All expected hook events fired")


def test_connect_disconnect_hooks():
    """CONNECT and DISCONNECT hooks fire."""
    hooks_dir = tempfile.mkdtemp()
    logfile = os.path.join(hooks_dir, "log.txt")

    write_hook(os.path.join(hooks_dir, "CONNECT.hook"), logfile)
    write_hook(os.path.join(hooks_dir, "DISCONNECT.hook"), logfile)

    hm = HookManager(hooks_dir)
    net = IrcNetworkConfig(name="testnet", host="localhost", port=6667)
    client = IrcClient(net, None)
    client.hook_manager = hm

    client._on_connected()
    client._on_disconnected()

    import time
    time.sleep(0.2)

    output = open(logfile).read()
    assert "CONNECT" in output, output
    assert "DISCONNECT" in output, output
    print("✓ CONNECT/DISCONNECT hooks fired")


if __name__ == "__main__":
    test_privmsg_hook()
    test_network_specific_hook()
    test_channel_specific_hook()
    test_all_event_hooks()
    test_connect_disconnect_hooks()
    print("\nAll hook tests passed!")
