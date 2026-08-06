#!/usr/bin/env python3
"""Patch user_session.py to send connection status on auth."""

with open('server/user_session.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Insert call after _send_welcome() in _try_authenticate()
old_block = """        self.authenticated = True
        print(f\"[BNC] User authenticated: {self.nick}\")
        
        # Send welcome
        self._send_welcome()
        
        # If only one network, auto-connect"""

new_block = """        self.authenticated = True
        print(f\"[BNC] User authenticated: {self.nick}\")
        
        # Send welcome
        self._send_welcome()
        
        # Send BNC status information
        self._send_connection_status()
        
        # If only one network, auto-connect"""

if old_block not in content:
    print("ERROR: Could not find insertion point")
    exit(1)

content = content.replace(old_block, new_block)

# 2. Insert new method before _attach_to_network
old_method = '    def _attach_to_network(self, network_name: str) -> None:\n        """Attach to an IRC network."""'

new_method = '''    def _send_connection_status(self) -> None:
        """Send BNC status information to the IRC client."""
        if not self.nick:
            return
        
        self._send(f":BNC NOTICE {self.nick} :Welcome to IRC BNC")
        self._send(f":BNC NOTICE {self.nick} :You are authenticated as {self.nick}")
        
        # Show available networks
        if self.irc_clients:
            self._send(f":BNC NOTICE {self.nick} :Available networks:")
            for name, client in self.irc_clients.items():
                if client.is_connected():
                    status = f"connected (nick: {client.state.current_nick})"
                else:
                    status = "disconnected"
                self._send(f":BNC NOTICE {self.nick} :  - {name}: {status}")
        else:
            self._send(f":BNC NOTICE {self.nick} :No networks configured")
        
        # Auto-attach hint or connect hint
        if len(self.irc_clients) == 1:
            network = list(self.irc_clients.keys())[0]
            self._send(f":BNC NOTICE {self.nick} :Auto-attaching to {network}...")
        elif len(self.irc_clients) > 1:
            self._send(f":BNC NOTICE {self.nick} :Use /BNC CONNECT <network> to attach to a network")
        
        self._send(f":BNC NOTICE {self.nick} :Use /BNC STATUS for status and /BNC HELP for commands")
    
    def _attach_to_network(self, network_name: str) -> None:
        """Attach to an IRC network."""'''

if old_method not in content:
    print("ERROR: Could not find _attach_to_network method")
    exit(1)

content = content.replace(old_method, new_method)

with open('server/user_session.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patched successfully")
