#!/usr/bin/env python3
"""
Quick test for /BNC DEBUG and PART auto-join sync fix.
"""
import sys
import os
import socket
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, IrcNetworkConfig, BncServerConfig, UserConfig
from shared.auth import UserDatabase, UserAccount, PasswordHasher
from client import IrcClient
from server.bnc_commands import BncCommandHandler
from server.user_session import UserSession


class MockSocket:
    """Fake socket that captures sent lines."""
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(data.decode('utf-8'))

    def recv(self, size):
        return b""

    def close(self):
        pass

    def settimeout(self, *args):
        pass


def test_config_sync_on_startup():
    """Main.py should sync config.channels from saved_channels."""
    config = Config()
    config.data_dir = tempfile.mkdtemp()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        channels=["#programming", "#random"],
    )
    config.add_network(net)
    config.add_user(UserConfig(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
        allowed_networks=["testnet"],
    ))

    # Simulate user parting #programming in previous session
    user_db = UserDatabase(config.data_dir)
    user_db.users["tester"] = UserAccount(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
    )
    user_db.users["tester"].saved_channels["testnet"] = {"#random"}
    user_db.save()

    # Simulate main.py startup sync
    for name, net_config in config.networks.items():
        saved_union = set()
        for account in user_db.users.values():
            saved_union.update(account.saved_channels.get(name, set()))
        if saved_union:
            net_config.channels = sorted(saved_union)

    assert config.networks["testnet"].channels == ["#random"], \
        f"Expected ['#random'], got {config.networks['testnet'].channels}"
    print("✓ config.channels synced from saved_channels on startup")


def test_part_updates_config_channels():
    """PART from user should remove channel from in-memory config.channels."""
    config = Config()
    config.data_dir = tempfile.mkdtemp()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        channels=["#programming", "#random"],
    )
    config.add_network(net)
    config.add_user(UserConfig(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
        allowed_networks=["testnet"],
    ))

    user_db = UserDatabase(config.data_dir)
    user_db.users["tester"] = UserAccount(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
    )
    user_db.users["tester"].saved_channels["testnet"] = {"#programming", "#random"}
    user_db.save()

    buffer_manager = None
    client = IrcClient(net, buffer_manager)

    # Create session without starting the thread
    sock = MockSocket()
    session = UserSession(
        conn=sock,
        addr=("127.0.0.1", 12345),
        irc_clients={"testnet": client},
        require_auth=False,
        user_db=user_db,
        buffer_manager=buffer_manager,
        command_handler=None,
    )
    session.nick = "tester"
    session.username = "tester"
    session.authenticated = True
    session.current_network = "testnet"
    session.selected_client = client

    # PART #programming
    session._handle_part(["#programming"], "PART #programming :bye")

    assert "#programming" not in [c.lower() for c in client.config.channels], \
        f"#programming still in config.channels: {client.config.channels}"
    assert "#random" in client.config.channels, \
        f"#random missing from config.channels: {client.config.channels}"
    assert "#programming" not in user_db.users["tester"].saved_channels.get("testnet", set()), \
        f"#programming still in saved_channels"
    print("✓ PART removes channel from saved_channels and config.channels")


def test_join_updates_config_channels():
    """JOIN from user should add channel to in-memory config.channels."""
    config = Config()
    config.data_dir = tempfile.mkdtemp()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        channels=["#random"],
    )
    config.add_network(net)
    config.add_user(UserConfig(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
        allowed_networks=["testnet"],
    ))

    user_db = UserDatabase(config.data_dir)
    user_db.users["tester"] = UserAccount(
        username="tester",
        password_hash=PasswordHasher.hash("pass"),
    )
    user_db.save()

    buffer_manager = None
    client = IrcClient(net, buffer_manager)

    sock = MockSocket()
    session = UserSession(
        conn=sock,
        addr=("127.0.0.1", 12345),
        irc_clients={"testnet": client},
        require_auth=False,
        user_db=user_db,
        buffer_manager=buffer_manager,
        command_handler=None,
    )
    session.nick = "tester"
    session.username = "tester"
    session.authenticated = True
    session.current_network = "testnet"
    session.selected_client = client

    # JOIN #newchan
    session._handle_join(["#newchan"], "JOIN #newchan")

    assert "#newchan" in [c.lower() for c in client.config.channels], \
        f"#newchan missing from config.channels: {client.config.channels}"
    print("✓ JOIN adds channel to saved_channels and config.channels")


def test_bnc_debug_command():
    """/BNC DEBUG should return useful debug info."""
    config = Config()
    config.data_dir = tempfile.mkdtemp()
    net = IrcNetworkConfig(
        name="testnet",
        host="localhost",
        port=6667,
        channels=["#programming"],
    )
    config.add_network(net)

    user_db = UserDatabase(config.data_dir)
    buffer_manager = None
    bnc_server = None
    handler = BncCommandHandler({"testnet": None}, user_db, buffer_manager, bnc_server)

    class FakeClient:
        class FakeState:
            current_nick = "MyNick"
            hostmask = "MyNick!user@host"
            channels = {"#programming": {"name": "#programming"}}
            channel_users = {"#programming": {"someone": "@"}}
        class FakeConfig:
            channels = ["#programming"]
        state = FakeState()
        config = FakeConfig()
        def is_connected(self):
            return True

    class FakeSession:
        nick = "tester"
        authenticated = True
        current_network = "testnet"
        selected_client = FakeClient()
        def _get_user_account(self):
            acc = UserAccount(username="tester", password_hash="x")
            acc.saved_channels["testnet"] = {"#programming"}
            return acc

    responses = handler.handle(FakeSession(), "BNC DEBUG")
    text = "\n".join(responses)
    assert "BNC Debug" in text
    assert "MyNick" in text
    assert "#programming" in text
    assert "users: 1" in text
    assert "Saved channels" in text
    print("✓ /BNC DEBUG command works")


if __name__ == "__main__":
    test_config_sync_on_startup()
    test_part_updates_config_channels()
    test_join_updates_config_channels()
    test_bnc_debug_command()
    print("\nAll tests passed!")
