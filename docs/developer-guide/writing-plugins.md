[Docs home](../index.md) › Developer guide › Writing plugins

# Writing plugins

This tutorial walks through writing an ibot plugin from scratch: a command, a pattern rule, a URL handler, persistent storage, configuration, setup and shutdown hooks, and a periodic job. ibot plugins are written exactly like Sopel plugins: you import from `sopel`, and ibot provides that package.

## In this article

- [Prerequisites](#prerequisites)
- [Anatomy of a plugin](#anatomy-of-a-plugin)
- [Step 1: A first command](#step-1-a-first-command)
- [Step 2: Arguments and replies](#step-2-arguments-and-replies)
- [Step 3: Restricting who can use it](#step-3-restricting-who-can-use-it)
- [Step 4: Reacting to patterns and URLs](#step-4-reacting-to-patterns-and-urls)
- [Step 5: Storing data](#step-5-storing-data)
- [Step 6: Configuration](#step-6-configuration)
- [Step 7: setup, shutdown and shared state](#step-7-setup-shutdown-and-shared-state)
- [Step 8: Periodic jobs](#step-8-periodic-jobs)
- [Step 9: Reacting to IRC events](#step-9-reacting-to-irc-events)
- [Best practices](#best-practices)
- [Common mistakes](#common-mistakes)
- [See also](#see-also)

## Prerequisites

- A working ibot install. See the [Quickstart](../getting-started/quickstart.md).
- A plugin directory listed in [`[core] extra`](../configuration/core-reference.md#extra), or the default `plugins/` directory.
- Owner rights on the bot, so you can use `.load` and `.reload`. See [Admin commands](../administration/admin-commands.md).

## Anatomy of a plugin

A plugin is a single `.py` file. The file name (without `.py`) is the plugin name used by `.load`, `.reload`, `.disable` and `exclude`.

| Part | Required | Purpose |
|---|---|---|
| `from sopel import plugin` | ✅ | The decorators. `from sopel import module` (legacy) also works. |
| Decorated module-level functions | ✅ | Handlers, called as `func(bot, trigger)` |
| `setup(bot)` | ❌ | Called once after loading |
| `shutdown(bot)` | ❌ | Called before unloading or reloading, and when the bot exits |
| A config section class | ❌ | Typed settings. See [Plugin configuration](../configuration/plugin-config.md). |

> **Note:** Only **module-level functions** are scanned. Decorated methods inside classes, and functions created inside other functions, aren't registered. Functions you import into the plugin from another module *are* scanned if they carry decorators, so keep shared helpers undecorated.

## Step 1: A first command

Create `hello.py` in your plugin directory:

```python
"""hello.py - a minimal ibot plugin."""
from sopel import plugin


@plugin.command('hello', 'hi')
@plugin.example('.hello')
def hello(bot, trigger):
    """Greet the caller."""
    bot.say(f'Hello, {trigger.nick}!')
```

Load it without restarting:

```text
<you>   .load hello
<bot>   Loaded hello (2 commands)
<you>   .hello
<bot>   Hello, you!
```

| Element | Meaning |
|---|---|
| `@plugin.command('hello', 'hi')` | Responds to `<prefix>hello` and `<prefix>hi`, case-insensitively |
| `@plugin.example` | Stored as metadata (`func._examples`). ibot has no built-in help command that reads it, but it's kept for Sopel compatibility and for your own help plugins. |
| `bot.say(text)` | Sends a PRIVMSG to where the command came from: the channel, or the user in a PM |

## Step 2: Arguments and replies

For commands, `trigger.group(1)` is the command name and `trigger.group(2)` is everything after it, or `None`.

```python
@plugin.command('roll')
def roll(bot, trigger):
    import random
    arg = (trigger.group(2) or '6').strip()
    if not arg.isdigit() or not 1 < int(arg) <= 1000:
        bot.reply('Usage: .roll [sides], 2-1000')
        return plugin.NOLIMIT
    bot.reply(f'You rolled {random.randint(1, int(arg))}')
```

| Method | Result |
|---|---|
| `bot.say(text)` | `text` |
| `bot.reply(text)` | `nick: text` |
| `bot.reply(text, notice=True)` | The same, sent as a NOTICE |
| `bot.notice(text)` / `bot.notice(text, nick)` | A NOTICE to the channel, or to a nick |
| `bot.action(text)` | `/me text` |
| `bot.say(text, '#other')` | Sent somewhere else |

Returning `plugin.NOLIMIT` means "don't count this call towards the rate limit". It's useful for usage errors.

## Step 3: Restricting who can use it

```python
from sopel import plugin

@plugin.require_chanmsg('Use this in a channel.')
@plugin.require_privilege(plugin.OP, 'You need to be a channel operator.')
@plugin.require_bot_privilege(plugin.OP, 'I need ops for that.')
@plugin.command('topicset')
def topicset(bot, trigger):
    bot.write(('TOPIC', trigger.sender), trigger.group(2) or '')
```

| Decorator | Passes when |
|---|---|
| `require_admin(msg)` | The caller is an admin or the owner |
| `require_owner(msg)` | The caller is the owner |
| `require_chanmsg(msg)` / `require_privmsg(msg)` | The message came from a channel or a PM, respectively |
| `require_privilege(level, msg)` | In a channel: the caller has at least `level` there, **or** is an admin. **Always fails in a PM.** |
| `require_bot_privilege(level, msg)` | In a channel: the bot has at least `level`. Always passes in a PM. |
| `require_account(msg)` | The caller is logged in to services |

Every `require_*` decorator takes `reply=True` to answer with `reply()` instead of `say()`. Without a message, a refused call is dropped silently. Checks run **bottom-up**, so the decorator nearest the `def` is checked first. See [Dispatch: the filter chain](../architecture/dispatch.md#the-filter-chain) and [Permissions](../administration/permissions.md).

Rate limiting:

```python
@plugin.rate(user=30, channel=10, message='Slow down a bit.')
@plugin.command('weather')
def weather(bot, trigger): ...
```

> **Note:** Admins skip rate limits unless you pass `include_admins=True`. The `message` is sent as a NOTICE, as written. Placeholders aren't filled in.

## Step 4: Reacting to patterns and URLs

```python
import re
from sopel import plugin

# Match anywhere in a line, once per line
@plugin.search(r'\bcoffee\b')
def coffee(bot, trigger):
    bot.action('hands out coffee ☕')

# Must match from the start of the line. Use (?i) for case-insensitivity.
@plugin.rule(r'(?i)^$nick[,:]?\s+thanks')
def thanks(bot, trigger):
    bot.reply("You're welcome!")

# Once per URL matching the pattern
@plugin.url(r'https?://(?:www\.)?example\.com/item/(\d+)')
def example_item(bot, trigger):
    bot.say(f'Item #{trigger.group(1)}')
```

| Decorator | Matching |
|---|---|
| `rule` | `re.match` from the start of the line, case-insensitive (`re.IGNORECASE`; multi-line patterns also get `re.VERBOSE`) |
| `search` | `re.search`: the first match anywhere |
| `find` | `re.finditer`: one call **per match** |
| `url` | `re.search` against each URL in the message |
| `nickname_command('cmd')` | `Bot: cmd args` / `Bot, cmd args` |
| `action_command('cmd')` | `/me cmd args` |

> **Warning:** Rules, searches and URL handlers **don't run on lines that matched a command**. `.say see https://example.com/item/4` won't trigger `example_item`. See [Dispatch](../architecture/dispatch.md#known-limitations).

> **Note:** In a rule pattern, `$nickname` becomes the bot's current nick (regex-escaped) and `$nick` becomes the nick followed by `:`, `,` or whitespace (`MyBot[:,\s]\s*`), as in Sopel. Patterns are recompiled when the bot's nick changes.

## Step 5: Storing data

```python
@plugin.command('setloc')
def setloc(bot, trigger):
    loc = (trigger.group(2) or '').strip()
    if not loc:
        bot.reply('Usage: .setloc <place>')
        return
    bot.db.set_nick_value(trigger.nick, 'location', loc)
    bot.reply(f'Saved {loc}.')

@plugin.command('loc')
def loc(bot, trigger):
    who = (trigger.group(2) or trigger.nick).strip()
    bot.say(bot.db.get_nick_value(who, 'location') or 'Unknown.')
```

Values must be JSON-serialisable. See [Database](../architecture/database.md#the-botdb-api) for every method.

## Step 6: Configuration

```python
from sopel import plugin
from sopel.config import types


class WeatherSection(types.StaticSection):
    api_key = types.SecretAttribute('api_key')
    units = types.ChoiceAttribute('units', ['metric', 'imperial'], default='metric')


def setup(bot):
    bot.settings.define_section('weather', WeatherSection)


@plugin.command('w')
def w(bot, trigger):
    if not bot.settings.weather.api_key:
        bot.reply('The weather plugin is not configured.')
        return
    ...
```

```ini
[weather]
api_key = YOUR_KEY_HERE
units = metric
```

See [Plugin configuration](../configuration/plugin-config.md) for every attribute type.

> **Warning:** Never echo configuration values, exceptions that may contain them, or `bot.db.get_uri()` to IRC.

## Step 7: setup, shutdown and shared state

```python
import threading

def setup(bot):
    bot.memory['quotes_lock'] = threading.Lock()
    bot.memory.setdefault('quotes_cache', {})

def shutdown(bot):
    bot.memory.pop('quotes_cache', None)
```

| Hook | When it's called | Argument |
|---|---|---|
| `setup(bot)` | Exactly once per load: at startup, after all plugins are registered and **before** connecting, and again on `.load`, `.reload` and `.rehash`. | The bot wrapper. A `setup()` with no parameters is called as `setup()`. If it raises, the plugin is unregistered (at startup or `.load`) or the previous version is kept (`.reload`/`.rehash`). |
| `shutdown(bot)` | Before `.unload`, before the new version's `setup()` on `.reload` and `.rehash`, and on exit (for every plugin loaded at that moment) | The bot wrapper. At exit the connection is already closed, so messages sent from `shutdown()` are dropped. |

> **Warning:** Messages sent from `setup()` at startup are dropped, because the connection doesn't exist yet. Defer greetings to an event handler (for example `@plugin.event('001')`).

> **Note:** If a new version's `setup()` fails on `.reload`, the old version's `setup()` runs again (its `shutdown()` already ran). Keep `setup()` and `shutdown()` safe to call in that order more than once.

`bot.memory` is a dict shared by all plugins. Each single operation is locked, but compound updates aren't, so use your own lock for read-modify-write.

## Step 8: Periodic jobs

```python
@plugin.interval(3600)
def hourly(bot):
    bot.say('Hourly reminder: stretch!', '#mychannel')
```

| Behaviour | Detail |
|---|---|
| Signature | `func(bot)`. There's no trigger. |
| Destination | **Required**. With no trigger there's no default target. |
| First run | One full interval after connecting |
| Execution | In asyncio's default executor (a thread), so blocking is allowed. Interval jobs don't use the handler pool. |
| Errors | Retried with a back-off of 5 s, 10 s, 20 s… (capped at the interval). The job is **disabled after 5 consecutive failures** until the next reconnect or reload of the plugin. |
| Reloads | `.reload`, `.unload` and `.rehash` cancel the old jobs; `.load`/`.reload`/`.rehash` start the new ones straight away (with a fresh initial delay). |
| Disconnects | All jobs are cancelled on disconnect and started again after the next connect |

## Step 9: Reacting to IRC events

```python
@plugin.event('JOIN')
def greet(bot, trigger):
    if trigger.nick != bot.nick:
        bot.say(f'Welcome to {trigger.sender}, {trigger.nick}!')

@plugin.event('001')
def connected(bot, trigger):
    bot.say('I am online.', 'End3r')
```

Events can be IRC commands (`JOIN`, `PART`, `QUIT`, `NICK`, `MODE`, `KICK`, `INVITE`, `NOTICE`, `TOPIC`) or numerics (`'001'`, `'433'`). `sopel.tools.events` gives names for common numerics.

> **Warning:** Don't combine `@plugin.event` with `@plugin.rule` and expect the rule to filter the event. In ibot the function runs for **every** such event. Check the text inside the function instead.

## Best practices

| Do | Why |
|---|---|
| Use timeouts for all network calls (`requests.get(url, timeout=10)`) | Handlers run in threads, but hung threads pile up |
| Don't build raw IRC lines from user input with `bot.write` | ibot replaces CR, LF and NUL with spaces in every outgoing line, so injection of a *second* line is blocked, but user text can still add parameters to the one line you send |
| Validate URLs before fetching them, and reject private IPs | Prevents SSRF against internal services |
| Catch expected exceptions and reply with a short, generic error | Unhandled exceptions are only logged. The user sees nothing. |
| Use `bot.say(text, max_messages=3)` deliberately | `say` sends **one** line by default and cuts off the rest |
| Keep `@plugin.thread(False)` for trivial, non-blocking handlers | These run on the network loop |
| Use `python3 -m py_compile file.py` before `.reload` | A failed `.reload` keeps the old version, but you find the mistake faster |

## Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| A command does nothing, and there's no log | Another plugin's command with the same name sorts first | Rename it, or `exclude` the other plugin |
| A rule never fires | It's anchored at the start, or the line began with a command | Use `search`, or `.*` at the start |
| Only the first line of output appears | `say()` defaults to `max_messages=1` | Pass `max_messages=N`, or use `bot.msg` |
| `KeyError` on `bot.memory[...]` after `.reload` | Memory survives reloads, but your setup changed it | Use `setdefault` in `setup()` |
| `AttributeError` on `bot.<something>` | Neither the wrapper nor the core bot has that attribute (the wrapper falls back to the core bot for anything it doesn't define) | See [Plugin API reference](plugin-api-reference.md#the-bot-object) |

## See also

- [Plugin API reference](plugin-api-reference.md)
- [Tools reference](tools-reference.md)
- [Testing](testing.md)
- [Sopel compatibility](sopel-compatibility.md)
- [sopel-scripts](https://github.com/lord3nd3r/sopel-scripts): real-world examples

---
[← Back to docs home](../index.md)
