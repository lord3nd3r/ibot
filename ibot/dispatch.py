"""Message dispatcher for ibot.

Handles matching incoming IRC messages against registered plugin handlers
(commands, rules, events) and dispatching to the appropriate callables.
"""

import logging
import queue
import re
import threading
import time as time_mod
from typing import Optional, List, Tuple, Pattern

from ibot.sopel_shim.trigger import PreTrigger, Trigger
from ibot.sopel_shim.bot import SopelWrapper
from ibot.sopel_shim.plugin import NOLIMIT

LOGGER = logging.getLogger(__name__)

# Rate limiting constants (already defined in RateLimitTracker)
# Dispatcher constants
MAX_COMMAND_LENGTH = 100  # Maximum command name length
MAX_RULE_PATTERN_LENGTH = 500  # Maximum regex pattern length

# Sopel priority ordering (lower runs first)
_PRIORITY_RANK = {
    'high': 0,
    'medium': 1,
    'low': 2,
}


def _handler_priority(func):
    return _PRIORITY_RANK.get(
        getattr(func, '_priority', 'medium') or 'medium', 1)


class _Handler(tuple):
    """A ``(compiled, func, plugin_name)`` tuple that also remembers its source.

    Behaves exactly like a plain 3-tuple (plugins unpack these), but keeps the
    original pattern text so patterns using ``$nick`` can be recompiled when
    the bot's nick changes.
    """

    def __new__(cls, compiled, func, plugin_name, raw=None, kind=None):
        obj = super().__new__(cls, (compiled, func, plugin_name))
        obj.raw = raw
        obj.kind = kind
        return obj


def _rule_flags(pattern):
    """Sopel compiles rules case-insensitively (VERBOSE if multi-line)."""
    flags = re.IGNORECASE
    if '\n' in pattern:
        flags |= re.VERBOSE
    return flags


class HandlerPool:
    """Bounded pool of daemon worker threads for plugin handlers.

    Replaces one-thread-per-message. Workers are spawned lazily up to
    ``max_workers``; extra work waits in a bounded queue. If the queue is
    full the job is dropped (with a rate-limited warning) instead of letting
    the process run out of threads/memory. Workers are daemon threads so a
    hung handler can never block shutdown.
    """

    def __init__(self, max_workers=64, max_queue=10000):
        self.max_workers = max(1, int(max_workers or 64))
        self._queue = queue.Queue(maxsize=max(1, int(max_queue or 10000)))
        self._lock = threading.Lock()
        self._workers = 0
        self._idle = 0
        self._shutdown = False
        self._last_drop_warning = 0.0
        self._dropped = 0

    def submit(self, fn):
        if self._shutdown:
            return False
        with self._lock:
            need_worker = self._idle == 0 and self._workers < self.max_workers
            if need_worker:
                self._workers += 1
        if need_worker:
            try:
                t = threading.Thread(target=self._worker, daemon=True,
                                     name=f'ibot-handler-{self._workers}')
                t.start()
            except RuntimeError:
                with self._lock:
                    self._workers -= 1
                LOGGER.exception("Could not start handler worker thread")
        try:
            self._queue.put_nowait(fn)
            return True
        except queue.Full:
            self._dropped += 1
            now = time_mod.time()
            if now - self._last_drop_warning > 30:
                self._last_drop_warning = now
                LOGGER.warning("Handler queue full (%d workers busy); dropped "
                               "%d job(s) so far", self._workers, self._dropped)
            return False

    def _worker(self):
        while True:
            with self._lock:
                self._idle += 1
            try:
                fn = self._queue.get()
            finally:
                with self._lock:
                    self._idle -= 1
            if fn is None:
                with self._lock:
                    self._workers -= 1
                return
            try:
                fn()
            except Exception:
                LOGGER.exception("Unhandled exception in handler worker")

    def shutdown(self):
        """Stop accepting work and let idle workers exit (does not wait)."""
        self._shutdown = True
        with self._lock:
            n = self._workers
        for _ in range(n):
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                break

    @property
    def stats(self):
        return {'workers': self._workers, 'idle': self._idle,
                'queued': self._queue.qsize(), 'dropped': self._dropped}


