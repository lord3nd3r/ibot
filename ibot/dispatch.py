"""Message dispatcher for ibot.

Handles matching incoming IRC messages against registered plugin handlers
(commands, rules, events) and dispatching to the appropriate callables.
"""

import logging
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
                            # Replace $nick and $nickname
                            nick = re.escape(self.bot.nick)
                            pattern = pattern.replace(
                                '$nick', nick + r'[:,\s]\s*')
                            pattern = pattern.replace('$nickname', nick)
                            compiled = re.compile(pattern)
                        else:
                            compiled = pattern
                        self._rule_handlers.append(
                            (compiled, func, plugin_name))
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
                    nick = re.escape(self.bot.nick)
                    escaped_cmd = re.escape(cmd)
                    pattern = (
                        r'^' + nick + r'[:,\s]\s*'
                        r'(' + escaped_cmd + r')'
                        r'(?:\s+(.*))?$'
                    )
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                        self._nick_command_handlers.append(
                            (compiled, func, plugin_name))
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
                            compiled = re.compile(pattern)
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
                            compiled = re.compile(pattern)
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
                            compiled = re.compile(pattern)
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
        if event in self._event_handlers:
            for func, plugin_name in self._event_handlers[event]:
                self._dispatch_to_func(
                    func, pretrigger, plugin_name, event_match=True)

        # PRIVMSG handling
        if event == 'PRIVMSG':
            text = pretrigger.text
            is_ctcp = pretrigger.ctcp is not None

            if is_ctcp:
                # Handle CTCP (including ACTION)
                ctcp_cmd = pretrigger.ctcp.upper()
                if ctcp_cmd in self._ctcp_handlers:
                    for func, pname in self._ctcp_handlers[ctcp_cmd]:
                        # If handler has rules, check them against the CTCP text
                        if hasattr(func, '_rules') and func._rules:
                            ctcp_text = pretrigger.args[-1] if pretrigger.args else ''
                            matched = False
                            for rule_pattern in func._rules:
                                try:
                                    if isinstance(rule_pattern, str):
                                        compiled = re.compile(rule_pattern)
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
                    for compiled, func, pname in self._action_command_handlers:
                        match = compiled.match(action_text)
                        if match:
                            self._dispatch_to_func(
                                func, pretrigger, pname, match=match)
            else:
                # Try command handlers
                for compiled, func, pname in self._command_handlers:
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try nickname command handlers
                for compiled, func, pname in self._nick_command_handlers:
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try rule handlers
                for compiled, func, pname in self._rule_handlers:
                    match = compiled.match(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try find handlers (match multiple times)
                for compiled, func, pname in self._find_handlers:
                    for match in compiled.finditer(text):
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try search handlers (first match only)
                for compiled, func, pname in self._search_handlers:
                    match = compiled.search(text)
                    if match:
                        self._dispatch_to_func(
                            func, pretrigger, pname, match=match)

                # Try URL callbacks
                if pretrigger.urls:
                    for url in pretrigger.urls:
                        for compiled, func, pname in self._url_handlers:
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

        # Check if this plugin is disabled in this channel
        channel = pretrigger.sender
        if channel and channel.startswith(('#', '&')):
            if self._is_plugin_disabled(channel, plugin_name):
                return

        trigger = Trigger(self.settings, pretrigger, match)

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

        if self._rate_limiter.check(func, nick, channel, is_admin):
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
                if result != NOLIMIT:
                    self._rate_limiter.update(func, nick, channel)
            except Exception:
                LOGGER.exception("Unhandled exception in plugin '%s', function '%s', triggered by %s in %s",
                                 plugin_name, func.__name__, trigger.nick, trigger.sender or 'PM')

        if threaded:
            t = threading.Thread(target=_run, daemon=True)
            t.start()
        else:
            _run()

    def _is_plugin_disabled(self, channel, plugin_name):
        """Check if a plugin is disabled in a channel via memory cache."""
        # The admin plugin can never be disabled
        if plugin_name == 'admin':
            return False
        disabled = self.bot.memory.get('disabled_plugins', {})
        channel_lower = channel.lower()
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
