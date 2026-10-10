"""
BNC Control Commands Handler
"""

import re
import time
from typing import List, Optional, Dict
from datetime import datetime

from shared import UserDatabase, PasswordHasher


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

            # Authentication
            'LOGIN': self.cmd_login,

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
            'AUTOOP': self.cmd_autoop,
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
            f":server NOTICE {session.nick} :Detached: {getattr(session, 'detached', False)}",
        ]

        if session.selected_client and session.selected_client.is_connected():
            stats = session.selected_client.get_stats()
            responses.extend([
                f":server NOTICE {session.nick} :IRC Nick: {stats['nick']}",
                f":server NOTICE {session.nick} :Channels: {stats['channels']}",
                f":server NOTICE {session.nick} :Connected: {stats['registered']}",
                f":server NOTICE {session.nick} :Bytes sent: {stats['bytes_sent']}",
                f":server NOTICE {session.nick} :Bytes received: {stats['bytes_received']}",
            ])

        responses.append(f":server NOTICE {session.nick} :==================")
        return responses

    def cmd_login(self, session: object, args: List[str]) -> List[str]:
        """Authenticate with BNC: /BNC LOGIN <username> <password>"""
        if len(args) < 2:
            return [f":server NOTICE {session.nick} :Usage: /BNC LOGIN <username> <password>"]

        if not getattr(session, 'user_db', None):
            return [f":server NOTICE {session.nick} :No user database configured"]

        username, password = args[0], args[1]
        client_ip = session.addr[0]
        user = session.user_db.authenticate(username, password, client_ip)
        if not user:
            return [f":server NOTICE {session.nick} :Login failed"]

        session.authenticated = True
        session.username = username
        if not session.nick:
            session.nick = username

        # Complete the login handshake exactly like PASS-based authentication:
        # send the BNC welcome, status, and auto-attach to the only network.
        session._send_welcome()
        session._send_connection_status()
        if len(session.irc_clients) == 1:
            network = list(session.irc_clients.keys())[0]
            session._attach_to_network(network)

        return [
            f":server NOTICE {session.nick} :Login successful. Welcome {username}.",
        ]
    
    # Message Commands
    
    def cmd_say(self, session: object, args: List[str]) -> List[str]:
        """Send message as bot: /BNC SAY <target> <message>"""
        if len(args) < 2:
            return [f":server NOTICE {session.nick} :Usage: /BNC SAY <#channel|nick> <message>"]
        
        if not session.selected_client or not session.selected_client.is_connected():
            return [f":server NOTICE {session.nick} :Not connected to IRC"]
        
        target = args[0]
        message = ' '.join(args[1:])
        
        session.selected_client.send_message(target, message)
        
        return [f":server NOTICE {session.nick} :Sent to {target}: {message[:50]}..."]
    
    def cmd_raw(self, session: object, args: List[str]) -> List[str]:
        """Send raw IRC command: /BNC RAW <command>"""
        if not args:
            return [f":server NOTICE {session.nick} :Usage: /BNC RAW <IRC command>"]
        
        if not session.selected_client or not session.selected_client.is_connected():
            return [f":server NOTICE {session.nick} :Not connected to IRC"]
        
        raw_cmd = ' '.join(args)
        session.selected_client._send(raw_cmd)
        
        return [f":server NOTICE {session.nick} :Sent raw: {raw_cmd[:50]}..."]
    
    # User Management (Admin only)
    
    def _require_admin(self, session: object) -> Optional[List[str]]:
        """Check if user is admin."""
        user = self.user_db.get_user(session.username)
        if not user or not user.is_admin:
            return [f":server NOTICE {session.nick} :Admin privileges required"]
        return None
    
    def cmd_adduser(self, session: object, args: List[str]) -> List[str]:
        """Add user: /BNC ADDUSER <username> <password> [admin]"""
        error = self._require_admin(session)
        if error:
            return error
        
        if len(args) < 2:
            return [f":server NOTICE {session.nick} :Usage: /BNC ADDUSER <username> <password> [admin]"]
        
        username = args[0]
        password = args[1]
        is_admin = len(args) > 2 and args[2].lower() == 'admin'
        
        if self.user_db.add_user(username, password, is_admin):
            return [f":server NOTICE {session.nick} :User {username} added successfully"]
        else:
            return [f":server NOTICE {session.nick} :User {username} already exists"]
    
    def cmd_deluser(self, session: object, args: List[str]) -> List[str]:
        """Delete user: /BNC DELUSER <username>"""
        error = self._require_admin(session)
        if error:
            return error
        
        if not args:
            return [f":server NOTICE {session.nick} :Usage: /BNC DELUSER <username>"]
        
        username = args[0]
        
        if username == session.username:
            return [f":server NOTICE {session.nick} :Cannot delete yourself"]
        
        if self.user_db.delete_user(username):
            return [f":server NOTICE {session.nick} :User {username} deleted"]
        else:
            return [f":server NOTICE {session.nick} :User {username} not found"]
    
    def cmd_listusers(self, session: object, args: List[str]) -> List[str]:
        """List users: /BNC LISTUSERS"""
        error = self._require_admin(session)
        if error:
            return error
        
        responses = [f":server NOTICE {session.nick} :=== Users ==="]
        
        for username, user in self.user_db.users.items():
            admin = " [admin]" if user.is_admin else ""
            locked = " [LOCKED]" if user.is_locked() else ""
            responses.append(f":server NOTICE {session.nick} :  {username}{admin}{locked}")
        
        responses.append(f":server NOTICE {session.nick} :=============")
        return responses
    
    def cmd_setpass(self, session: object, args: List[str]) -> List[str]:
        """Set password: /BNC SETPASS <username> <newpassword>"""
        error = self._require_admin(session)
        if error:
            return error
        
        if len(args) < 2:
            return [f":server NOTICE {session.nick} :Usage: /BNC SETPASS <username> <newpassword>"]
        
        # Implementation would update password
        return [f":server NOTICE {session.nick} :Password updated (stub)"]
    
    # Buffer Commands
    
    def cmd_buffer(self, session: object, args: List[str]) -> List[str]:
        """Show buffer info: /BNC BUFFER"""
        if not session.current_network:
            return [f":server NOTICE {session.nick} :Not connected to network"]
        
        stats = self.buffer.get_buffer_stats(session.current_network)
        
        return [
            f":server NOTICE {session.nick} :Buffer stats for {session.current_network}:",
            f":server NOTICE {session.nick} :  Channels: {stats['channels']}",
            f":server NOTICE {session.nick} :  Queries: {stats['queries']}",
            f":server NOTICE {session.nick} :  Total messages: {stats['total_messages']}"
        ]
    
    def cmd_clearbuffer(self, session: object, args: List[str]) -> List[str]:
        """Clear buffer: /BNC CLEARBUFFER [channel]"""
        if not session.current_network:
            return [f":server NOTICE {session.nick} :Not connected to network"]
        
        # Would clear specific or all buffers
        return [f":server NOTICE {session.nick} :Buffer cleared (stub)"]
    
    # Session Commands
    
    def cmd_detach(self, session: object, args: List[str]) -> List[str]:
        """Detach session: /BNC DETACH"""
        session._detach()
        return [
            f":server NOTICE {session.nick} :Detached from IRC.",
            f":server NOTICE {session.nick} :Bot continues running in background.",
            f":server NOTICE {session.nick} :Use /BNC ATTACH to reconnect."
        ]
    
    def cmd_attach(self, session: object, args: List[str]) -> List[str]:
        """Attach session: /BNC ATTACH"""
        session._reattach()
        return [f":server NOTICE {session.nick} :Reattached to IRC."]
    
    # Help
    
    def cmd_autoop(self, session: object, args: List[str]) -> List[str]:
        """Manage auto-op masks: /BNC AUTOOP ADD|DEL|LIST [#channel] [nick!user@host]"""
        user = self.user_db.get_user(session.username)
        if not user:
            return [f":server NOTICE {session.nick} :You are not authenticated"]

        if not args:
            return [f":server NOTICE {session.nick} :Usage: /BNC AUTOOP ADD #channel nick!user@host"]

        subcmd = args[0].upper()
        network = session.current_network or (list(self.irc_clients.keys())[0] if len(self.irc_clients) == 1 else None)
        if not network:
            return [f":server NOTICE {session.nick} :No network selected"]

        if subcmd == 'LIST':
            channel_filter = args[1].lower() if len(args) > 1 else None
            network_ops = user.auto_op.get(network, {})
            if not network_ops:
                return [f":server NOTICE {session.nick} :No auto-op masks for {network}"]
            lines = [f":server NOTICE {session.nick} :Auto-op masks for {network}:"]
            for ch, masks in sorted(network_ops.items()):
                if channel_filter and ch != channel_filter:
                    continue
                lines.append(f":server NOTICE {session.nick} :  {ch}: {' '.join(masks)}")
            return lines

        if len(args) < 3:
            return [f":server NOTICE {session.nick} :Usage: /BNC AUTOOP ADD #channel nick!user@host"]

        channel = args[1].lower()
        mask = args[2]
        if not mask.count('!') == 1 or '@' not in mask.split('!')[1]:
            return [f":server NOTICE {session.nick} :Mask must be nick!user@host"]

        network_ops = user.auto_op.setdefault(network, {})
        channel_masks = network_ops.setdefault(channel, [])

        if subcmd == 'ADD':
            if mask not in channel_masks:
                channel_masks.append(mask)
                self.user_db.save()
            # Immediately register on the upstream IRC client and try to op
            # users already present in the channel.
            client = session.selected_client
            if client:
                client.add_auto_op_masks(channel, [mask])
                session._apply_auto_op_masks(client, network, channel)
                # Request WHO for the channel so hostmasks are refreshed and
                # auto-op triggers for users already present.
                if client.is_connected():
                    client._send(f"WHO {channel}")
            return [f":server NOTICE {session.nick} :Added auto-op: {mask} on {channel}"]
        elif subcmd == 'DEL':
            if mask in channel_masks:
                channel_masks.remove(mask)
                self.user_db.save()
            client = session.selected_client
            if client:
                client.remove_auto_op_masks(channel, [mask])
            return [f":server NOTICE {session.nick} :Removed auto-op: {mask} from {channel}"]
        else:
            return [f":server NOTICE {session.nick} :Unknown AUTOOP subcommand: {subcmd}"]

    def cmd_help(self, session: object, args: List[str]) -> List[str]:
        """Show help: /BNC HELP [command]"""
        if args:
            cmd = args[0].upper()
            return [f":server NOTICE {session.nick} :Help for {cmd}: (detailed help stub)"]

        return [
            f":server NOTICE {session.nick} :=== BNC Commands ===",
            f":server NOTICE {session.nick} :Connection: CONNECT, DISCONNECT, RECONNECT, JUMP, NETWORKS, STATUS",
            f":server NOTICE {session.nick} :Messaging: SAY, RAW",
            f":server NOTICE {session.nick} :Session: DETACH, ATTACH",
            f":server NOTICE {session.nick} :Buffer: BUFFER, CLEARBUFFER",
            f":server NOTICE {session.nick} :Channel: AUTOOP",
            f":server NOTICE {session.nick} :Admin: ADDUSER, DELUSER, LISTUSERS, SETPASS",
            f":server NOTICE {session.nick} :Use /BNC HELP <command> for details",
            f":server NOTICE {session.nick} :===================="
        ]
