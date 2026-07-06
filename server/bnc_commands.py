\"\"\"\nBNC Control Commands Handler\n\"\"\"\n\nimport re\nimport time\nfrom typing import List, Optional, Dict\nfrom datetime import datetime\n\nfrom ..shared import UserDatabase, PasswordHasher

class BncCommandHandler:
    """
    Handles all /BNC commands for administration and control.
    """
    
    def __init__(self, irc_clients: Dict[str, object], 
                 user_db: UserDatabase,
                 buffer_manager: object,
                 bnc_server: object):
        self.irc_clients = irc_clients
        self.user_db = user_db
        self.buffer = buffer_manager
        self.bnc_server = bnc_server
        
        # Command handlers
        self.commands = {
            # Connection commands
            'CONNECT': self.cmd_connect,
            'DISCONNECT': self.cmd_disconnect,
            'RECONNECT': self.cmd_reconnect,
            'JUMP': self.cmd_jump,
            'NETWORKS': self.cmd_networks,
            'STATUS': self.cmd_status,
            
            # Message commands
            'SAY': self.cmd_say,
            'RAW': self.cmd_raw,
            'QUOTE': self.cmd_raw,  # Alias
            
            # User management (admin only)
            'ADDUSER': self.cmd_adduser,
            'DELUSER': self.cmd_deluser,
            'LISTUSERS': self.cmd_listusers,
            'SETPASS': self.cmd_setpass,
            
            # Buffer commands
            'BUFFER': self.cmd_buffer,
            'CLEARBUFFER': self.cmd_clearbuffer,
            
            # Session commands
            'DETACH': self.cmd_detach,
            'ATTACH': self.cmd_attach,
            
            # Help
            'HELP': self.cmd_help,
        }
    
    def handle(self, session: object, command_line: str) -> List[str]:
        """
        Handle a BNC command.
        Returns list of response lines to send to user.
        """
        parts = command_line.split()
        if len(parts) < 2:
            return [":server NOTICE * :Usage: /BNC <command> [args]"]
        
        cmd = parts[1].upper()
        args = parts[2:]
        
        handler = self.commands.get(cmd)
        if not handler:
            return [f":server NOTICE {session.nick} :Unknown BNC command: {cmd}"]
        
        try:
            return handler(session, args)
        except Exception as e:
            return [f":server NOTICE {session.nick} :Error: {str(e)}"]
    
    # Connection Commands
    
    def cmd_connect(self, session: object, args: List[str]) -> List[str]:
        """Connect to a network: /BNC CONNECT <network>"""
        if not args:
            return [f":server NOTICE {session.nick} :Usage: /BNC CONNECT <network>"]
        
        network_name = args[0]
        client = self.irc_clients.get(network_name)
        
        if not client:
            return [f":server NOTICE {session.nick} :Network '{network_name}' not found"]
        
        if client.is_connected():
            return [f":server NOTICE {session.nick} :Already connected to {network_name}"]
        
        # Start connection
        client.start()
        
        return [
            f":server NOTICE {session.nick} :Connecting to {network_name}...",
            f":server NOTICE {session.nick} :Use /BNC STATUS to check connection"
        ]
    
    def cmd_disconnect(self, session: object, args: List[str]) -> List[str]:
        """Disconnect from a network: /BNC DISCONNECT [network]"""
        network = args[0] if args else session.current_network
        
        if not network:
            return [f":server NOTICE {session.nick} :Not connected to any network"]
        
        client = self.irc_clients.get(network)
        if not client:
            return [f":server NOTICE {session.nick} :Network '{network}' not found"]
        
        client.stop()
        
        if session.current_network == network:
            session.current_network = None
            session.selected_client = None
        
        return [f":server NOTICE {session.nick} :Disconnected from {network}"]
    
    def cmd_reconnect(self, session: object, args: List[str]) -> List[str]:
        """Reconnect to current network: /BNC RECONNECT"""
        return self.cmd_jump(session, args)
    
    def cmd_jump(self, session: object, args: List[str]) -> List[str]:
        """Jump (reconnect) to server: /BNC JUMP [network]"""
        network = args[0] if args else session.current_network
        
        if not network:
            return [f":server NOTICE {session.nick} :No network specified"]
        
        client = self.irc_clients.get(network)
        if not client:
            return [f":server NOTICE {session.nick} :Network '{network}' not found"]
        
        # Disconnect and reconnect
        client.stop()
        time.sleep(1)
        client.start()
        
        return [
            f":server NOTICE {session.nick} :Jumping on {network}...",
            f":server NOTICE {session.nick} :Reconnecting to {client.config.host}:{client.config.port}"
        ]
    
    def cmd_networks(self, session: object, args: List[str]) -> List[str]:
        """List available networks: /BNC NETWORKS"""
        responses = [f":server NOTICE {session.nick} :=== Available Networks ==="]
        
        for name, client in self.irc_clients.items():
            status = "connected" if client.is_connected() else "disconnected"
            current = " [current]" if name == session.current_network else ""
            nick = client.state.current_nick if client.is_connected() else "-"
            responses.append(
                f":server NOTICE {session.nick} :  {name}: {status} (nick: {nick}){current}"
            )
        
        responses.append(f":server NOTICE {session.nick} :=======================")
        return responses
    
    def cmd_status(self, session: object, args: List[str]) -> List[str]:
        """Show BNC status: /BNC STATUS"""
        responses = [
            f":server NOTICE {session.nick} :=== BNC Status ===",
            f":server NOTICE {session.nick} :User: {session.nick}",
            f":server NOTICE {session.nick} :Authenticated: {session.authenticated}",
            f":server NOTICE {session.nick} :Current Network: {session.current_network or 'None'}",
            f":server NOTICE {session.nick} :Detached: {session.detached}",
        ]
        
        if session.selected_client and session.selected_client.is_connected():
            stats = session.selected_client.get_stats()
            responses.extend([\n                f":server NOTICE {session.nick} :IRC Nick: {stats['nick']}",\n                f":server NOTICE {session.nick} :Channels: {stats['channels']}",\n                f":server NOTICE {session.nick} :Connected: {stats['registered']}",\n                f":server NOTICE {session.nick} :Bytes sent: {stats['bytes_sent']}",\n                f":server NOTICE {session.nick} :Bytes received: {stats['bytes_received']}",\n            ])\n        \n        responses.append(f":server NOTICE {session.nick} :==================")\n        return responses\n    \n    # Message Commands\n    \n    def cmd_say(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Send message as bot: /BNC SAY <target> <message>\"\"\"\n        if len(args) < 2:\n            return [f\":server NOTICE {session.nick} :Usage: /BNC SAY <#channel|nick> <message>\"]\n        \n        if not session.selected_client or not session.selected_client.is_connected():\n            return [f\":server NOTICE {session.nick} :Not connected to IRC\"]\n        \n        target = args[0]\n        message = ' '.join(args[1:])\n        \n        session.selected_client.send_message(target, message)\n        \n        return [f\":server NOTICE {session.nick} :Sent to {target}: {message[:50]}...\"]\n    \n    def cmd_raw(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Send raw IRC command: /BNC RAW <command>\"\"\"\n        if not args:\n            return [f\":server NOTICE {session.nick} :Usage: /BNC RAW <IRC command>\"]\n        \n        if not session.selected_client or not session.selected_client.is_connected():\n            return [f\":server NOTICE {session.nick} :Not connected to IRC\"]\n        \n        raw_cmd = ' '.join(args)\n        session.selected_client._send(raw_cmd)\n        \n        return [f\":server NOTICE {session.nick} :Sent raw: {raw_cmd[:50]}...\"]\n    \n    # User Management (Admin only)\n    \n    def _require_admin(self, session: object) -> Optional[List[str]]:\n        \"\"\"Check if user is admin.\"\"\"\n        user = self.user_db.get_user(session.username)\n        if not user or not user.is_admin:\n            return [f\":server NOTICE {session.nick} :Admin privileges required\"]\n        return None\n    \n    def cmd_adduser(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Add user: /BNC ADDUSER <username> <password> [admin]\"\"\"\n        error = self._require_admin(session)\n        if error:\n            return error\n        \n        if len(args) < 2:\n            return [f\":server NOTICE {session.nick} :Usage: /BNC ADDUSER <username> <password> [admin]\"]\n        \n        username = args[0]\n        password = args[1]\n        is_admin = len(args) > 2 and args[2].lower() == 'admin'\n        \n        if self.user_db.add_user(username, password, is_admin):\n            return [f\":server NOTICE {session.nick} :User {username} added successfully\"]\n        else:\n            return [f\":server NOTICE {session.nick} :User {username} already exists\"]\n    \n    def cmd_deluser(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Delete user: /BNC DELUSER <username>\"\"\"\n        error = self._require_admin(session)\n        if error:\n            return error\n        \n        if not args:\n            return [f\":server NOTICE {session.nick} :Usage: /BNC DELUSER <username>\"]\n        \n        username = args[0]\n        \n        if username == session.username:\n            return [f\":server NOTICE {session.nick} :Cannot delete yourself\"]\n        \n        if self.user_db.delete_user(username):\n            return [f\":server NOTICE {session.nick} :User {username} deleted\"]\n        else:\n            return [f\":server NOTICE {session.nick} :User {username} not found\"]\n    \n    def cmd_listusers(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"List users: /BNC LISTUSERS\"\"\"\n        error = self._require_admin(session)\n        if error:\n            return error\n        \n        responses = [f\":server NOTICE {session.nick} :=== Users ===\"]\n        \n        for username, user in self.user_db.users.items():\n            admin = \" [admin]\" if user.is_admin else \"\"\n            locked = \" [LOCKED]\" if user.is_locked() else \"\"\n            responses.append(f\":server NOTICE {session.nick} :  {username}{admin}{locked}\")\n        \n        responses.append(f\":server NOTICE {session.nick} :=============\")\n        return responses\n    \n    def cmd_setpass(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Set password: /BNC SETPASS <username> <newpassword>\"\"\"\n        error = self._require_admin(session)\n        if error:\n            return error\n        \n        if len(args) < 2:\n            return [f\":server NOTICE {session.nick} :Usage: /BNC SETPASS <username> <newpassword>\"]\n        \n        # Implementation would update password\n        return [f\":server NOTICE {session.nick} :Password updated (stub)\"]\n    \n    # Buffer Commands\n    \n    def cmd_buffer(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Show buffer info: /BNC BUFFER\"\"\"\n        if not session.current_network:\n            return [f\":server NOTICE {session.nick} :Not connected to network\"]\n        \n        stats = self.buffer.get_buffer_stats(session.current_network)\n        \n        return [\n            f\":server NOTICE {session.nick} :Buffer stats for {session.current_network}:\",\n            f\":server NOTICE {session.nick} :  Channels: {stats['channels']}\",\n            f\":server NOTICE {session.nick} :  Queries: {stats['queries']}\",\n            f\":server NOTICE {session.nick} :  Total messages: {stats['total_messages']}\"\n        ]\n    \n    def cmd_clearbuffer(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Clear buffer: /BNC CLEARBUFFER [channel]\"\"\"\n        if not session.current_network:\n            return [f\":server NOTICE {session.nick} :Not connected to network\"]\n        \n        # Would clear specific or all buffers\n        return [f\":server NOTICE {session.nick} :Buffer cleared (stub)\"]\n    \n    # Session Commands\n    \n    def cmd_detach(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Detach session: /BNC DETACH\"\"\"\n        session._detach()\n        return [\n            f\":server NOTICE {session.nick} :Detached from IRC.\",\n            f\":server NOTICE {session.nick} :Bot continues running in background.\",\n            f\":server NOTICE {session.nick} :Use /BNC ATTACH to reconnect.\"\n        ]\n    \n    def cmd_attach(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Attach session: /BNC ATTACH\"\"\"\n        session._reattach()\n        return [f\":server NOTICE {session.nick} :Reattached to IRC.\"]\n    \n    # Help\n    \n    def cmd_help(self, session: object, args: List[str]) -> List[str]:\n        \"\"\"Show help: /BNC HELP [command]\"\"\"\n        if args:\n            cmd = args[0].upper()\n            return [f\":server NOTICE {session.nick} :Help for {cmd}: (detailed help stub)\"]\n        \n        return [\n            f\":server NOTICE {session.nick} :=== BNC Commands ===\",\n            f\":server NOTICE {session.nick} :Connection: CONNECT, DISCONNECT, RECONNECT, JUMP, NETWORKS, STATUS\",\n            f\":server NOTICE {session.nick} :Messaging: SAY, RAW\",\n            f\":server NOTICE {session.nick} :Session: DETACH, ATTACH\",\n            f\":server NOTICE {session.nick} :Buffer: BUFFER, CLEARBUFFER\",\n            f\":server NOTICE {session.nick} :Admin: ADDUSER, DELUSER, LISTUSERS, SETPASS\",\n            f\":server NOTICE {session.nick} :Use /BNC HELP <command> for details\",\n            f\":server NOTICE {session.nick} :====================\"\n        ]\n