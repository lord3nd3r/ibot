"""Sopel-compatible plugin decorators.

Provides all the decorators and constants that Sopel plugins use:
@plugin.command, @plugin.rule, @plugin.event, @plugin.require_admin, etc.

These decorators work by attaching metadata to function objects, which the
plugin loader reads when registering handlers.
"""

from ibot.sopel_shim.privileges import (
    VOICE, HALFOP, OP, ADMIN, OWNER, OPER,
    AccessLevel,
)


__all__ = [
    'NOLIMIT', 'VOICE', 'HALFOP', 'OP', 'ADMIN', 'OWNER', 'OPER',
    'command', 'commands', 'rule', 'event', 'interval',
    'nickname_command', 'nickname_commands',
    'action_command', 'action_commands',
    'require_admin', 'require_owner', 'require_chanmsg',
    'require_privmsg', 'require_privilege', 'require_bot_privilege',
    'require_account',
    'rate', 'rate_user', 'rate_channel', 'rate_global',
    'thread', 'priority', 'unblockable', 'allow_bots', 'echo',
    'example', 'output_prefix', 'label',
    'url', 'url_lazy',
    'find', 'find_lazy', 'search', 'search_lazy',
    'rule_lazy', 'ctcp',
]

NOLIMIT = 1


def _ensure_attrs(func):
    """Ensure a function has all the plugin metadata attributes."""
    if not hasattr(func, '_ibot_plugin'):
        func._ibot_plugin = True
        func._commands = getattr(func, '_commands', [])
        func._rules = getattr(func, '_rules', [])
        func._events = getattr(func, '_events', [])
        func._nickname_commands = getattr(func, '_nickname_commands', [])
        func._action_commands = getattr(func, '_action_commands', [])
        func._intervals = getattr(func, '_intervals', [])
        func._priority = getattr(func, '_priority', 'medium')
        func._threaded = getattr(func, '_threaded', True)
        func._unblockable = getattr(func, '_unblockable', False)
        func._allow_bots = getattr(func, '_allow_bots', False)
        func._allow_echo = getattr(func, '_allow_echo', False)
        func._rate_user = getattr(func, '_rate_user', 0)
        func._rate_channel = getattr(func, '_rate_channel', 0)
        func._rate_global = getattr(func, '_rate_global', 0)
        func._rate_message = getattr(func, '_rate_message', None)
        func._rate_limit_admins = getattr(func, '_rate_limit_admins', False)
        func._predicates = getattr(func, '_predicates', [])
        func._output_prefix = getattr(func, '_output_prefix', '')
        func._examples = getattr(func, '_examples', [])
        func._label = getattr(func, '_label', None)
        func._ctcp = getattr(func, '_ctcp', [])
        func._url_regex = getattr(func, '_url_regex', [])
        func._url_lazy_loaders = getattr(func, '_url_lazy_loaders', [])
        func._find_rules = getattr(func, '_find_rules', [])
        func._search_rules = getattr(func, '_search_rules', [])
        func._rules_lazy_loaders = getattr(func, '_rules_lazy_loaders', [])
        func._find_rules_lazy_loaders = getattr(func, '_find_rules_lazy_loaders', [])
        func._search_rules_lazy_loaders = getattr(func, '_search_rules_lazy_loaders', [])
        func._is_setup = getattr(func, '_is_setup', False)
        func._is_shutdown = getattr(func, '_is_shutdown', False)
    return func


# --- Trigger decorators ---

def command(*command_list):
    """Decorate a function to be triggered by prefix commands (e.g. .hello)."""
    def decorator(func):
        func = _ensure_attrs(func)
        for cmd in command_list:
            if cmd not in func._commands:
                func._commands.append(cmd)
        return func
    return decorator


commands = command


def rule(*patterns):
    """Decorate a function to be triggered when a message matches a regex pattern."""
    def decorator(func):
        func = _ensure_attrs(func)
        for pattern in patterns:
            if pattern not in func._rules:
                func._rules.append(pattern)
        return func
    return decorator


