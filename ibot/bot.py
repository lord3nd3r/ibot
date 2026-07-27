"""Core IRC client for ibot.

Provides an asyncio-based IRC connection with SSL/TLS support,
SASL authentication, auto-reconnect, flood protection,
channel/user tracking, and integration with the plugin dispatcher.
"""

import asyncio
import base64
import logging
import os
import re
import signal
import ssl
import threading
import time
from typing import Optional

from ibot.sopel_shim.tools import Identifier, SopelMemory, SopelIdentifierMemory
from ibot.sopel_shim.db import SopelDB
from ibot.sopel_shim.privileges import VOICE, HALFOP, OP, ADMIN, OWNER

LOGGER = logging.getLogger(__name__)

# Constants
MAX_MESSAGE_LENGTH = 400  # Conservative limit for IRC message length
MAX_RECONNECT_DELAY = 300  # Maximum reconnect delay in seconds
INTERVAL_JOB_MAX_FAILURES = 5  # Max consecutive failures before disabling
INTERVAL_JOB_BACKOFF_BASE = 5  # Base backoff time in seconds

# Map IRC mode chars to privilege levels
MODE_TO_PRIVILEGE = {
    '+': VOICE,
    '%': HALFOP,
    '@': OP,
    '&': ADMIN,
    '~': OWNER,
}
MODE_LETTER_TO_PRIVILEGE = {
    'v': VOICE,
    'h': HALFOP,
    'o': OP,
    'a': ADMIN,
    'q': OWNER,
}


class User:
    """Represents a tracked IRC user."""

    def __init__(self, nick, user=None, host=None):
        self.nick = Identifier(nick)
        self.user = user or ''
        self.host = host or ''
        self.account = None
        self.realname = ''
        self.away = None
        self.channels = set()

    @property
    def hostmask(self):
        return f'{self.nick}!{self.user}@{self.host}'


class Channel:
    """Represents a tracked IRC channel."""

    def __init__(self, name):
        self.name = Identifier(name)
        self.privileges = SopelIdentifierMemory()
        self.topic = ''
        self.users = SopelIdentifierMemory()

    def has_privilege(self, nick, privilege):
        priv = self.privileges.get(nick, 0)
        return priv >= privilege

    # Sopel-compatible per-level checks (bitmask, like sopel.tools.target).
    def is_voiced(self, nick):
        return bool(self.privileges.get(nick, 0) & VOICE)

    def is_halfop(self, nick):
        return bool(self.privileges.get(nick, 0) & HALFOP)

    def is_op(self, nick):
        return bool(self.privileges.get(nick, 0) & OP)

    def is_admin(self, nick):
        return bool(self.privileges.get(nick, 0) & ADMIN)

    def is_owner(self, nick):
        return bool(self.privileges.get(nick, 0) & OWNER)

    def add_user(self, nick, privilege=0, user_obj=None):
        nick_id = Identifier(nick)
        if user_obj:
            self.users[nick_id] = user_obj
        elif nick_id not in self.users:
            self.users[nick_id] = User(nick)
        if privilege:
            current = self.privileges.get(nick_id, 0)
            self.privileges[nick_id] = current | privilege

    def remove_user(self, nick):
        nick_id = Identifier(nick)
        self.users.pop(nick_id, None)
        self.privileges.pop(nick_id, None)


