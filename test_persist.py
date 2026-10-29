#!/usr/bin/env python3
"""
Test two persistence behaviours:
1. Disconnecting a user session must NOT stop the upstream IRC client.
2. A nick change by the user must survive an upstream reconnect.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, IrcNetworkConfig, BncServerConfig, UserConfig
from shared.auth import UserDatabase, UserAccount, PasswordHasher
from client import IrcClient
from server.user_session import UserSession


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data.decode('utf-8'))

    def sendall(self, data):
        self.sent.append(data.decode('utf-8'))

    def recv(self, size):
        return b""

    def close(self):
        self.closed = True

    def settimeout(self, *args):
        pass


def test_user_disconnect_keeps_irc_client_running():
    """When the user's IRC client quits, the upstream bot must stay connected."""
    config = Config()
    config.data_dir = tempfile.mkdtemp()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        channels=["#test"],
    )
    config.add_network(net)
    config.add_user(UserConfig(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
    ))

    user_db = UserDatabase(config.data_dir)
    user_db.users["tester"] = UserAccount(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
    )
    user_db.save()

    client = IrcClient(net, None)
    # Simulate an already running upstream client
    client._running = True
    client.state.registered = True

    sock = FakeSocket()
    session = UserSession(
        conn=sock,
        addr=("127.0.0.1", 12345),
        irc_clients={"testnet": client},
        require_auth=False,
        user_db=user_db,
        buffer_manager=None,
        command_handler=None,
    )
    session.nick = "tester"
    session.username = "tester"
    session.authenticated = True
    session.current_network = "testnet"
    session.selected_client = client

    # User disconnects
    session.disconnect()

    assert not session.running
    assert sock.closed
    assert client._running, "User disconnect must NOT stop the upstream IRC client"
    assert client.state.registered, "Upstream registration state should be preserved"
    print("✓ User disconnect keeps upstream IRC client running")


def test_nick_change_survives_reconnect():
    """After the user changes nick, reconnect should use the new nick."""
    config = Config()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        nick="OldNick",
    )
    config.add_network(net)

    client = IrcClient(net, None)

    # User changes nick
    client.change_nick("NewNick")

    assert client.state.nick == "NewNick"
    assert client.state.current_nick == "NewNick"
    assert client.config.nick == "NewNick"

    # Simulate server confirming the nick change
    from shared.message import IrcMessage
    msg = IrcMessage.parse(":OldNick!user@host NICK :NewNick")
    client._handle_nick(msg)

    assert client.config.nick == "NewNick"

    # Simulate a reconnect: _connect_and_run resets state from config
    client.state = type(client.state).__new__(type(client.state))
    client.state.__init__()
    client.state.nick = client.config.nick
    client.state.current_nick = client.config.nick

    assert client.state.nick == "NewNick"
    assert client.state.current_nick == "NewNick"
    print("✓ Nick change survives upstream reconnect")


if __name__ == "__main__":
    test_user_disconnect_keeps_irc_client_running()
    test_nick_change_survives_reconnect()
    print("\nAll persistence tests passed!")
