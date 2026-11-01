#!/usr/bin/env python3
"""
Test the exact scenario reported by the user:
- HexChat session nick is m5it
- Upstream IRC client is connected as t3ch_
- On attach, BNC must sync HexChat to t3ch_ before sending JOIN/NAMES,
  otherwise channels do not appear joined in HexChat.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


class FakeConnection:
    def __init__(self):
        self._connected = True
        self.sent = []

    def is_connected(self):
        return self._connected

    def send(self, message):
        self.sent.append(message)

    def disconnect(self):
        self._connected = False


def make_session(client, nick):
    sock = FakeSocket()
    session = UserSession(
        conn=sock,
        addr=("127.0.0.1", 12345),
        irc_clients={"libera": client},
        require_auth=False,
        user_db=None,
        buffer_manager=None,
        command_handler=None,
    )
    session.nick = nick
    session.username = nick
    session.authenticated = True
    session.current_network = "libera"
    session.selected_client = client
    return session, sock


def test_nick_sync_and_join_replay():
    """HexChat m5it + upstream t3ch_ -> channels appear joined after attach."""
    config = Config()
    net = IrcNetworkConfig(name="libera", host="irc.libera.chat", port=6697, nick="t3ch")
    config.add_network(net)
    client = IrcClient(net, None)

    # Upstream registered as t3ch_ (nick collision)
    client.connection = FakeConnection()
    client.state.current_nick = "t3ch_"
    client.state.nick = "t3ch_"
    client.state.registered = True

    # Pretend upstream is already in #kosdb and #linux
    client.state.channels = {"#kosdb": {"name": "#kosdb", "joined": True},
                             "#linux": {"name": "#linux", "joined": True}}
    client.state.channel_users["#kosdb"] = {"t3ch_": "", "t3ch": "", "someone": "@"}
    client.state.channel_names["#kosdb"] = [
        ":calcium.libera.chat 353 t3ch_ = #kosdb :t3ch_ t3ch someone"
    ]

    # Saved channels include #kosdb (already joined) and #rhel (not joined)
    session, sock = make_session(client, "m5it")
    # Do not pre-set current_network/selected_client, otherwise attach will
    # detach first and then see the client as disconnected.
    session.current_network = None
    session.selected_client = None

    # Simulate attach
    session._attach_to_network("libera")

    output = "\n".join(sock.sent)
    print(output)

    # 1. Nick sync must be sent first
    assert ":m5it!user@host NICK :t3ch_" in output, \
        "BNC did not sync HexChat nick to upstream nick"

    # 2. JOINs must come from the now-synced nick t3ch_, not m5it
    assert ":t3ch_!user@host JOIN #kosdb" in output
    assert ":t3ch_!user@host JOIN #linux" in output

    # 3. NAMES replies must use t3ch_
    assert "353 t3ch_ = #kosdb" in output

    # 4. #rhel is saved but not joined upstream -> only request upstream JOIN,
    #    no fake JOIN to HexChat.
    assert "JOIN #rhel" not in output, \
        "Fake JOIN sent for channel not yet joined upstream"

    # 5. Session nick was updated
    assert session.nick == "t3ch_"

    print("✓ Nick sync + join replay works for m5it/t3ch_ scenario")


if __name__ == "__main__":
    test_nick_sync_and_join_replay()
    print("\nAttach nick-sync test passed!")