class IRCBot:
    """Core asyncio-based IRC client.

    Handles the raw TCP/SSL connection, IRC protocol, SASL auth,
    channel/user tracking, and message sending with flood protection.
    """

    def __init__(self, settings):
        self.settings = settings
        self.nick = settings.core.nick
        self._desired_nick = settings.core.nick

        # State
        self.channels = SopelIdentifierMemory()
        self.users = SopelIdentifierMemory()
        self.memory = SopelMemory()
        self.db = SopelDB(settings)
        self._state_lock = threading.RLock()  # Protects channels/users

        # Connection
        self._reader = None
        self._writer = None
        self._connected = False
        self._registered = False
        self._running = False
        self._reconnect_delay = 5

        # Flood protection
        self._send_queue = asyncio.Queue()
        self._flood_burst = settings.core.flood_burst or 4
        self._flood_tokens = self._flood_burst
        self._flood_refill = settings.core.flood_refill or 1
        self._last_refill = time.time()

        # SASL
        self._sasl_in_progress = False
        self._cap_negotiating = False

        # Dispatcher (set after construction)
        self.dispatcher = None

        # Interval scheduler
        self._interval_tasks = []
        self._loop = None

    # --- Connection ---

    async def connect(self):
        """Establish connection to the IRC server."""
        host = self.settings.core.host
        port = self.settings.core.port
        use_ssl = self.settings.core.use_ssl

        LOGGER.info("Connecting to %s:%d (SSL=%s)...", host, port, use_ssl)

        ssl_ctx = None
        if use_ssl:
            ssl_ctx = ssl.create_default_context()
            if not self.settings.core.verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

        self._reader, self._writer = await asyncio.open_connection(
            host, port, ssl=ssl_ctx,
        )
        self._connected = True
        LOGGER.info("Connected to %s:%d", host, port)

    async def _send_raw(self, line):
        """Send a raw IRC line (internal async version)."""
        if not self._writer:
            return
        if not line.endswith('\r\n'):
            line += '\r\n'
        LOGGER.debug(">>> %s", self._sanitize_for_log(line.strip()))
        self._writer.write(line.encode('utf-8', errors='replace'))
        await self._writer.drain()

    def _sanitize_for_log(self, line):
        """Sanitize sensitive data from log output."""
        # Hide SASL authentication
        if line.startswith('AUTHENTICATE ') and line != 'AUTHENTICATE PLAIN':
            return 'AUTHENTICATE [redacted]'
        # Hide NickServ password
        if 'PRIVMSG NickServ :IDENTIFY' in line or 'PRIVMSG nickserv :IDENTIFY' in line.lower():
            parts = line.split('IDENTIFY', 1)
            return parts[0] + 'IDENTIFY [redacted]'
        return line

    def send_raw(self, line):
        """Send a raw IRC line (thread-safe, called by plugins)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._send_queue.put(line), self._loop)

    def send_privmsg(self, target, text):
        """Send a PRIVMSG (thread-safe)."""
        # Split long messages (512 bytes max per IRC line minus overhead)
        for chunk in self._split_message(text):
            self.send_raw(f'PRIVMSG {target} :{chunk}')

    @staticmethod
    def _split_message(text, max_bytes=MAX_MESSAGE_LENGTH):
        """Split text into chunks that fit within max_bytes when UTF-8 encoded.

        Splits on character boundaries so multibyte characters are never cut in
        half, and measures length in bytes (IRC's real limit) rather than in
        characters.
        """
        text = str(text)
        if len(text.encode('utf-8')) <= max_bytes:
            yield text
            return

        chunk = []
        chunk_bytes = 0
        for ch in text:
            ch_bytes = len(ch.encode('utf-8'))
            if chunk_bytes + ch_bytes > max_bytes and chunk:
                yield ''.join(chunk)
                chunk = []
                chunk_bytes = 0
            chunk.append(ch)
            chunk_bytes += ch_bytes
        if chunk:
            yield ''.join(chunk)

    def send_notice(self, text, target):
        """Send a NOTICE (thread-safe)."""
        self.send_raw(f'NOTICE {target} :{text}')

    async def _send_loop(self):
        """Process the send queue with flood protection."""
        while self._running:
            try:
                line = await asyncio.wait_for(
                    self._send_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Refill tokens
                now = time.time()
                elapsed = now - self._last_refill
                self._flood_tokens = min(
                    self._flood_burst,
                    self._flood_tokens + elapsed * self._flood_refill,
                )
                self._last_refill = now
                continue

            # Wait for a token
            while self._flood_tokens < 1:
                await asyncio.sleep(0.1)
                now = time.time()
                elapsed = now - self._last_refill
                self._flood_tokens = min(
                    self._flood_burst,
                    self._flood_tokens + elapsed * self._flood_refill,
                )
                self._last_refill = now

            self._flood_tokens -= 1
            await self._send_raw(line)

    # --- IRC Protocol ---

    async def register(self):
        """Send NICK and USER to register with the server."""
        auth_method = self.settings.core.auth_method

        if auth_method and auth_method.lower() == 'sasl':
            self._cap_negotiating = True
            await self._send_raw('CAP REQ :sasl')

        await self._send_raw(f'NICK {self.nick}')
        await self._send_raw(
            f'USER {self.nick} 0 * :{self.nick} - ibot')

    async def _handle_line(self, line):
        """Process a single line from the server."""
        line = line.strip()
        if not line:
            return

        LOGGER.debug("<<< %s", line)

        # Handle PING immediately
        if line.startswith('PING'):
            pong = line.replace('PING', 'PONG', 1)
            await self._send_raw(pong)
            return

        # Parse basic IRC structure for internal handling
        parts = line.split(' ')

        # Strip tags
        if parts[0].startswith('@'):
            parts = parts[1:]

        prefix = None
        if parts[0].startswith(':'):
            prefix = parts[0][1:]
            parts = parts[1:]

        if not parts:
            return

        command = parts[0].upper()
        params = parts[1:]

        # Handle CAP (capability negotiation)
        if command == 'CAP':
            await self._handle_cap(params)
            return

        # Handle SASL
        if command == 'AUTHENTICATE':
            await self._handle_authenticate(params)
            return

        # RPL_WELCOME (001) - registration complete
        if command == '001':
            self._registered = True
            LOGGER.info("Registered as %s", self.nick)
            await self._on_registered()

        # ERR_NICKNAMEINUSE (433)
        if command == '433':
            self.nick = self.nick + '_'
            await self._send_raw(f'NICK {self.nick}')

        # RPL_SASLSUCCESS (903)
        if command == '903':
            LOGGER.info("SASL authentication successful")
            self._sasl_in_progress = False
            if self._cap_negotiating:
                await self._send_raw('CAP END')
                self._cap_negotiating = False

        # ERR_SASLFAIL (904)
        if command in ('904', '905', '906'):
            LOGGER.error("SASL authentication failed: %s", line)
            self._sasl_in_progress = False
            if self._cap_negotiating:
                await self._send_raw('CAP END')
                self._cap_negotiating = False

        # Handle JOIN for channel/user tracking
        if command == 'JOIN' and prefix:
            nick = prefix.split('!')[0]
            channel = params[0].lstrip(':') if params else None
            if channel:
                self._track_join(nick, channel)

        # Handle PART
        if command == 'PART' and prefix:
            nick = prefix.split('!')[0]
            channel = params[0] if params else None
            if channel:
                self._track_part(nick, channel)

        # Handle QUIT
        if command == 'QUIT' and prefix:
            nick = prefix.split('!')[0]
            self._track_quit(nick)

        # Handle NICK change
        if command == 'NICK' and prefix:
            old_nick = prefix.split('!')[0]
            new_nick = params[0].lstrip(':') if params else None
            if new_nick:
                self._track_nick_change(old_nick, new_nick)

        # Handle KICK
        if command == 'KICK' and len(params) >= 2:
            channel = params[0]
            kicked = params[1]
            self._track_part(kicked, channel)

        # Handle MODE for privilege tracking
        if command == 'MODE' and len(params) >= 2:
            self._handle_mode(params)

        # Handle 353 (NAMES reply) for initial channel population
        if command == '353' and len(params) >= 3:
            self._handle_names(params)

        # Handle JOIN errors — retry for recoverable failures
        # 471=full, 473=invite-only, 474=banned, 475=bad key, 477=need registered
        if command in ('471', '473', '474', '475', '477'):
            failed_channel = params[1] if len(params) > 1 else '?'
            reason = ' '.join(params[2:]).lstrip(':') if len(params) > 2 else command
            LOGGER.warning("Failed to join %s: %s (code %s)", failed_channel, reason, command)
            # Retry for +R (477) and channel-full (471) after a delay
            if command in ('477', '471'):
                asyncio.create_task(self._retry_failed_join(failed_channel, delay=10))

        # Handle TOPIC
        if command in ('332', 'TOPIC'):
            self._handle_topic(command, params, prefix)

        # Dispatch to plugins
        if self.dispatcher:
            self.dispatcher.dispatch(line)

    async def _handle_cap(self, params):
        """Handle CAP (capability negotiation) responses."""
        if len(params) < 2:
            return

        subcommand = params[1].upper()

        if subcommand == 'ACK':
            cap_list = ' '.join(params[2:]).lstrip(':').split()
            if 'sasl' in cap_list:
                self._sasl_in_progress = True
                await self._send_raw('AUTHENTICATE PLAIN')

        elif subcommand == 'NAK':
            LOGGER.warning("CAP NAK received")
            if self._cap_negotiating:
                await self._send_raw('CAP END')
                self._cap_negotiating = False

    async def _handle_authenticate(self, params):
        """Handle SASL AUTHENTICATE challenge."""
        if params and params[0] == '+':
            user = self.settings.core.auth_user or self.nick
            password = self.settings.core.auth_password
            if password:
                auth_string = f'{user}\0{user}\0{password}'
                encoded = base64.b64encode(
                    auth_string.encode('utf-8')).decode('utf-8')
                await self._send_raw(f'AUTHENTICATE {encoded}')
            else:
                LOGGER.error("SASL: No password configured")
                await self._send_raw('AUTHENTICATE *')

    async def _on_registered(self):
        """Called after successful registration (001)."""
        # NickServ auth if not using SASL
        auth_method = self.settings.core.auth_method
        if auth_method and auth_method.lower() == 'nickserv':
            password = self.settings.core.auth_password
            target = self.settings.core.auth_target or 'NickServ'
            if password:
                await self._send_raw(
                    f'PRIVMSG {target} :IDENTIFY {password}')
                # Wait for NickServ to process identification before joining
                # channels. Channels with +R (registered only) will reject
                # JOINs until identification is complete.
                LOGGER.info("Waiting for NickServ identification before joining channels...")
                await asyncio.sleep(5)

        # Collect all channels to join
        config_channels = self.settings.core.channels
        LOGGER.info("Config channels (raw): %r", config_channels)
        LOGGER.info("Config channels (type): %s", type(config_channels))
        
        channels = set(config_channels) if config_channels else set()
        LOGGER.info("Config channels after set(): %d channels", len(channels))
        
        # Load persistent channels from DB (those joined via .bjoin)
        try:
            p_chans = self.db.get_plugin_value('admin', 'persistent_channels', [])
            if p_chans:
                if isinstance(p_chans, list):
                    LOGGER.info("Loading %d persistent channel(s) from DB: %s", 
                               len(p_chans), ', '.join(p_chans))
                    channels.update(p_chans)
                else:
                    LOGGER.warning("persistent_channels is not a list: %r", p_chans)
            else:
                LOGGER.info("No persistent channels in DB")
        except Exception:
            LOGGER.exception("Failed to load persistent channels from DB")

        LOGGER.info("Total channels to join: %d - %s", len(channels), sorted(channels))
        self._pending_joins = set()
        for channel in sorted(channels):
            channel = channel.strip()
            if channel:
                self._pending_joins.add(channel.lower())
                await self._send_raw(f'JOIN {channel}')
                LOGGER.info("Joining %s", channel)
            else:
                LOGGER.warning("Skipping empty channel string")

    async def _retry_failed_join(self, channel, delay=10):
        """Retry a failed JOIN after a delay."""
        LOGGER.info("Will retry joining %s in %d seconds", channel, delay)
        await asyncio.sleep(delay)
        if self._running and self._connected:
            LOGGER.info("Retrying JOIN %s", channel)
            await self._send_raw(f'JOIN {channel}')

    # --- Channel/User Tracking ---

    def _track_join(self, nick, channel):
        """Track a user joining a channel."""
        nick_id = Identifier(nick)
        chan_id = Identifier(channel)

        with self._state_lock:
            if nick_id.lower() == Identifier(self.nick).lower():
                if chan_id not in self.channels:
                    self.channels[chan_id] = Channel(channel)

            if nick_id not in self.users:
                self.users[nick_id] = User(nick)
            self.users[nick_id].channels.add(chan_id)

            if chan_id in self.channels:
                self.channels[chan_id].add_user(nick, user_obj=self.users[nick_id])

    def _track_part(self, nick, channel):
        """Track a user leaving a channel."""
        nick_id = Identifier(nick)
        chan_id = Identifier(channel)

        with self._state_lock:
            if nick_id.lower() == Identifier(self.nick).lower():
                self.channels.pop(chan_id, None)
            elif chan_id in self.channels:
                self.channels[chan_id].remove_user(nick)

            if nick_id in self.users:
                self.users[nick_id].channels.discard(chan_id)
                if not self.users[nick_id].channels:
                    self.users.pop(nick_id, None)

    def _track_quit(self, nick):
        """Track a user quitting."""
        nick_id = Identifier(nick)
        with self._state_lock:
            if nick_id in self.users:
                for chan_id in self.users[nick_id].channels:
                    if chan_id in self.channels:
                        self.channels[chan_id].remove_user(nick)
                self.users.pop(nick_id, None)

    def _track_nick_change(self, old_nick, new_nick):
        """Track a nickname change."""
        old_id = Identifier(old_nick)
        new_id = Identifier(new_nick)

        with self._state_lock:
            if old_id.lower() == Identifier(self.nick).lower():
                self.nick = new_nick

            if old_id in self.users:
                user = self.users.pop(old_id)
                user.nick = new_id
                self.users[new_id] = user

                for chan_id in user.channels:
                    if chan_id in self.channels:
                        chan = self.channels[chan_id]
                        priv = chan.privileges.pop(old_id, 0)
                        chan.users.pop(old_id, None)
                        chan.users[new_id] = user
                        if priv:
                            chan.privileges[new_id] = priv

    def _handle_mode(self, params):
        """Track channel mode changes for privilege updates."""
        if len(params) < 2:
            return

        channel = params[0]
        if not channel.startswith(('#', '&')):
            return

        chan_id = Identifier(channel)
        with self._state_lock:
            if chan_id not in self.channels:
                return

            mode_str = params[1]
            mode_params = params[2:]
            param_idx = 0
            adding = True

            for char in mode_str:
                if char == '+':
                    adding = True
                elif char == '-':
                    adding = False
                elif char in MODE_LETTER_TO_PRIVILEGE:
                    if param_idx < len(mode_params):
                        nick = mode_params[param_idx]
                        param_idx += 1
                        priv = MODE_LETTER_TO_PRIVILEGE[char]
                        nick_id = Identifier(nick)
                        current = self.channels[chan_id].privileges.get(nick_id, 0)
                        if adding:
                            self.channels[chan_id].privileges[nick_id] = current | priv
                        else:
                            self.channels[chan_id].privileges[nick_id] = current & ~priv
                elif char in 'beIkl':
                    # These modes take a parameter
                    param_idx += 1

    def _handle_names(self, params):
        """Handle 353 (RPL_NAMREPLY) for channel population."""
        # Format: <nick> = <channel> :<names>
        channel = None
        names_str = ''

        for i, p in enumerate(params):
            if p.startswith('#') or p.startswith('&'):
                channel = p
                # Names are in the trailing parameter
                rest = ' '.join(params[i + 1:])
                if rest.startswith(':'):
                    rest = rest[1:]
                names_str = rest
                break

        if not channel:
            return

        chan_id = Identifier(channel)
        with self._state_lock:
            if chan_id not in self.channels:
                self.channels[chan_id] = Channel(channel)

            for name in names_str.split():
                if not name:
                    continue
                # Strip privilege prefix
                priv = 0
                while name and name[0] in MODE_TO_PRIVILEGE:
                    priv |= MODE_TO_PRIVILEGE[name[0]]
                    name = name[1:]
                if name:
                    if Identifier(name) not in self.users:
                        self.users[Identifier(name)] = User(name)
                    self.users[Identifier(name)].channels.add(chan_id)
                    self.channels[chan_id].add_user(
                        name, priv, user_obj=self.users[Identifier(name)])

    def _handle_topic(self, command, params, prefix):
        """Track channel topic changes."""
        if command == '332' and len(params) >= 2:
            channel = params[1] if len(params) > 2 else params[0]
            topic = ' '.join(params[2:]).lstrip(':') if len(params) > 2 else ''
            chan_id = Identifier(channel)
            if chan_id in self.channels:
                self.channels[chan_id].topic = topic
        elif command == 'TOPIC' and params:
            channel = params[0]
            topic = ' '.join(params[1:]).lstrip(':')
            chan_id = Identifier(channel)
            if chan_id in self.channels:
                self.channels[chan_id].topic = topic

    def get_privilege(self, channel, nick):
        """Get a user's privilege level in a channel."""
        chan_id = Identifier(channel)
        with self._state_lock:
            if chan_id in self.channels:
                return self.channels[chan_id].privileges.get(
                    Identifier(nick), 0)
            return 0

    # --- Main Loop ---

    async def _read_loop(self):
        """Read lines from the server and process them."""
        buffer = ''
        while self._running and self._reader:
            try:
                data = await self._reader.read(4096)
                if not data:
                    LOGGER.warning("Connection closed by server")
                    break

                buffer += data.decode('utf-8', errors='replace')
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    await self._handle_line(line)
                # Handle lines ending with just \n
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        await self._handle_line(line)

            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.exception("Error reading from server")
                break

        self._connected = False

    async def _interval_runner(self, interval_secs, func, plugin_name):
        """Run a plugin's interval function periodically with backoff on errors."""
        from ibot.sopel_shim.bot import SopelWrapper
        from ibot.sopel_shim.trigger import PreTrigger, Trigger

        await asyncio.sleep(interval_secs)  # Initial delay
        consecutive_failures = 0
        
        while self._running:
            try:
                # Interval functions get bot but no trigger
                wrapper = SopelWrapper.__new__(SopelWrapper)
                wrapper._bot = self
                wrapper._trigger = None
                wrapper._default_destination = None
                wrapper._output_prefix = getattr(func, '_output_prefix', '')

                # Run in thread since it may block
                await asyncio.get_event_loop().run_in_executor(
                    None, func, wrapper)
                consecutive_failures = 0  # Reset on success
            except Exception:
                consecutive_failures += 1
                LOGGER.exception("Error in interval job %s.%s (failure %d/%d)",
                                 plugin_name, func.__name__,
                                 consecutive_failures, INTERVAL_JOB_MAX_FAILURES)
                
                if consecutive_failures >= INTERVAL_JOB_MAX_FAILURES:
                    LOGGER.error("Disabling interval job %s.%s after %d consecutive failures",
                                 plugin_name, func.__name__, consecutive_failures)
                    return
                
                # Exponential backoff on errors
                backoff_delay = min(interval_secs, INTERVAL_JOB_BACKOFF_BASE * (2 ** (consecutive_failures - 1)))
                await asyncio.sleep(backoff_delay)
                continue
                
            await asyncio.sleep(interval_secs)

    async def run(self):
        """Main run loop with auto-reconnect."""
        self._running = True
        self._loop = asyncio.get_event_loop()

        # Handle graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._signal_shutdown(s)))
            except (NotImplementedError, RuntimeError):
                pass

        while self._running:
            try:
                await self.connect()
                await self.register()

                # Start send loop and read loop
                send_task = asyncio.create_task(self._send_loop())
                read_task = asyncio.create_task(self._read_loop())

                # Start interval jobs
                if self.dispatcher:
                    for iv, func, pname in self.dispatcher.get_interval_jobs():
                        task = asyncio.create_task(
                            self._interval_runner(iv, func, pname))
                        self._interval_tasks.append(task)

                # Wait for either the read task to finish or the bot to stop
                done, pending = await asyncio.wait(
                    [read_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cleanup tasks for this connection session
                send_task.cancel()
                for task in self._interval_tasks:
                    task.cancel()
                self._interval_tasks.clear()

                # Ensure connection is closed
                if self._writer:
                    self._writer.close()
                    await self._writer.wait_closed()

            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    LOGGER.exception("Connection error")

            if not self._running:
                break

            if self.settings.core.reconnect_on_disconnect:
                LOGGER.info("Reconnecting in %d seconds...",
                            self._reconnect_delay)
                try:
                    await asyncio.sleep(self._reconnect_delay)
                except asyncio.CancelledError:
                    break
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, MAX_RECONNECT_DELAY)
            else:
                break

        # Final cleanup
        await self._cleanup()

    async def _signal_shutdown(self, sig):
        """Handle shutdown signal by breaking the run loop."""
        LOGGER.info("Shutdown signal received: %s", sig)
        self._running = False
        # Close connection to break the read loop
        if self._writer:
            try:
                self._writer.write(b'QUIT :Shutdown signal\r\n')
                self._writer.close()
            except Exception:
                pass

    async def _cleanup(self):
        """Clean up connections and resources."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

        self.db.close()
        LOGGER.info("Bot shut down.")