def rule_lazy(*loaders):
    """Decorate a function with lazy-loaded regex rules."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._rules_lazy_loaders.extend(loaders)
        return func
    return decorator


def find(*patterns):
    """Decorate a function to trigger for each match of a pattern in a line."""
    def decorator(func):
        func = _ensure_attrs(func)
        for pattern in patterns:
            if pattern not in func._find_rules:
                func._find_rules.append(pattern)
        return func
    return decorator


def find_lazy(*loaders):
    """Decorate a function with lazy-loaded find rules."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._find_rules_lazy_loaders.extend(loaders)
        return func
    return decorator


def search(*patterns):
    """Decorate a function to trigger on the first match of a pattern anywhere in a line."""
    def decorator(func):
        func = _ensure_attrs(func)
        for pattern in patterns:
            if pattern not in func._search_rules:
                func._search_rules.append(pattern)
        return func
    return decorator


def search_lazy(*loaders):
    """Decorate a function with lazy-loaded search rules."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._search_rules_lazy_loaders.extend(loaders)
        return func
    return decorator


def event(*event_list):
    """Decorate a function to be triggered on specific IRC events (JOIN, PART, etc.)."""
    def decorator(func):
        func = _ensure_attrs(func)
        for evt in event_list:
            if evt not in func._events:
                func._events.append(evt)
        return func
    return decorator


def nickname_command(*command_list):
    """Decorate a function to trigger on 'BotNick: command' style messages."""
    def decorator(func):
        func = _ensure_attrs(func)
        for cmd in command_list:
            if cmd not in func._nickname_commands:
                func._nickname_commands.append(cmd)
        return func
    return decorator


nickname_commands = nickname_command


def action_command(*command_list):
    """Decorate a function to trigger on CTCP ACTION commands (/me action)."""
    def decorator(func):
        func = _ensure_attrs(func)
        for cmd in command_list:
            if cmd not in func._action_commands:
                func._action_commands.append(cmd)
        return func
    return decorator


action_commands = action_command


def ctcp(function=None, *command_list):
    """Decorate a function to trigger on CTCP commands."""
    default_commands = ('ACTION',) + command_list

    if function is None:
        return ctcp(*default_commands)
    elif callable(function) and not isinstance(function, str):
        return ctcp(*default_commands)(function)

    ctcp_commands = (function,) + command_list

    def decorator(func):
        func = _ensure_attrs(func)
        for name in ctcp_commands:
            if name not in func._ctcp:
                func._ctcp.append(name)
        return func

    return decorator


def interval(*intervals):
    """Decorate a function to be called periodically (every N seconds)."""
    def decorator(func):
        func = _ensure_attrs(func)
        for iv in intervals:
            if iv not in func._intervals:
                func._intervals.append(iv)
        return func
    return decorator


def url(*patterns):
    """Decorate a function to be triggered when a URL matches."""
    def decorator(func):
        func = _ensure_attrs(func)
        for pattern in patterns:
            func._url_regex.append(pattern)
        return func
    return decorator


def url_lazy(*loaders):
    """Decorate a function with lazy-loaded URL patterns."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._url_lazy_loaders.extend(loaders)
        return func
    return decorator


# --- Restriction decorators ---

def require_admin(message=None, reply=False):
    """Restrict a function to bot admins only."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            if trigger.admin:
                return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    if callable(message):
        fn = message
        message = None
        return decorator(fn)

    return decorator


def require_owner(message=None, reply=False):
    """Restrict a function to the bot owner only."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            if trigger.owner:
                return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    if callable(message):
        fn = message
        message = None
        return decorator(fn)

    return decorator


def require_chanmsg(message=None, reply=False):
    """Restrict a function to channel messages only (not PMs)."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            if not trigger.is_privmsg:
                return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    if callable(message):
        fn = message
        message = None
        return decorator(fn)

    return decorator


def require_privmsg(message=None, reply=False):
    """Restrict a function to private messages only."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            if trigger.is_privmsg:
                return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    if callable(message):
        fn = message
        message = None
        return decorator(fn)

    return decorator


