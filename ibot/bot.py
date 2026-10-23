"""Core IRC client for ibot.

Provides an asyncio-based IRC connection with SSL/TLS support,
SASL authentication, auto-reconnect, flood protection,
channel/user tracking, and integration with the plugin dispatcher.
"""

import asyncio
import base64
import codecs
import logging
import logging.handlers
import os
import random
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
INITIAL_RECONNECT_DELAY = 5  # Reconnect delay after a successful session
MAX_LINE_BYTES = 510  # IRC line limit (512) minus CRLF
CONNECT_TIMEOUT = 60  # Seconds to wait for the TCP/TLS connection
READ_TIMEOUT = 240  # Silence before we send a keepalive PING
PING_TIMEOUT = 60  # Silence after the keepalive PING before reconnecting
MAX_READ_BUFFER = 65536  # Max unterminated input kept between reads
WAIT_CLOSED_TIMEOUT = 5  # Max wait for the socket to close
QUIT_TIMEOUT = 3  # Max wait for the server to close the link after QUIT
MAX_NICK_ATTEMPTS = 20  # Alternate nicks tried before reconnecting
DEFAULT_NICKLEN = 30  # Assumed NICKLEN before ISUPPORT arrives
MIN_NICKLEN = 9  # RFC 1459 minimum, used after repeated failures
NICK_REGAIN_DELAY = 3  # Seconds between GHOST and NICK
JOIN_RETRY_BASE_DELAY = 10  # First JOIN retry delay (471/477)
JOIN_RETRY_MAX_DELAY = 300  # Max JOIN retry delay
JOIN_RETRY_MAX_ATTEMPTS = 8  # JOIN retries per channel per connection
RAW_LOG_MAX_BYTES = 10 * 1024 * 1024  # Raw log rotation size
RAW_LOG_BACKUPS = 3  # Raw log files kept

_CAP_SUBCOMMANDS = ('ACK', 'NAK', 'LS', 'NEW', 'DEL', 'LIST')
_SAFE_AUTHENTICATE_ARGS = {'PLAIN', 'EXTERNAL', 'SCRAM-SHA-1', 'SCRAM-SHA-256', '+', '*'}
_SENSITIVE_SERVICE_VERBS = {
    'IDENTIFY', 'ID', 'GHOST', 'RECOVER', 'REGAIN', 'RELEASE', 'REGISTER',
    'GROUP', 'LOGIN', 'AUTH', 'CONFIRM', 'RESETPASS', 'SETPASS',
}

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
# Defaults used until the server sends ISUPPORT PREFIX / CHANMODES
DEFAULT_PREFIX_MODES = (('q', '~'), ('a', '&'), ('o', '@'), ('h', '%'), ('v', '+'))
DEFAULT_CHANMODES = ('beI', 'k', 'l', '')


