#!/usr/bin/env python3
"""Verify hooks can send to channel / user / server by echoing commands."""
import sys, os, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import IrcNetworkConfig
from shared.message import IrcMessage
from shared.hook_manager import HookManager
from client import IrcClient
from client.connection import IrcConnection

def write_hook(path, body):
    with open(path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(body + "\n")
    os.chmod(path, 0o755)

class FakeConn:
    def __init__(self): self.sent = []
    def is_connected(self): return True
    def send(self, line): self.sent.append(line)

hooks_dir = tempfile.mkdtemp()
# PRIVMSG hook that replies to the channel and DMs the sender
write_hook(os.path.join(hooks_dir, "PRIVMSG.hook"),
    'echo "PRIVMSG $IRC_CHANNEL :Hello $IRC_NICK from hook!"\n'
    'echo "NOTICE $IRC_NICK :Got your message on $IRC_CHANNEL"\n'
    'echo "this is just a log line"\n'
)
# JOIN hook that sends a raw MODE
write_hook(os.path.join(hooks_dir, "JOIN.hook"),
    'echo "MODE $IRC_CHANNEL +v $IRC_NICK"\n'
)

hm = HookManager(hooks_dir)
net = IrcNetworkConfig(name="testnet", host="irc.example.com", port=6667)
client = IrcClient(net, None)
fake = FakeConn()
client.connection = fake
client.hook_manager = hm
client.state.current_nick = "mybot"

# Trigger PRIVMSG
msg = IrcMessage.parse(":someone!i@h PRIVMSG #test :hello bot")
client._handle_command(msg)
time.sleep(0.4)

assert any("PRIVMSG #test :Hello someone from hook!" in s for s in fake.sent), fake.sent
assert any("NOTICE someone :Got your message on #test" in s for s in fake.sent), fake.sent
print("✓ PRIVMSG hook can send to channel and user")

# Trigger JOIN
fake.sent.clear()
msg = IrcMessage.parse(":someone!i@h JOIN #test")
client._handle_command(msg)
time.sleep(0.4)

assert any("MODE #test +v someone" in s for s in fake.sent), fake.sent
print("✓ JOIN hook can send MODE to server")

# Non-command stdout should not be sent
assert not any("just a log line" in s for s in fake.sent)
print("✓ Non-command hook output only logged, not sent")

print("\nAll hook-send tests passed!")