def require_privilege(level, message=None, reply=False):
    """Restrict a function to users with a specific channel privilege level."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            # Check if user has the required privilege in the channel
            channel = trigger.sender
            if channel and not channel.is_nick():
                if hasattr(bot, '_get_privilege'):
                    user_priv = bot._get_privilege(channel, trigger.nick)
                    if user_priv >= level:
                        return True
                # Also allow admins/owner
                if trigger.admin:
                    return True
            if message:
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    return decorator


def require_bot_privilege(level, message=None, reply=False):
    """Restrict a function to run only when the bot has a channel privilege.

    In a private message the check is skipped (the function runs), matching
    Sopel's behaviour. In a channel, the bot must hold at least ``level``.
    """
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            channel = trigger.sender
            # Not in a channel (PM): the privilege check does not apply.
            if channel is None or channel.is_nick():
                return True
            if hasattr(bot, 'has_channel_privilege'):
                if bot.has_channel_privilege(channel, level):
                    return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    return decorator


def require_account(message=None, reply=False):
    """Restrict a function to users logged into services."""
    def decorator(func):
        func = _ensure_attrs(func)

        def predicate(bot, trigger):
            if trigger.account:
                return True
            if message and not callable(message):
                if reply:
                    bot.reply(message)
                else:
                    bot.say(message)
            return False

        func._predicates.append(predicate)
        return func

    if callable(message):
        fn = message
        message = None
        return decorator(fn)

    return decorator


# --- Behavioral decorators ---

def thread(value):
    """Set whether the function should run in a separate thread."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._threaded = bool(value)
        return func
    return decorator


def priority(value):
    """Set the execution priority: 'low', 'medium', or 'high'."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._priority = value
        return func
    return decorator


def unblockable(function=None):
    """Exempt a function from the bot's ignore system."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._unblockable = True
        return func

    if callable(function):
        return decorator(function)
    return decorator


def allow_bots(function=None):
    """Allow a function to receive events from other bots."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._allow_bots = True
        return func

    if callable(function):
        return decorator(function)
    return decorator


def echo(function=None):
    """Allow a function to receive the bot's own echo messages."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._allow_echo = True
        return func

    if callable(function):
        return decorator(function)
    return decorator


# --- Rate limiting ---

def rate(user=0, channel=0, server=0, *, message=None, include_admins=False):
    """Set rate limits for a function."""
    def decorator(func):
        func = _ensure_attrs(func)
        if func._rate_user == 0:
            func._rate_user = user
        if func._rate_channel == 0:
            func._rate_channel = channel
        if func._rate_global == 0:
            func._rate_global = server
        func._rate_message = message
        func._rate_limit_admins = include_admins
        return func
    return decorator


def rate_user(rate_val, message=None, include_admins=False):
    """Set per-user rate limit."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._rate_user = rate_val
        if message:
            func._rate_message = message
        func._rate_limit_admins = include_admins
        return func
    return decorator


def rate_channel(rate_val, message=None, include_admins=False):
    """Set per-channel rate limit."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._rate_channel = rate_val
        if message:
            func._rate_message = message
        func._rate_limit_admins = include_admins
        return func
    return decorator


def rate_global(rate_val, message=None, include_admins=False):
    """Set global rate limit."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._rate_global = rate_val
        if message:
            func._rate_message = message
        func._rate_limit_admins = include_admins
        return func
    return decorator


# --- Documentation decorators ---

def example(text, help_text=None, *, user_help=False, online=False, result=None, extra=None):
    """Add an example to a function's documentation."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._examples.append({
            'text': text,
            'help_text': help_text,
            'user_help': user_help,
            'online': online,
            'result': result,
            'extra': extra,
        })
        return func
    return decorator


def output_prefix(prefix):
    """Add a prefix to all output from this function."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._output_prefix = prefix
        return func
    return decorator


def label(value):
    """Give a human-readable label to a rule."""
    def decorator(func):
        func = _ensure_attrs(func)
        func._label = value
        return func
    return decorator


def intent(*intent_list):
    """Alias for ctcp — trigger on CTCP messages with specific intents."""
    return ctcp(*intent_list)