class User:
    """Represents a tracked IRC user."""

    def __init__(self, nick, user=None, host=None):
        self.nick = Identifier(nick)
        self.user = user or ''
        self.host = host or ''
        self.account = None
        self.realname = ''
        self.away = None
        self.is_bot = False  # set from bot-mode / message tags when available
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
        self._reconnect_delay = INITIAL_RECONNECT_DELAY
        self._quitting = False
        self._restart_requested = False
        self._loop_thread_id = None

        # Flood protection
        self._send_queue = asyncio.Queue()
        self._flood_burst = settings.core.flood_burst or 4
        self._flood_tokens = self._flood_burst
        self._flood_refill = settings.core.flood_refill or 1
        self._last_refill = time.time()

        # SASL / CAP
        self._sasl_in_progress = False
        self._sasl_started = False
        self._cap_negotiating = False
        self._requested_caps = set()
        self._enabled_caps = set()
        self._cap_available = set()
        self._cap_ls_buffer = set()
        self._cap_pending = 0
        self._cap_split_retry = False
        self._sasl_wanted = bool(
            settings.core.auth_method
            and settings.core.auth_method.lower() == 'sasl'
        )

        # Server capabilities advertised in RPL_ISUPPORT (005)
        self.isupport = {}
        self._prefix_modes = dict(DEFAULT_PREFIX_MODES)   # letter -> symbol
        self._chanmodes = DEFAULT_CHANMODES               # (A, B, C, D)
        self._nicklen = None
        self._nick_attempts = 0

        # JOIN retry bookkeeping (471/477)
        self._pending_joins = set()
        self._join_retry_tasks = {}    # channel_lower -> Task
        self._join_retry_counts = {}   # channel_lower -> attempts so far

        # Misc per-connection helper tasks (e.g. nick regain)
        self._conn_tasks = set()

        # Dispatcher (set after construction)
        self.dispatcher = None

        # Interval scheduler: {plugin_name: [(interval, func, Task), ...]}
        self._interval_tasks = {}
        self._interval_lock = threading.Lock()
        self._loop = None

        # Optional raw traffic log ([core] log_raw)
        self._raw_logger = None
        self._setup_raw_log()

    # --- Raw log ---

    def _setup_raw_log(self):
        """Set up the redacted raw IRC log when [core] log_raw is enabled."""
        try:
            enabled = bool(getattr(self.settings.core, 'log_raw', False))
        except Exception:
            enabled = False
        if not enabled:
            return
        try:
            logdir = self.settings.core.logdir
            os.makedirs(logdir, mode=0o700, exist_ok=True)
            basename = getattr(self.settings, 'basename', None) or 'ibot'
            path = os.path.join(logdir, f'{basename}.raw.log')
            raw_logger = logging.getLogger('ibot.raw')
            raw_logger.propagate = False
            raw_logger.setLevel(logging.INFO)
            for h in list(raw_logger.handlers):
                if getattr(h, 'baseFilename', None) == os.path.abspath(path):
                    raw_logger.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass
            handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=RAW_LOG_MAX_BYTES, backupCount=RAW_LOG_BACKUPS,
                encoding='utf-8')
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            handler.setFormatter(logging.Formatter(
                '%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
            raw_logger.addHandler(handler)
            self._raw_logger = raw_logger
            LOGGER.info("Raw IRC log (redacted) enabled: %s", path)
        except Exception:
            LOGGER.exception("Could not set up raw IRC log; continuing without it")
            self._raw_logger = None

    def _raw_log(self, direction, sanitized_line):
        if self._raw_logger is not None:
            try:
                self._raw_logger.info("%s %s", direction, sanitized_line)
            except Exception:
                pass

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

        kwargs = {}
        bind_host = getattr(self.settings.core, 'bind_host', None)
        if bind_host:
            kwargs['local_addr'] = (bind_host, 0)
            LOGGER.info("Binding outgoing connection to %s", bind_host)

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx, **kwargs),
            timeout=CONNECT_TIMEOUT,
        )
        self._connected = True
        LOGGER.info("Connected to %s:%d", host, port)

    @staticmethod
    def _clean_line(line):
        """Make a line safe to put on the wire.

        CR, LF and NUL inside the line are replaced with spaces (so a plugin
        can never inject a second IRC command), and the result is truncated
        to 510 bytes (512 minus CRLF) on a UTF-8 character boundary.

        Returns ``(clean_text, wire_bytes)``.
        """
        line = str(line).rstrip('\r\n')
        if '\r' in line or '\n' in line or '\0' in line:
            line = line.replace('\r', ' ').replace('\n', ' ').replace('\0', ' ')
        raw = line.encode('utf-8', errors='replace')
        if len(raw) > MAX_LINE_BYTES:
            line = raw[:MAX_LINE_BYTES].decode('utf-8', errors='ignore')
            raw = line.encode('utf-8', errors='replace')
        return line, raw + b'\r\n'

    async def _send_raw(self, line):
        """Send a raw IRC line (internal async version)."""
        if not self._writer:
            return
        clean, data = self._clean_line(line)
        safe = self._sanitize_for_log(clean)
        LOGGER.debug(">>> %s", safe)
        self._raw_log('>>>', safe)
        try:
            self._note_outgoing(clean)
        except Exception:
            LOGGER.debug("Outgoing-line bookkeeping failed", exc_info=True)
        self._writer.write(data)
        await self._writer.drain()

    def _service_targets(self):
        targets = {'nickserv', 'ns'}
        try:
            target = self.settings.core.auth_target
            if target and (self.settings.core.auth_method or '').lower() == 'nickserv':
                targets.add(str(target).split('@', 1)[0].lower())
        except Exception:
            pass
        return targets

    def _sanitize_for_log(self, line):
        """Return ``line`` with credentials redacted, for logging only."""
        try:
            return self._redact(line)
        except Exception:
            return '[line not logged: redaction failed]'

    def _redact(self, line):
        s = str(line).rstrip('\r\n')
        head = ''
        rest = s
        if rest.startswith('@'):
            tags, _, rest = rest.partition(' ')
            head += tags + ' '
        if rest.startswith(':'):
            pfx, _, rest = rest.partition(' ')
            head += pfx + ' '
        cmd, _, args = rest.partition(' ')
        ucmd = cmd.upper()

        if ucmd == 'AUTHENTICATE':
            if args.strip().upper() in _SAFE_AUTHENTICATE_ARGS:
                return s
            return head + cmd + ' [redacted]'
        if ucmd == 'PASS':
            return head + cmd + ' [redacted]'
        if ucmd == 'OPER':
            name = args.split(' ', 1)[0] if args else ''
            return f'{head}{cmd} {name} [redacted]'.rstrip()

        def _redact_service_body(body):
            words = body.split()
            if not words:
                return None
            verb = words[0].upper()
            if verb in _SENSITIVE_SERVICE_VERBS:
                return words[0]
            if verb == 'SET' and len(words) > 1 and words[1].upper() in ('PASSWORD', 'PASS'):
                return words[0] + ' ' + words[1]
            return None

        if ucmd in ('PRIVMSG', 'NOTICE', 'SQUERY'):
            target, _, text = args.partition(' ')
            tname = target.split('@', 1)[0].lower()
            if tname in self._service_targets():
                body = text[1:] if text.startswith(':') else text
                kept = _redact_service_body(body)
                if kept is not None:
                    return f'{head}{cmd} {target} :{kept} [redacted]'
            return s
        if ucmd in ('NS', 'NICKSERV', 'CS', 'CHANSERV'):
            body = args[1:] if args.startswith(':') else args
            kept = _redact_service_body(body)
            if kept is not None:
                return f'{head}{cmd} {kept} [redacted]'
            return s
        if ucmd in ('IDENTIFY', 'LOGIN'):
            return head + cmd + ' [redacted]'
        return s

    def _note_outgoing(self, clean_line):
        """Bookkeeping for lines we send (runs on the event loop)."""
        if not clean_line[:5].upper() == 'PART ':
            return
        parts = clean_line.split(' ')
        if len(parts) >= 2:
            for chan in parts[1].lstrip(':').split(','):
                if chan:
                    self._cancel_join_retry(chan)

    def send_raw(self, line):
        """Send a raw IRC line (thread-safe, called by plugins)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._send_queue.put(line), self._loop)

    @staticmethod
    def _split_lines(text):
        """Split text on CR/LF. Text without line breaks is returned as-is."""
        text = str(text)
        if '\r' not in text and '\n' not in text:
            return [text]
        return [ln for ln in re.split(r'\r\n|\r|\n', text) if ln.strip()]

    def send_privmsg(self, target, text):
        """Send a PRIVMSG (thread-safe)."""
        # Split on line breaks, then long lines (512 bytes max per IRC line
        # minus overhead)
        for line in self._split_lines(text):
            for chunk in self._split_message(line):
                self.send_privmsg_chunk(target, chunk)

    def send_privmsg_chunk(self, target, text):
        """Send a single PRIVMSG body without further splitting.

        Used by SopelWrapper.say() after it has already applied max_messages
        and truncation so chunks are not re-split and re-counted.
        """
        self.send_raw(f'PRIVMSG {target} :{text}')

    @staticmethod
    def _split_message(text, max_bytes=MAX_MESSAGE_LENGTH):
        """Split text into chunks that fit within max_bytes when UTF-8 encoded.

        Splits on character boundaries so multibyte characters are never cut in
        half, and measures length in bytes (IRC's real limit) rather than in
        characters.
        """
        text = str(text)
        if len(text.encode('utf-8', errors='replace')) <= max_bytes:
            yield text
            return

        chunk = []
        chunk_bytes = 0
        for ch in text:
            ch_bytes = len(ch.encode('utf-8', errors='replace'))
            if chunk_bytes + ch_bytes > max_bytes and chunk:
                yield ''.join(chunk)
                chunk = []
                chunk_bytes = 0
            chunk.append(ch)
            chunk_bytes += ch_bytes
        if chunk:
            yield ''.join(chunk)

    def send_notice(self, text, target):
        """Send a NOTICE (thread-safe). Multi-line text becomes several NOTICEs."""
        for line in self._split_lines(text):
            for chunk in self._split_message(line):
                self.send_raw(f'NOTICE {target} :{chunk}')

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
            try:
                await self._send_raw(line)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Error sending line to server")

    # --- IRC Protocol ---

    async def register(self):
        """Send CAP LS, NICK and USER to register with the server.

        Negotiates useful IRCv3 capabilities (account-tag, extended-join,
        multi-prefix, server-time, plus sasl when configured). Only the caps
        the server actually advertises are requested. CAP END is sent once
        all requests are answered (and SASL has finished, if used).
        """
        self._cap_negotiating = True
        self._cap_ls_buffer = set()
        self._cap_available = set()
        self._cap_pending = 0
        self._cap_split_retry = False
        self._sasl_started = False
        self._sasl_in_progress = False
        self._requested_caps = {
            'account-tag',
            'extended-join',
            'multi-prefix',
            'server-time',
        }
        if self._sasl_wanted:
            self._requested_caps.add('sasl')

        await self._send_raw('CAP LS 302')
        await self._send_raw(f'NICK {self.nick}')
        user = getattr(self.settings.core, 'user', None) or self.nick
        realname = getattr(self.settings.core, 'name', None) or f'{self.nick} - ibot'
        await self._send_raw(f'USER {user} 0 * :{realname}')

    async def _handle_line(self, line):
        """Process a single line from the server."""
        line = line.strip()
        if not line:
            return

        safe = self._sanitize_for_log(line)
        LOGGER.debug("<<< %s", safe)
        self._raw_log('<<<', safe)

        # Parse basic IRC structure for internal handling
        parts = line.split(' ')

        # Strip tags
        if parts and parts[0].startswith('@'):
            parts = parts[1:]

        prefix = None
        if parts and parts[0].startswith(':'):
            prefix = parts[0][1:]
            parts = parts[1:]

        if not parts:
            return

        command = parts[0].upper()
        params = parts[1:]

        # Handle PING immediately
        if command == 'PING':
            token = ' '.join(params)
            await self._send_raw(f'PONG {token}' if token else 'PONG')
            return

        # Handle CAP (capability negotiation)
        if command == 'CAP':
            await self._handle_cap(params)
            return

        # Handle SASL
        if command == 'AUTHENTICATE':
            await self._handle_authenticate(params)
            return

        try:
            await self._process_line(command, params, prefix, line)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Internal error handling server line: %s", safe)

        # Dispatch to plugins
        if self.dispatcher:
            try:
                self.dispatcher.dispatch(line)
            except Exception:
                LOGGER.exception("Dispatcher error for line: %s", safe)

    async def _process_line(self, command, params, prefix, line):
        """Internal protocol/state handling for one parsed server line."""
        # RPL_WELCOME (001) - registration complete
        if command == '001':
            self._registered = True
            self._reconnect_delay = INITIAL_RECONNECT_DELAY
            self._nick_attempts = 0
            if params and params[0] and params[0] != '*':
                actual = params[0].lstrip(':')
                if actual and actual != self.nick:
                    LOGGER.info("Server registered us as %s (was using %s)",
                                actual, self.nick)
                    self.nick = actual
            self._refresh_nick_patterns()
            LOGGER.info("Registered as %s", self.nick)
            await self._on_registered()

        # RPL_ISUPPORT (005)
        if command == '005':
            self._handle_isupport(params)

        # Nick errors: 432 erroneous, 433 in use, 436 collision, 437 unavailable
        if command in ('432', '433', '436', '437'):
            await self._handle_nick_error(command, params)

        # RPL_SASLSUCCESS (903)
        if command == '903':
            LOGGER.info("SASL authentication successful")
            self._sasl_in_progress = False
            await self._maybe_cap_end()

        # SASL failures: 902 nick locked, 904 failed, 905 too long,
        # 906 aborted, 907 already authenticated
        if command in ('902', '904', '905', '906', '907'):
            if command == '907':
                LOGGER.info("SASL: already authenticated")
            else:
                LOGGER.error("SASL authentication failed (%s): %s",
                             command, self._sanitize_for_log(line))
            self._sasl_in_progress = False
            await self._maybe_cap_end()

        if command == 'ERROR':
            LOGGER.warning("Server ERROR: %s", self._sanitize_for_log(line))

        # Handle JOIN for channel/user tracking
        if command == 'JOIN' and prefix:
            nick = prefix.split('!')[0]
            # params may include extended-join: channel [account [realname]]
            channel = params[0].lstrip(':') if params else None
            account = None
            realname = ''
            if len(params) >= 2:
                # extended-join: account is params[1], realname trailing
                acct = params[1].lstrip(':')
                if acct and acct != '*':
                    account = acct
            if len(params) >= 3:
                realname = ' '.join(params[2:]).lstrip(':')
            if channel:
                self._track_join(nick, channel, account=account,
                                 realname=realname, prefix=prefix)
                if Identifier(nick).lower() == Identifier(self.nick).lower():
                    self._cancel_join_retry(channel)

        # ACCOUNT message (account-notify / some networks after account-tag)
        if command == 'ACCOUNT' and prefix:
            nick = prefix.split('!')[0]
            account = params[0].lstrip(':') if params else None
            if account == '*':
                account = None
            self._track_account(nick, account)

        # Handle PART
        if command == 'PART' and prefix:
            nick = prefix.split('!')[0]
            channel = params[0].lstrip(':') if params else None
            if channel:
                for chan in channel.split(','):
                    if chan:
                        self._track_part(nick, chan)
                        if Identifier(nick).lower() == Identifier(self.nick).lower():
                            self._cancel_join_retry(chan)

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
            channel = params[0].lstrip(':')
            kicked = params[1].lstrip(':')
            self._track_part(kicked, channel)
            if Identifier(kicked).lower() == Identifier(self.nick).lower():
                self._cancel_join_retry(channel)

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
            # Retry for +R (477) and channel-full (471) with capped backoff
            if command in ('477', '471') and failed_channel != '?':
                self._schedule_join_retry(failed_channel)

        # Handle TOPIC
        if command in ('332', 'TOPIC'):
            self._handle_topic(command, params, prefix)

    # --- CAP / SASL ---

    async def _handle_cap(self, params):
        """Handle CAP (capability negotiation) responses."""
        if not params:
            return

        # CAP replies look like: * ACK :cap1 cap2   or  nick ACK :...
        idx = None
        if len(params) >= 2 and params[1].upper() in _CAP_SUBCOMMANDS:
            idx = 1
        elif params[0].upper() in _CAP_SUBCOMMANDS:
            idx = 0
        if idx is None:
            return
        subcommand = params[idx].upper()
        rest = params[idx + 1:]
        more_coming = False
        if subcommand in ('LS', 'LIST') and len(rest) >= 2 and rest[0] == '*':
            more_coming = True
            rest = rest[1:]
        cap_list = ' '.join(rest).lstrip(':').split()

        if subcommand == 'LS':
            for cap in cap_list:
                name = cap.split('=', 1)[0]
                if name:
                    self._cap_ls_buffer.add(name)
            if more_coming:
                return
            self._cap_available = set(self._cap_ls_buffer)
            self._cap_ls_buffer = set()
            LOGGER.info("Server capabilities: %s",
                        ' '.join(sorted(self._cap_available)) or '(none)')
            if self._sasl_wanted and 'sasl' not in self._cap_available:
                LOGGER.warning(
                    "SASL is configured but the server does not offer the "
                    "'sasl' capability; continuing WITHOUT SASL")
            if not self._cap_negotiating:
                return
            want = sorted(self._requested_caps & self._cap_available)
            if want:
                self._cap_pending += 1
                await self._send_raw('CAP REQ :' + ' '.join(want))
            else:
                await self._maybe_cap_end()

        elif subcommand == 'ACK':
            self._cap_pending = max(0, self._cap_pending - 1)
            for cap in cap_list:
                if cap.startswith('-'):
                    self._enabled_caps.discard(cap[1:])
                elif cap:
                    self._enabled_caps.add(cap)
            LOGGER.info("CAP ACK: %s", ' '.join(cap_list) or '(none)')
            if ('sasl' in self._enabled_caps and self._sasl_wanted
                    and not self._sasl_started and self._cap_negotiating):
                self._sasl_started = True
                self._sasl_in_progress = True
                await self._send_raw('AUTHENTICATE PLAIN')
            await self._maybe_cap_end()

        elif subcommand == 'NAK':
            self._cap_pending = max(0, self._cap_pending - 1)
            LOGGER.warning("CAP NAK: %s", ' '.join(cap_list) or '(none)')
            if self._cap_negotiating and len(cap_list) > 1 and not self._cap_split_retry:
                # A NAK rejects the whole request; retry the caps one by one
                # so a single unsupported cap doesn't cost us all of them.
                self._cap_split_retry = True
                for cap in cap_list:
                    self._cap_pending += 1
                    await self._send_raw(f'CAP REQ :{cap}')
            elif 'sasl' in cap_list and self._sasl_wanted:
                LOGGER.error("Server refused (NAK) the SASL capability; "
                             "continuing WITHOUT SASL")
            await self._maybe_cap_end()

        elif subcommand == 'DEL':
            for cap in cap_list:
                self._enabled_caps.discard(cap.split('=', 1)[0])
                self._cap_available.discard(cap.split('=', 1)[0])
            LOGGER.info("CAP DEL: %s", ' '.join(cap_list))

        elif subcommand == 'NEW':
            LOGGER.info("CAP NEW: %s", ' '.join(cap_list))

    async def _maybe_cap_end(self):
        """Send CAP END once all CAP REQs are answered and SASL is done."""
        if (self._cap_negotiating and self._cap_pending <= 0
                and not self._sasl_in_progress):
            self._cap_negotiating = False
            await self._send_raw('CAP END')

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

    # --- ISUPPORT ---

    def _handle_isupport(self, params):
        """Parse RPL_ISUPPORT tokens (NICKLEN, PREFIX, CHANMODES, ...)."""
        for tok in params[1:]:
            if tok.startswith(':'):
                break
            if tok.startswith('-'):
                self.isupport.pop(tok[1:].upper(), None)
                continue
            key, _, value = tok.partition('=')
            key = key.upper()
            self.isupport[key] = value
            try:
                if key == 'PREFIX':
                    m = re.match(r'^\(([^)]*)\)(.*)$', value)
                    if m and len(m.group(1)) == len(m.group(2)):
                        self._prefix_modes = dict(zip(m.group(1), m.group(2)))
                elif key == 'CHANMODES':
                    groups = (value.split(',') + ['', '', '', ''])[:4]
                    self._chanmodes = tuple(groups)
                elif key == 'NICKLEN' and value:
                    self._nicklen = int(value)
            except (ValueError, TypeError):
                LOGGER.debug("Bad ISUPPORT token: %s", tok)

    # --- Nick handling ---

    @staticmethod
    def _sanitize_nick(nick):
        cleaned = re.sub(r'[^A-Za-z0-9\[\]\\`_\^\{\|\}\-]', '', str(nick or ''))
        cleaned = cleaned.lstrip('0123456789-')
        return cleaned

    def _next_nick(self, command):
        """Pick the next nick to try during registration."""
        attempt = self._nick_attempts
        if self._nicklen:
            limit = self._nicklen
        else:
            limit = DEFAULT_NICKLEN if attempt <= 6 else MIN_NICKLEN
        base = self._desired_nick
        if command == '432':
            base = self._sanitize_nick(base) or 'ibot'
            if attempt == 1 and base[:limit] != self.nick:
                return base[:limit]
        if attempt == 1:
            suffix = '_'
        elif attempt == 2:
            suffix = '__'
        else:
            suffix = '_' + str(random.randint(100, 999))
        keep = max(1, limit - len(suffix))
        return base[:keep] + suffix

    async def _handle_nick_error(self, command, params):
        attempted = params[1] if len(params) > 1 else self.nick
        reason = ' '.join(params[2:]).lstrip(':') if len(params) > 2 else command
        if self._registered:
            LOGGER.warning("Nick change to %s refused (%s: %s); keeping %s",
                           attempted, command, reason, self.nick)
            return
        self._nick_attempts += 1
        if self._nick_attempts > MAX_NICK_ATTEMPTS:
            LOGGER.error("No usable nick after %d attempts; dropping connection "
                         "to retry later", self._nick_attempts - 1)
            await self._close_connection()
            return
        new_nick = self._next_nick(command)
        LOGGER.warning("Nick %s unavailable (%s: %s); trying %s",
                       attempted, command, reason, new_nick)
        self.nick = new_nick
        await self._send_raw(f'NICK {new_nick}')

    def _refresh_nick_patterns(self):
        """Tell the dispatcher our nick changed so $nick patterns follow."""
        disp = self.dispatcher
        if disp is not None and hasattr(disp, 'refresh_nick_patterns'):
            try:
                disp.refresh_nick_patterns()
            except Exception:
                LOGGER.exception("Failed to refresh nick-based patterns")

    async def _regain_nick(self):
        """Try to get our configured nick back (NickServ GHOST, then NICK)."""
        desired = self._desired_nick
        try:
            core = self.settings.core
            method = (core.auth_method or '').lower()
            password = core.auth_password
            if not password or method not in ('nickserv', 'sasl'):
                LOGGER.info("Using nick %s (wanted %s); no NickServ password "
                            "configured, not attempting to regain it",
                            self.nick, desired)
                return
            target = (core.auth_target or 'NickServ') if method == 'nickserv' else 'NickServ'
            LOGGER.info("Nick %s is taken; asking %s to GHOST it", desired, target)
            await self._send_raw(f'PRIVMSG {target} :GHOST {desired} {password}')
            await asyncio.sleep(NICK_REGAIN_DELAY)
            if (self._connected and self._running
                    and Identifier(self.nick).lower() != Identifier(desired).lower()):
                await self._send_raw(f'NICK {desired}')
                if method == 'nickserv':
                    # The IDENTIFY sent at 001 was for the fallback nick;
                    # identify again once we're back on the real one.
                    await asyncio.sleep(NICK_REGAIN_DELAY)
                    if (self._connected and self._running
                            and Identifier(self.nick).lower() == Identifier(desired).lower()):
                        await self._send_raw(f'PRIVMSG {target} :IDENTIFY {password}')
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Nick regain failed")

    def _start_conn_task(self, coro):
        task = asyncio.create_task(coro)
        self._conn_tasks.add(task)
        task.add_done_callback(self._conn_tasks.discard)
        return task

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

        # Get our nick back if registration had to fall back to another one
        if Identifier(self.nick).lower() != Identifier(self._desired_nick).lower():
            self._start_conn_task(self._regain_nick())

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
                # Through the flood-controlled queue (big join bursts can
                # otherwise get us disconnected for excess flood)
                await self._send_queue.put(f'JOIN {channel}')
                LOGGER.info("Joining %s", channel)
            else:
                LOGGER.warning("Skipping empty channel string")

    def _schedule_join_retry(self, channel):
        """Retry a failed JOIN later, with capped exponential backoff."""
        key = channel.lower()
        task = self._join_retry_tasks.get(key)
        if task is not None and not task.done():
            return
        attempts = self._join_retry_counts.get(key, 0)
        if attempts >= JOIN_RETRY_MAX_ATTEMPTS:
            LOGGER.warning("Giving up on joining %s after %d retries",
                           channel, attempts)
            return
        self._join_retry_counts[key] = attempts + 1
        delay = min(JOIN_RETRY_BASE_DELAY * (2 ** attempts), JOIN_RETRY_MAX_DELAY)
        self._join_retry_tasks[key] = asyncio.create_task(
            self._retry_failed_join(channel, delay=delay))

    async def _retry_failed_join(self, channel, delay=10):
        """Retry a failed JOIN after a delay."""
        key = channel.lower()
        try:
            LOGGER.info("Will retry joining %s in %d seconds", channel, delay)
            await asyncio.sleep(delay)
            if self._running and self._connected:
                LOGGER.info("Retrying JOIN %s", channel)
                await self._send_queue.put(f'JOIN {channel}')
        finally:
            if self._join_retry_tasks.get(key) is asyncio.current_task():
                self._join_retry_tasks.pop(key, None)

    def _cancel_join_retry(self, channel, reset=True):
        key = str(channel).lower()
        task = self._join_retry_tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
        if reset:
            self._join_retry_counts.pop(key, None)

    def _cancel_all_join_retries(self):
        for task in list(self._join_retry_tasks.values()):
            if not task.done():
                task.cancel()
        self._join_retry_tasks.clear()
        self._join_retry_counts.clear()

    # --- Channel/User Tracking ---

    def _track_join(self, nick, channel, account=None, realname='', prefix=None):
        """Track a user joining a channel."""
        nick_id = Identifier(nick)
        chan_id = Identifier(channel)

        with self._state_lock:
            if nick_id.lower() == Identifier(self.nick).lower():
                if chan_id not in self.channels:
                    self.channels[chan_id] = Channel(channel)

            if nick_id not in self.users:
                user_obj = User(nick)
                if prefix and '!' in prefix:
                    rest = prefix.split('!', 1)[1]
                    if '@' in rest:
                        user_obj.user, user_obj.host = rest.split('@', 1)
                    else:
                        user_obj.user = rest
                self.users[nick_id] = user_obj
            if account is not None:
                self.users[nick_id].account = account
            if realname:
                self.users[nick_id].realname = realname
            self.users[nick_id].channels.add(chan_id)

            if chan_id in self.channels:
                self.channels[chan_id].add_user(
                    nick, user_obj=self.users[nick_id])

    def _track_account(self, nick, account):
        """Update a user's services account (ACCOUNT / account-tag)."""
        nick_id = Identifier(nick)
        with self._state_lock:
            if nick_id not in self.users:
                self.users[nick_id] = User(nick)
            self.users[nick_id].account = account

    def get_user_account(self, nick):
        """Return the tracked services account for nick, or None."""
        nick_id = Identifier(nick)
        with self._state_lock:
            user = self.users.get(nick_id)
            return user.account if user else None

    def _track_part(self, nick, channel):
        """Track a user leaving a channel (PART or KICK)."""
        nick_id = Identifier(nick)
        chan_id = Identifier(channel)

        with self._state_lock:
            if nick_id.lower() == Identifier(self.nick).lower():
                chan = self.channels.pop(chan_id, None)
                if chan is not None:
                    # We left: forget members we no longer share a channel with
                    for member_id in list(chan.users.keys()):
                        member = self.users.get(member_id)
                        if member is None:
                            continue
                        member.channels.discard(chan_id)
                        if not member.channels:
                            self.users.pop(member_id, None)
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
                for chan_id in list(self.users[nick_id].channels):
                    if chan_id in self.channels:
                        self.channels[chan_id].remove_user(nick)
                self.users.pop(nick_id, None)

    def _track_nick_change(self, old_nick, new_nick):
        """Track a nickname change."""
        old_id = Identifier(old_nick)
        new_id = Identifier(new_nick)
        own = False

        with self._state_lock:
            if old_id.lower() == Identifier(self.nick).lower():
                self.nick = new_nick
                own = True

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

        if own:
            LOGGER.info("Our nick is now %s", new_nick)
            self._refresh_nick_patterns()

    def _handle_mode(self, params):
        """Track channel mode changes for privilege updates.

        Uses the server's ISUPPORT PREFIX / CHANMODES so parameters are
        consumed correctly for every mode type.
        """
        if len(params) < 2:
            return

        channel = params[0]
        if not channel.startswith(('#', '&', '!', '+')):
            return

        list_modes, always_modes, set_modes, _ = self._chanmodes
        prefix_modes = self._prefix_modes

        chan_id = Identifier(channel)
        with self._state_lock:
            if chan_id not in self.channels:
                return

            mode_str = params[1].lstrip(':')
            mode_params = [p.lstrip(':') for p in params[2:]]
            param_idx = 0
            adding = True

            for char in mode_str:
                if char == '+':
                    adding = True
                elif char == '-':
                    adding = False
                elif char in prefix_modes:
                    if param_idx < len(mode_params):
                        nick = mode_params[param_idx]
                        param_idx += 1
                        priv = MODE_LETTER_TO_PRIVILEGE.get(char, 0)
                        if not priv:
                            continue
                        nick_id = Identifier(nick)
                        current = self.channels[chan_id].privileges.get(nick_id, 0)
                        if adding:
                            self.channels[chan_id].privileges[nick_id] = current | priv
                        else:
                            self.channels[chan_id].privileges[nick_id] = current & ~priv
                elif char in list_modes or char in always_modes:
                    # Type A/B: always take a parameter
                    param_idx += 1
                elif char in set_modes:
                    # Type C: parameter only when being set
                    if adding:
                        param_idx += 1
                # Type D / unknown: no parameter

    def _symbol_privileges(self):
        """Map NAMES prefix symbols to privilege bits."""
        mapping = {}
        for letter, symbol in self._prefix_modes.items():
            priv = MODE_LETTER_TO_PRIVILEGE.get(letter) or MODE_TO_PRIVILEGE.get(symbol, 0)
            mapping[symbol] = priv
        for symbol, priv in MODE_TO_PRIVILEGE.items():
            mapping.setdefault(symbol, priv)
        return mapping

    def _handle_names(self, params):
        """Handle 353 (RPL_NAMREPLY) for channel population."""
        # Format: <nick> = <channel> :<names>
        channel = None
        names_str = ''

        for i, p in enumerate(params):
            if i == 0:
                continue  # our own nick
            if p.startswith(('#', '&', '!', '+')) and p not in ('=', '*', '@'):
                if p[0] in '+!' and i != 2:
                    continue
                channel = p
                # Names are in the trailing parameter
                rest = ' '.join(params[i + 1:])
                if rest.startswith(':'):
                    rest = rest[1:]
                names_str = rest
                break

        if not channel:
            return

        symbols = self._symbol_privileges()
        chan_id = Identifier(channel)
        with self._state_lock:
            if chan_id not in self.channels:
                self.channels[chan_id] = Channel(channel)

            for name in names_str.split():
                if not name:
                    continue
                # Strip privilege prefix
                priv = 0
                while name and name[0] in symbols:
                    priv |= symbols[name[0]]
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
        """Read lines from the server and process them.

        Uses an incremental UTF-8 decoder (multibyte characters split across
        reads decode correctly; invalid bytes become U+FFFD). If the server
        is silent for READ_TIMEOUT seconds we send a PING; if nothing at all
        arrives within PING_TIMEOUT after that, the connection is treated as
        dead and we reconnect.
        """
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        buffer = ''
        ping_sent = False
        while self._running and self._reader:
            try:
                timeout = PING_TIMEOUT if ping_sent else READ_TIMEOUT
                try:
                    data = await asyncio.wait_for(self._reader.read(4096), timeout)
                except asyncio.TimeoutError:
                    if ping_sent:
                        LOGGER.warning("No reply from server %ds after keepalive "
                                       "PING; reconnecting", PING_TIMEOUT)
                        break
                    ping_sent = True
                    LOGGER.info("No data from server for %ds; sending keepalive PING",
                                READ_TIMEOUT)
                    await self._send_raw(f'PING :ibot-{int(time.time())}')
                    continue

                if not data:
                    LOGGER.warning("Connection closed by server")
                    break
                ping_sent = False

                buffer += decoder.decode(data)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.rstrip('\r')
                    if not line.strip():
                        continue
                    try:
                        await self._handle_line(line)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        LOGGER.exception("Error handling line: %s",
                                         self._sanitize_for_log(line))
                if len(buffer) > MAX_READ_BUFFER:
                    LOGGER.warning("Discarding %d bytes of unterminated input",
                                   len(buffer))
                    buffer = ''

            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.exception("Error reading from server")
                break

        self._connected = False

    async def _interval_runner(self, interval_secs, func, plugin_name):
        """Run a plugin's interval function periodically with backoff on errors."""
        from ibot.sopel_shim.bot import SopelWrapper

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
                await asyncio.get_running_loop().run_in_executor(
                    None, func, wrapper)
                consecutive_failures = 0  # Reset on success
            except asyncio.CancelledError:
                raise
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

    # --- Interval job management (thread-safe entry points) ---

    def _in_loop_thread(self):
        return self._loop_thread_id is not None and threading.get_ident() == self._loop_thread_id

    def _call_in_loop(self, fn, *args):
        loop = self._loop
        if loop is None or not loop.is_running():
            return False
        if self._in_loop_thread():
            fn(*args)
        else:
            loop.call_soon_threadsafe(fn, *args)
        return True

    def start_interval_jobs(self, plugin_name=None):
        """Start interval jobs (all, or one plugin's) if we are connected.

        Safe to call from any thread; a no-op before the bot is running.
        Jobs that are already running are not started twice.
        """
        self._call_in_loop(self._start_interval_jobs_now, plugin_name)

    def _start_interval_jobs_now(self, plugin_name=None):
        if not self.dispatcher or not self._running or not self._connected:
            return
        with self._interval_lock:
            for iv, func, pname in self.dispatcher.get_interval_jobs():
                if plugin_name is not None and pname != plugin_name:
                    continue
                entries = self._interval_tasks.setdefault(pname, [])
                if any(e_func is func and e_iv == iv and not task.done()
                       for e_iv, e_func, task in entries):
                    continue
                task = asyncio.create_task(self._interval_runner(iv, func, pname))
                entries.append((iv, func, task))

    def cancel_interval_jobs(self, plugin_name=None):
        """Cancel interval jobs (all, or one plugin's). Safe from any thread."""
        with self._interval_lock:
            if plugin_name is None:
                entries = [e for lst in self._interval_tasks.values() for e in lst]
                self._interval_tasks.clear()
            else:
                entries = self._interval_tasks.pop(plugin_name, [])
        tasks = [task for _, _, task in entries if not task.done()]
        if not tasks:
            return
        loop = self._loop
        if loop is not None and loop.is_running() and not self._in_loop_thread():
            for task in tasks:
                loop.call_soon_threadsafe(task.cancel)
        else:
            for task in tasks:
                task.cancel()

    # --- Connection lifecycle ---

    def _reset_connection_state(self):
        """Forget all per-connection state before (re)connecting."""
        with self._state_lock:
            dict.clear(self.channels)
            dict.clear(self.users)
        self._enabled_caps.clear()
        self._cap_available = set()
        self._cap_ls_buffer = set()
        self._cap_pending = 0
        self._cap_negotiating = False
        self._sasl_in_progress = False
        self._sasl_started = False
        self._registered = False
        self._connected = False
        self._quitting = False
        self.isupport = {}
        self._prefix_modes = dict(DEFAULT_PREFIX_MODES)
        self._chanmodes = DEFAULT_CHANMODES
        self._nicklen = None
        self._nick_attempts = 0
        self._pending_joins = set()
        self._cancel_all_join_retries()
        # Drop anything queued for the old connection
        try:
            while True:
                self._send_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        self._flood_tokens = self._flood_burst
        self._last_refill = time.time()
        if self.nick != self._desired_nick:
            self.nick = self._desired_nick
            self._refresh_nick_patterns()

    def _teardown_connection_tasks(self):
        self.cancel_interval_jobs()
        self._cancel_all_join_retries()
        for task in list(self._conn_tasks):
            if not task.done():
                task.cancel()
        self._conn_tasks.clear()

    async def _close_connection(self):
        """Close the socket (bounded wait so a dead peer can't hang us)."""
        writer = self._writer
        if not writer:
            return
        try:
            writer.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=WAIT_CLOSED_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass

    async def run(self):
        """Main run loop with auto-reconnect."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()

        # Handle graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._signal_shutdown(s)))
            except (NotImplementedError, RuntimeError):
                pass

        while self._running:
            send_task = None
            read_task = None
            try:
                self._reset_connection_state()
                await self.connect()
                await self.register()

                # Start send loop and read loop
                send_task = asyncio.create_task(self._send_loop())
                read_task = asyncio.create_task(self._read_loop())

                # Start interval jobs
                self._start_interval_jobs_now()

                # Wait for the read task to finish (disconnect or stop)
                await asyncio.wait([read_task])

            except asyncio.CancelledError:
                self._running = False
            except Exception:
                if self._running:
                    LOGGER.exception("Connection error")
            finally:
                self._connected = False
                if send_task is not None:
                    send_task.cancel()
                if read_task is not None and not read_task.done():
                    read_task.cancel()
                self._teardown_connection_tasks()
                # Ensure connection is closed
                await self._close_connection()

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

    # --- Quit / restart (thread-safe) ---

    def quit(self, message=None):
        """Send QUIT and stop the bot (no reconnect). Safe from any thread."""
        self._quitting = True
        loop = self._loop
        if loop is None or not loop.is_running():
            self._running = False
            return
        fut = asyncio.run_coroutine_threadsafe(self._do_quit(message), loop)
        if not self._in_loop_thread():
            try:
                fut.result(timeout=QUIT_TIMEOUT + WAIT_CLOSED_TIMEOUT + 3)
            except Exception:
                pass

    def restart(self, message=None):
        """Quit, then re-exec the bot process (handled in __main__)."""
        self._restart_requested = True
        self.quit(message or 'Restarting')

    async def _do_quit(self, message):
        self._running = False
        line = f'QUIT :{message}' if message else 'QUIT'
        if self._writer:
            try:
                await asyncio.wait_for(self._send_raw(line), timeout=5)
            except Exception:
                pass
            # Give the server a moment to close the link cleanly
            loop = asyncio.get_running_loop()
            deadline = loop.time() + QUIT_TIMEOUT
            while self._connected and loop.time() < deadline:
                await asyncio.sleep(0.1)
            await self._close_connection()

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
        await self._close_connection()
        self.db.close()
        LOGGER.info("Bot shut down.")