class RateLimitTracker:
    """Tracks rate limit timestamps per user/channel/global."""

    CLEANUP_INTERVAL = 300  # Clean up old entries every 5 minutes
    ENTRY_MAX_AGE = 3600    # Remove entries older than 1 hour

    def __init__(self):
        self._user_times = {}    # {func_id: {nick: last_time}}
        self._channel_times = {} # {func_id: {channel: last_time}}
        self._global_times = {}  # {func_id: last_time}
        self._lock = threading.Lock()
        self._last_cleanup = time_mod.time()

    def check(self, func, nick, channel, is_admin):
        """Check if a function call is rate-limited.

        Returns True if the call should be blocked.
        """
        if not getattr(func, '_rate_limit_admins', False) and is_admin:
            return False

        func_id = id(func)
        now = time_mod.time()

        with self._lock:
            # User rate limit
            user_rate = getattr(func, '_rate_user', 0)
            if user_rate > 0:
                user_times = self._user_times.setdefault(func_id, {})
                last = user_times.get(nick, 0)
                if now - last < user_rate:
                    return True

            # Channel rate limit
            channel_rate = getattr(func, '_rate_channel', 0)
            if channel_rate > 0 and channel:
                chan_times = self._channel_times.setdefault(func_id, {})
                last = chan_times.get(channel, 0)
                if now - last < channel_rate:
                    return True

            # Global rate limit
            global_rate = getattr(func, '_rate_global', 0)
            if global_rate > 0:
                last = self._global_times.get(func_id, 0)
                if now - last < global_rate:
                    return True

        return False

    def check_and_record(self, func, nick, channel, is_admin):
        """Atomically check the rate limit and, if allowed, record the call.

        Recording at check time (under the lock) means several messages
        arriving at once can't all slip past the limit before the first
        handler finishes.

        Returns ``(blocked, token)``. Pass ``token`` to :meth:`restore` if the
        handler returns NOLIMIT, to undo the recorded timestamp.
        """
        if not getattr(func, '_rate_limit_admins', False) and is_admin:
            # Admins bypass the check, but the call still counts (as before)
            return False, self._record(func, nick, channel)

        func_id = id(func)
        now = time_mod.time()
        with self._lock:
            user_rate = getattr(func, '_rate_user', 0)
            if user_rate > 0:
                last = self._user_times.get(func_id, {}).get(nick, 0)
                if now - last < user_rate:
                    return True, None
            channel_rate = getattr(func, '_rate_channel', 0)
            if channel_rate > 0 and channel:
                last = self._channel_times.get(func_id, {}).get(channel, 0)
                if now - last < channel_rate:
                    return True, None
            global_rate = getattr(func, '_rate_global', 0)
            if global_rate > 0:
                last = self._global_times.get(func_id, 0)
                if now - last < global_rate:
                    return True, None
            return False, self._record_locked(func_id, nick, channel, now)

    def _record(self, func, nick, channel):
        with self._lock:
            return self._record_locked(id(func), nick, channel, time_mod.time())

    _MISSING = object()

    def _record_locked(self, func_id, nick, channel, now):
        user_times = self._user_times.setdefault(func_id, {})
        prev = (func_id, nick, channel, now,
                user_times.get(nick, self._MISSING),
                self._channel_times.get(func_id, {}).get(channel, self._MISSING)
                if channel else self._MISSING,
                self._global_times.get(func_id, self._MISSING))
        user_times[nick] = now
        if channel:
            self._channel_times.setdefault(func_id, {})[channel] = now
        self._global_times[func_id] = now
        if now - self._last_cleanup > self.CLEANUP_INTERVAL:
            self._cleanup_old_entries(now)
            self._last_cleanup = now
        return prev

    def restore(self, token):
        """Undo a recorded call (handler returned NOLIMIT)."""
        if not token:
            return
        func_id, nick, channel, stamp, p_user, p_chan, p_glob = token
        missing = self._MISSING
        with self._lock:
            # Only roll back if nobody recorded a newer call meanwhile
            ut = self._user_times.get(func_id)
            if ut is not None and ut.get(nick) == stamp:
                if p_user is missing:
                    ut.pop(nick, None)
                else:
                    ut[nick] = p_user
            if channel:
                ct = self._channel_times.get(func_id)
                if ct is not None and ct.get(channel) == stamp:
                    if p_chan is missing:
                        ct.pop(channel, None)
                    else:
                        ct[channel] = p_chan
            if self._global_times.get(func_id) == stamp:
                if p_glob is missing:
                    self._global_times.pop(func_id, None)
                else:
                    self._global_times[func_id] = p_glob

    def update(self, func, nick, channel):
        """Record that a function was just called."""
        func_id = id(func)
        now = time_mod.time()
        with self._lock:
            self._user_times.setdefault(func_id, {})[nick] = now
            if channel:
                self._channel_times.setdefault(func_id, {})[channel] = now
            self._global_times[func_id] = now
            
            # Periodic cleanup
            if now - self._last_cleanup > self.CLEANUP_INTERVAL:
                self._cleanup_old_entries(now)
                self._last_cleanup = now

    def _cleanup_old_entries(self, now):
        """Remove entries older than ENTRY_MAX_AGE (must be called with lock held)."""
        cutoff = now - self.ENTRY_MAX_AGE
        
        # Clean user times
        for func_id in list(self._user_times.keys()):
            user_dict = self._user_times[func_id]
            for nick in list(user_dict.keys()):
                if user_dict[nick] < cutoff:
                    del user_dict[nick]
            if not user_dict:
                del self._user_times[func_id]
        
        # Clean channel times
        for func_id in list(self._channel_times.keys()):
            chan_dict = self._channel_times[func_id]
            for channel in list(chan_dict.keys()):
                if chan_dict[channel] < cutoff:
                    del chan_dict[channel]
            if not chan_dict:
                del self._channel_times[func_id]
        
        # Clean global times
        for func_id in list(self._global_times.keys()):
            if self._global_times[func_id] < cutoff:
                del self._global_times[func_id]


