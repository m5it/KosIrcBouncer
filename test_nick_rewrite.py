#!/usr/bin/env python3
"""
Test that replayed IRC lines are rewritten to the current nick after a nick
change.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, IrcNetworkConfig
from shared.message import IrcMessage
from client import IrcClient
from server.user_session import UserSession


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data.decode('utf-8').strip())

    def sendall(self, data):
        self.sent.append(data.decode('utf-8').strip())

    def recv(self, size):
        return b""

    def close(self):
        self.closed = True

    def settimeout(self, *args):
        pass


def make_session(client, nick):
    sock = FakeSocket()
    session = UserSession(
        conn=sock,
        addr=("127.0.0.1", 12345),
        irc_clients={"testnet": client},
        require_auth=False,
        user_db=None,
        buffer_manager=None,
        command_handler=None,
    )
    session.nick = nick
    session.username = nick
    session.authenticated = True
    session.current_network = "testnet"
    session.selected_client = client
    return session, sock


def test_who_reply_rewritten():
    """Cached WHO replies must show the current nick after a nick change."""
    config = Config()
    net = IrcNetworkConfig(name="testnet", host="localhost", port=6667, nick="realt3ch")
    config.add_network(net)
    client = IrcClient(net, None)

    # Simulate server assigning the nick, then user changing it.
    msg = IrcMessage.parse(":server 001 realt3ch :Welcome")
    client.state.current_nick = "realt3ch"
    client.state.nick = "realt3ch"
    client._handle_nick(IrcMessage.parse(":realt3ch!u@h NICK :t3ch"))

    assert client.state.current_nick == "t3ch"
    assert client.state.previous_nick == "realt3ch"

    # Cache a WHO reply captured when nick was realt3ch.
    cached_who = ":mercury.libera.chat 352 realt3ch #civilcultural ~bnc host.net mercury.libera.chat realt3ch H :0 realname"
    client.state.channel_who["#civilcultural"] = [cached_who]

    session, sock = make_session(client, "t3ch")
    session._handle_who(["#civilcultural"], "WHO #civilcultural")

    output = "\n".join(sock.sent)
    assert "352 t3ch #civilcultural" in output, f"client nick not rewritten: {output}"
    assert "mercury.libera.chat t3ch H" in output, f"queried nick not rewritten: {output}"
    assert "realt3ch" not in output, f"old nick still present: {output}"
    print("✓ WHO reply rewritten to current nick")


def test_names_reply_rewritten():
    """Cached NAMES replies must show the current nick after a nick change."""
    config = Config()
    net = IrcNetworkConfig(name="testnet", host="localhost", port=6667, nick="realt3ch")
    config.add_network(net)
    client = IrcClient(net, None)

    client.state.current_nick = "realt3ch"
    client._handle_nick(IrcMessage.parse(":realt3ch!u@h NICK :t3ch"))

    cached_names = [
        ":mercury.libera.chat 353 realt3ch = #civilcultural :@t3ch +someone",
        ":mercury.libera.chat 366 realt3ch #civilcultural :End of /NAMES list.",
    ]
    client.state.channel_names["#civilcultural"] = cached_names

    session, sock = make_session(client, "t3ch")
    session._handle_names(["#civilcultural"], "NAMES #civilcultural")

    output = "\n".join(sock.sent)
    assert "353 t3ch = #civilcultural" in output, f"names client nick not rewritten: {output}"
    assert "366 t3ch #civilcultural" in output, f"endofnames client nick not rewritten: {output}"
    assert "realt3ch" not in output, f"old nick still present: {output}"
    print("✓ NAMES reply rewritten to current nick")


def test_buffer_privmsg_rewritten():
    """Buffered messages from the BNC's old nick must be rewritten."""
    config = Config()
    net = IrcNetworkConfig(name="testnet", host="localhost", port=6667, nick="realt3ch")
    config.add_network(net)
    client = IrcClient(net, None)

    client.state.current_nick = "realt3ch"
    client._handle_nick(IrcMessage.parse(":realt3ch!u@h NICK :t3ch"))

    from shared.buffer import BufferManager
    bm = BufferManager()
    # The global network buffer stores raw IRC lines.
    bm.add_message("testnet", "*", ":realt3ch!~bnc@host.net PRIVMSG #civilcultural :hello world", "PRIVMSG")

    session, sock = make_session(client, "t3ch")
    session.buffer_manager = bm
    session._send_buffer_playback("testnet")

    output = "\n".join(sock.sent)
    assert ":t3ch!~bnc@host.net PRIVMSG #civilcultural :hello world" in output, f"buffered nick not rewritten: {output}"
    assert "realt3ch" not in output, f"old nick still present: {output}"
    print("✓ Buffered PRIVMSG rewritten to current nick")


if __name__ == "__main__":
    test_who_reply_rewritten()
    test_names_reply_rewritten()
    test_buffer_privmsg_rewritten()
    print("\nAll nick-rewrite tests passed!")