class Dispatcher:
    """Matches incoming IRC messages to plugin handlers and dispatches them."""

    def __init__(self, bot_core, settings):
        self.bot = bot_core
        self.settings = settings
        self.plugins = []
        self._rate_limiter = RateLimitTracker()
        self._ignore_nicks = set()
        self._ignore_hostmasks = []  # compiled regexes
        self._channel_disabled = {}  # {channel_lower: set(plugins) / {'*'}}
        self._rebuild_ignore_lists()
        self._compiled_nick = getattr(bot_core, 'nick', None)
        core = settings.core
        self.pool = HandlerPool(
            getattr(core, 'handler_threads', 64) or 64,
            getattr(core, 'handler_queue_size', 10000) or 10000)

        # Compiled command patterns: [(compiled_regex, func, plugin_name)]
        self._command_handlers = []
        # Compiled rule patterns: [(compiled_regex, func, plugin_name)]
        self._rule_handlers = []
        # Event handlers: {event_name: [(func, plugin_name)]}
        self._event_handlers = {}
        # Nickname command patterns
        self._nick_command_handlers = []
        # Action command patterns
        self._action_command_handlers = []
        # Find rule patterns
        self._find_handlers = []
        # Search rule patterns
        self._search_handlers = []
        # CTCP handlers: {ctcp_command: [(func, plugin_name)]}
        self._ctcp_handlers = {}
        # URL callbacks
        self._url_handlers = []
        # Interval jobs
        self._interval_jobs = []

    def _rebuild_ignore_lists(self):
        """Compile nick_blocks / host_blocks from config."""
        from ibot.sopel_shim.tools import get_hostmask_regex, Identifier
        core = self.settings.core
        self._ignore_nicks = {
            Identifier(n).lower() for n in (core.nick_blocks or [])
        }
        self._ignore_hostmasks = []
        for mask in (core.host_blocks or []):
            try:
                self._ignore_hostmasks.append(get_hostmask_regex(mask))
            except re.error:
                LOGGER.error("Bad host_blocks pattern: %s", mask)
        self._load_channel_disables()

    def _load_channel_disables(self):
        """Read ``disable_plugins`` from ``[#channel]`` config sections."""
        disabled = {}
        parser = getattr(self.settings, 'parser', None)
        if parser is None:
            self._channel_disabled = disabled
            return
        try:
            for section in parser.sections():
                if not section.startswith(('#', '&')):
                    continue
                try:
                    raw = parser.get(section, 'disable_plugins', fallback=None)
                except Exception:
                    raw = None
                if not raw:
                    continue
                names = {p.strip().lower() for p in raw.split(',') if p.strip()}
                if names:
                    disabled[section.lower()] = names
        except Exception:
            LOGGER.exception("Failed to read per-channel disable_plugins")
        self._channel_disabled = disabled
        if disabled:
            LOGGER.info("Per-channel disable_plugins from config: %s",
                        ', '.join(f'{c}={",".join(sorted(v))}'
                                  for c, v in sorted(disabled.items())))

    def _is_ignored(self, pretrigger):
        """True if the sender is on the ignore list."""
        from ibot.sopel_shim.tools import Identifier
        nick = Identifier(pretrigger.nick).lower()
        if nick in self._ignore_nicks:
            return True
        hostmask = pretrigger.hostmask or ''
        for regex in self._ignore_hostmasks:
            if regex.match(hostmask):
                return True
        return False

    def _is_bot_user(self, pretrigger):
        """Best-effort bot detection (message tag or tracked User.is_bot)."""
        tags = pretrigger.tags or {}
        if 'bot' in tags:
            return True
        if hasattr(self.bot, 'users'):
            user = self.bot.users.get(pretrigger.nick)
            if user is not None and getattr(user, 'is_bot', False):
                return True
        return False

    def _sort_handlers(self):
        """Sort list-style handlers by Sopel priority (high → medium → low)."""
        def key3(item):
            # (compiled, func, plugin) or (interval, func, plugin)
            return (_handler_priority(item[1]), item[2], getattr(item[1], '__name__', ''))

        def key2(item):
            # (func, plugin)
            return (_handler_priority(item[0]), item[1], getattr(item[0], '__name__', ''))

        # Build sorted copies and swap them in, instead of sorting in place:
        # list.sort() leaves the list empty while it runs, which a dispatch
        # on the event-loop thread could observe during a live reload.
        self._command_handlers = sorted(self._command_handlers, key=key3)
        self._rule_handlers = sorted(self._rule_handlers, key=key3)
        self._nick_command_handlers = sorted(self._nick_command_handlers, key=key3)
        self._action_command_handlers = sorted(self._action_command_handlers, key=key3)
        self._find_handlers = sorted(self._find_handlers, key=key3)
        self._search_handlers = sorted(self._search_handlers, key=key3)
        self._url_handlers = sorted(self._url_handlers, key=key3)
        for evt in list(self._event_handlers):
            self._event_handlers[evt] = sorted(self._event_handlers[evt], key=key2)
        for ctcp in list(self._ctcp_handlers):
            self._ctcp_handlers[ctcp] = sorted(self._ctcp_handlers[ctcp], key=key2)

    def clear(self):
        """Clear all registered handlers (for rehash/full reload)."""
        self._command_handlers.clear()
        self._rule_handlers.clear()
        self._event_handlers.clear()
        self._nick_command_handlers.clear()
        self._action_command_handlers.clear()
        self._find_handlers.clear()
        self._search_handlers.clear()
        self._ctcp_handlers.clear()
        self._url_handlers.clear()
        self._interval_jobs.clear()
        self.plugins.clear()
        cancel = getattr(self.bot, 'cancel_interval_jobs', None)
        if cancel is not None:
            try:
                cancel()
            except Exception:
                LOGGER.exception("Failed to cancel interval jobs")

    def unregister_plugin(self, plugin_name):
        """Remove all handlers belonging to a specific plugin."""
        self._command_handlers = [
            h for h in self._command_handlers if h[2] != plugin_name]
        self._rule_handlers = [
            h for h in self._rule_handlers if h[2] != plugin_name]
        self._nick_command_handlers = [
            h for h in self._nick_command_handlers if h[2] != plugin_name]
        self._action_command_handlers = [
            h for h in self._action_command_handlers if h[2] != plugin_name]
        self._find_handlers = [
            h for h in self._find_handlers if h[2] != plugin_name]
        self._search_handlers = [
            h for h in self._search_handlers if h[2] != plugin_name]
        self._url_handlers = [
            h for h in self._url_handlers if h[2] != plugin_name]
        self._interval_jobs = [
            h for h in self._interval_jobs if h[2] != plugin_name]
        for evt in list(self._event_handlers):
            self._event_handlers[evt] = [
                h for h in self._event_handlers[evt] if h[1] != plugin_name]
            if not self._event_handlers[evt]:
                del self._event_handlers[evt]
        for ctcp_cmd in list(self._ctcp_handlers):
            self._ctcp_handlers[ctcp_cmd] = [
                h for h in self._ctcp_handlers[ctcp_cmd] if h[1] != plugin_name]
            if not self._ctcp_handlers[ctcp_cmd]:
                del self._ctcp_handlers[ctcp_cmd]
        self.plugins = [p for p in self.plugins if p.name != plugin_name]
        cancel = getattr(self.bot, 'cancel_interval_jobs', None)
        if cancel is not None:
            try:
                cancel(plugin_name)
            except Exception:
                LOGGER.exception("Failed to cancel interval jobs for %s",
                                 plugin_name)

    def _resolve_patterns(self, func, static_attr, lazy_attr):
        """Collect static patterns plus any produced by lazy loaders.

        Sopel's ``*_lazy`` decorators register loader callables that are
        evaluated at registration time with the bot settings and return a
        list of (usually compiled) patterns.
        """
        patterns = list(getattr(func, static_attr, []) or [])
        for loader in getattr(func, lazy_attr, []) or []:
            try:
                loaded = loader(self.settings)
                if loaded:
                    patterns.extend(loaded)
            except Exception:
                LOGGER.exception(
                    "Lazy loader failed for %s in plugin function %s",
                    lazy_attr, getattr(func, '__name__', '?'))
        return patterns

    def _compile_rule(self, pattern):
        """Compile a string rule the way Sopel does.

        ``$nickname`` becomes the bot's nick, ``$nick`` the nick followed by
        ``:``/``,``/space (``$nickname`` must be replaced first, otherwise
        ``$nick`` would eat its prefix). Case-insensitive like Sopel.
        """
        nick = re.escape(self.bot.nick)
        pattern = pattern.replace('$nickname', nick)
        pattern = pattern.replace('$nick', nick + r'[:,\s]\s*')
        return re.compile(pattern, _rule_flags(pattern))

    def _compile_nick_command(self, cmd):
        nick = re.escape(self.bot.nick)
        pattern = (
            r'^' + nick + r'[:,\s]\s*'
            r'(' + re.escape(cmd) + r')'
            r'(?:\s+(.*))?$'
        )
        return re.compile(pattern, re.IGNORECASE)

    def refresh_nick_patterns(self):
        """Recompile ``$nick`` rules and nick commands after a nick change."""
        nick = getattr(self.bot, 'nick', None)
        if not nick or nick == self._compiled_nick:
            return

        def rebuild(handlers):
            out = []
            for h in handlers:
                kind = getattr(h, 'kind', None)
                raw = getattr(h, 'raw', None)
                if raw is None or kind is None:
                    out.append(h)
                    continue
                try:
                    if kind == 'rule':
                        compiled = self._compile_rule(raw)
                    else:
                        compiled = self._compile_nick_command(raw)
                    out.append(_Handler(compiled, h[1], h[2], raw, kind))
                except re.error:
                    out.append(h)
            return out

        self._rule_handlers = rebuild(self._rule_handlers)
        self._nick_command_handlers = rebuild(self._nick_command_handlers)
        self._compiled_nick = nick
        LOGGER.info("Recompiled nick-based patterns for nick %s", nick)

    def register_plugins(self, plugins):
        """Register all loaded plugins with the dispatcher."""
        self.plugins.extend(plugins)
        prefix = self.settings.core.prefix

        for plugin in plugins:
            plugin_name = plugin.name

            # Register command handlers
            for func in plugin.commands:
                for cmd in func._commands:
                    # Build regex: prefix + command + optional args
                    escaped_cmd = re.escape(cmd)
                    pattern = (
                        r'^' + prefix +
                        r'(' + escaped_cmd + r')'
                        r'(?:\s+(.*))?$'
                    )
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                        self._command_handlers.append(
                            (compiled, func, plugin_name))
                    except re.error:
                        LOGGER.error("Bad command pattern for %s: %s",
                                     cmd, pattern)

            # Register rule handlers
            for func in plugin.rules:
                for pattern in self._resolve_patterns(
                        func, '_rules', '_rules_lazy_loaders'):
                    try:
                        if isinstance(pattern, str):
                            raw = pattern if '$nick' in pattern else None
                            compiled = self._compile_rule(pattern)
                        else:
                            raw = None
                            compiled = pattern
                        self._rule_handlers.append(
                            _Handler(compiled, func, plugin_name, raw, 'rule'))
                    except re.error:
                        LOGGER.error("Bad rule pattern in %s: %s",
                                     plugin_name, pattern)

            # Register event handlers
            for func in plugin.events:
                for evt in func._events:
                    evt_upper = evt.upper()
                    self._event_handlers.setdefault(
                        evt_upper, []).append((func, plugin_name))

            # Register nickname command handlers
            for func in plugin.nick_commands:
                for cmd in func._nickname_commands:
                    try:
                        compiled = self._compile_nick_command(cmd)
                        self._nick_command_handlers.append(
                            _Handler(compiled, func, plugin_name, cmd, 'nickcmd'))
                    except re.error:
                        LOGGER.error("Bad nick command pattern: %s", cmd)

            # Register action command handlers
            for func in plugin.action_commands:
                for cmd in func._action_commands:
                    escaped_cmd = re.escape(cmd)
                    pattern = (
                        r'^(' + escaped_cmd + r')'
                        r'(?:\s+(.*))?$'
                    )
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                        self._action_command_handlers.append(
                            (compiled, func, plugin_name))
                    except re.error:
                        LOGGER.error("Bad action command pattern: %s", cmd)

            # Register find rules
            for func in plugin.find_rules:
                for pattern in self._resolve_patterns(
                        func, '_find_rules', '_find_rules_lazy_loaders'):
                    try:
                        if isinstance(pattern, str):
                            compiled = re.compile(pattern, _rule_flags(pattern))
                        else:
                            compiled = pattern
                        self._find_handlers.append(
                            (compiled, func, plugin_name))
                    except re.error:
                        LOGGER.error("Bad find pattern in %s", plugin_name)

            # Register search rules
            for func in plugin.search_rules:
                for pattern in self._resolve_patterns(
                        func, '_search_rules', '_search_rules_lazy_loaders'):
                    try:
                        if isinstance(pattern, str):
                            compiled = re.compile(pattern, _rule_flags(pattern))
                        else:
                            compiled = pattern
                        self._search_handlers.append(
                            (compiled, func, plugin_name))
                    except re.error:
                        LOGGER.error("Bad search pattern in %s", plugin_name)

            # Register CTCP handlers
            for func in plugin.ctcp_handlers:
                for ctcp_cmd in func._ctcp:
                    self._ctcp_handlers.setdefault(
                        ctcp_cmd.upper(), []).append((func, plugin_name))

            # Register URL callbacks
            for func in plugin.url_callbacks:
                for pattern in self._resolve_patterns(
                        func, '_url_regex', '_url_lazy_loaders'):
                    try:
                        if isinstance(pattern, str):
                            compiled = re.compile(pattern, _rule_flags(pattern))
                        else:
                            compiled = pattern
                        self._url_handlers.append(
                            (compiled, func, plugin_name))
                    except re.error:
                        LOGGER.error("Bad URL pattern in %s", plugin_name)

            # Collect interval jobs
            for func in plugin.intervals:
                for iv in func._intervals:
                    self._interval_jobs.append((iv, func, plugin_name))

        self._sort_handlers()
        self._compiled_nick = getattr(self.bot, 'nick', None)

        # Start interval jobs for these plugins if we're already connected
        # (no-op at startup; the bot starts all jobs once connected)
        start = getattr(self.bot, 'start_interval_jobs', None)
        if start is not None:
            for plugin in plugins:
                if plugin.intervals:
                    try:
                        start(plugin.name)
                    except Exception:
                        LOGGER.exception("Failed to start interval jobs for %s",
                                         plugin.name)

        total_commands = len(self._command_handlers)
        total_rules = len(self._rule_handlers)
        total_events = sum(len(v) for v in self._event_handlers.values())
        LOGGER.info("Registered %d commands, %d rules, %d event handlers",
                     total_commands, total_rules, total_events)

    def dispatch(self, line):
        """Parse an IRC line and dispatch to matching handlers.

        This is the main entry point called by the IRC client for each
        incoming message.
        """
        try:
            pretrigger = PreTrigger(self.bot.nick, line)
        except Exception:
            LOGGER.exception("Failed to parse IRC line: %s", line)
            return

        event = pretrigger.event

        # Dispatch to event handlers first
        event_handlers = self._event_handlers.get(event)
        if event_handlers:
            for func, plugin_name in list(event_handlers):
                self._dispatch_to_func(
                    func, pretrigger, plugin_name, event_match=True)

        # PRIVMSG handling
        if event == 'PRIVMSG':
            text = pretrigger.text
            is_ctcp = pretrigger.ctcp is not None

            if is_ctcp:
                # Handle CTCP (including ACTION)
                ctcp_cmd = pretrigger.ctcp.upper()
                ctcp_handlers = self._ctcp_handlers.get(ctcp_cmd)
                if ctcp_handlers:
                    for func, pname in list(ctcp_handlers):
                        # If handler has rules, check them against the CTCP text
                        if hasattr(func, '_rules') and func._rules:
                            ctcp_text = pretrigger.args[-1] if pretrigger.args else ''
                            matched = False
                            for rule_pattern in func._rules:
                                try:
                                    if isinstance(rule_pattern, str):
                                        compiled = re.compile(
                                            rule_pattern, _rule_flags(rule_pattern))
                                    else:
                                        compiled = rule_pattern
                                    match = compiled.match(ctcp_text)
                                    if match:
                                        self._dispatch_to_func(
                                            func, pretrigger, pname, match=match)
                                        matched = True
                                        break
                                except (re.error, TypeError):
                                    LOGGER.error("Bad rule pattern in CTCP handler: %s", rule_pattern)
                            # If no rules matched, skip this handler
                        else:
                            # No rules, dispatch unconditionally
                            self._dispatch_to_func(
                                func, pretrigger, pname, event_match=True)

                # Handle action commands
                if ctcp_cmd == 'ACTION':
                    action_text = pretrigger.args[-1] if pretrigger.args else ''
                    for compiled, func, pname in list(self._action_command_handlers):
                        match = compiled.match(action_text)
                        if match:
                            self._dispatch_to_func(
                                func, pretrigger, pname, match=match)
            else:
                # Try command handlers
                for compiled, func, pname in list(self._command_handlers):
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)
                        return

                # Try nickname command handlers
                for compiled, func, pname in list(self._nick_command_handlers):
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try rule handlers
                for compiled, func, pname in list(self._rule_handlers):
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try find handlers (match multiple times)
                for compiled, func, pname in list(self._find_handlers):
                    for match in compiled.finditer(text):
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try search handlers (first match only)
                for compiled, func, pname in list(self._search_handlers):
                    match = compiled.search(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try URL callbacks
                if pretrigger.urls:
                    url_handlers = list(self._url_handlers)
                    for url in pretrigger.urls:
                        for compiled, func, pname in url_handlers:
                            match = compiled.search(url)
                            if match:
                                self._dispatch_to_func(
                                    func, pretrigger, pname, match=match)

    def _dispatch_to_func(self, func, pretrigger, plugin_name,
                          match=None, event_match=False):
        """Create Trigger and SopelWrapper, then call the function."""
        if match is None and event_match:
            match = re.match(r'(.*)', pretrigger.text or '')

        if match is None:
            return

        # Echo filter: skip the bot's own messages unless @echo
        bot_nick = getattr(self.bot, 'nick', None)
        if bot_nick and str(pretrigger.nick).lower() == str(bot_nick).lower():
            if not getattr(func, '_allow_echo', False):
                return

        # Ignore list (unless @unblockable)
        if not getattr(func, '_unblockable', False):
            if self._is_ignored(pretrigger):
                return

        # Other bots (unless @allow_bots)
        if not getattr(func, '_allow_bots', False):
            if self._is_bot_user(pretrigger):
                return

        # Check if this plugin is disabled in this channel
        channel = pretrigger.sender
        if channel and str(channel).startswith(('#', '&')):
            if self._is_plugin_disabled(channel, plugin_name):
                return

        # Prefer account-tag / extended-join tag; fall back to tracked User.account
        account = pretrigger.tags.get('account') if pretrigger.tags else None
        if not account and hasattr(self.bot, 'get_user_account'):
            account = self.bot.get_user_account(pretrigger.nick)
        elif not account and hasattr(self.bot, 'users'):
            user = self.bot.users.get(pretrigger.nick)
            if user is not None:
                account = getattr(user, 'account', None)

        # Keep tracked state warm from account-tag
        if account and hasattr(self.bot, '_track_account'):
            try:
                self.bot._track_account(pretrigger.nick, account)
            except Exception:
                pass
        # Bot tag on message
        if pretrigger.tags and 'bot' in pretrigger.tags and hasattr(self.bot, 'users'):
            user = self.bot.users.get(pretrigger.nick)
            if user is not None:
                user.is_bot = True

        trigger = Trigger(self.settings, pretrigger, match, account=account)

        # Check predicates (require_admin, require_chanmsg, etc.)
        wrapper = SopelWrapper(self.bot, trigger)
        wrapper._output_prefix = getattr(func, '_output_prefix', '')

        for predicate in getattr(func, '_predicates', []):
            try:
                if not predicate(wrapper, trigger):
                    return
            except Exception:
                LOGGER.exception("Predicate check failed in plugin %s, function %s",
                                 plugin_name, func.__name__)
                return

        # Check rate limits
        nick = str(trigger.nick).lower()
        channel = str(trigger.sender).lower() if trigger.sender else None
        is_admin = trigger.admin

        blocked, rl_token = self._rate_limiter.check_and_record(
            func, nick, channel, is_admin)
        if blocked:
            msg = getattr(func, '_rate_message', None)
            if msg:
                wrapper.notice(msg, destination=str(trigger.nick))
            return

        # Execute
        threaded = getattr(func, '_threaded', True)

        def _run():
            try:
                result = func(wrapper, trigger)
                # A handler returning NOLIMIT opts out of rate-limit accounting
                # for this invocation (Sopel semantics).
                if result == NOLIMIT:
                    self._rate_limiter.restore(rl_token)
            except Exception:
                LOGGER.exception("Unhandled exception in plugin '%s', function '%s', triggered by %s in %s",
                                 plugin_name, func.__name__, trigger.nick, trigger.sender or 'PM')

        if threaded:
            self.pool.submit(_run)
        else:
            _run()

    def _is_plugin_disabled(self, channel, plugin_name):
        """Check if a plugin is disabled in a channel via memory cache."""
        # The admin plugin can never be disabled
        if plugin_name == 'admin':
            return False
        channel_lower = channel.lower()
        cfg = self._channel_disabled.get(channel_lower)
        if cfg and ('*' in cfg or plugin_name.lower() in cfg):
            return True
        disabled = self.bot.memory.get('disabled_plugins', {})
        if channel_lower in disabled:
            return plugin_name.lower() in disabled[channel_lower]
        return False

    def load_disabled_commands(self):
        """Load disabled plugins per channel from the DB into bot.memory cache."""
        disabled = {}
        try:
            from ibot.sopel_shim.db import ChannelValues
            from sqlalchemy.sql import select
            import json
            with self.bot.db.session() as session:
                results = session.execute(
                    select(ChannelValues)
                    .where(ChannelValues.key == 'disabled_plugins')
                ).scalars()
                for row in results:
                    try:
                        plugins = json.loads(row.value)
                        if isinstance(plugins, list):
                            disabled[row.channel.lower()] = set(
                                p.lower() for p in plugins)
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception:
            LOGGER.exception("Failed to load disabled plugins from DB")
        self.bot.memory['disabled_plugins'] = disabled
        LOGGER.info("Loaded disabled plugins for %d channels", len(disabled))

    def get_interval_jobs(self):
        """Return list of (interval_seconds, func, plugin_name) tuples."""
        return list(self._interval_jobs)
