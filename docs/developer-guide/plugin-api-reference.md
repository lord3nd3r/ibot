[Docs home](../index.md) › Developer guide › Plugin API reference

# Plugin API reference

This is the complete reference for the API that ibot exposes to plugins through the `sopel` compatibility package: decorators, constants, the `trigger` and `bot` objects, tracked channel and user state, memory, and lifecycle hooks. Everything listed here exists in the ibot source. Sopel features that aren't listed aren't available.

## In this article

- [Prerequisites](#prerequisites)
- [Importable modules](#importable-modules)
- [Trigger decorators](#trigger-decorators)
- [Restriction decorators](#restriction-decorators)
- [Behaviour decorators](#behaviour-decorators)
- [Rate-limit decorators](#rate-limit-decorators)
- [Metadata decorators](#metadata-decorators)
- [Constants](#constants)
- [Trigger](#trigger)
- [The bot object](#the-bot-object)
- [Channel and user state](#channel-and-user-state)
- [Memory classes](#memory-classes)
- [Lifecycle hooks](#lifecycle-hooks)
- [See also](#see-also)

## Prerequisites

- [Writing plugins](writing-plugins.md)

## Importable modules

The shim is installed into `sys.modules` before any plugin is loaded.

| Import | Provides |
|---|---|
| `sopel` | The package. `sopel.plugin`, `sopel.module`, `sopel.tools`, `sopel.formatting` are available as attributes. |
| `sopel.plugin` | Every decorator and constant on this page |
| `sopel.module` | Legacy alias, re-exporting `sopel.plugin` |
| `sopel.trigger` | `PreTrigger`, `Trigger` |
| `sopel.bot` | `SopelWrapper` |
| `sopel.db` | `SopelDB` |
| `sopel.config`, `sopel.config.types`, `sopel.config.core_section` | Configuration. See [Plugin configuration](../configuration/plugin-config.md). |
| `sopel.tools`, `sopel.tools.web`, `sopel.tools.time`, `sopel.tools.events`, `sopel.tools.identifiers`, `sopel.tools.target` | See [Tools reference](tools-reference.md) |
| `sopel.formatting` | IRC formatting helpers |
| `sopel.privileges` | `AccessLevel` and the level constants |
| `sopel.irc`, `sopel.irc.utils`, `sopel.plugins`, `sopel.plugins.exceptions` | **Empty stub modules**, so imports succeed but contain nothing |
| `sopel.lifecycle` | A stub containing only a no-op `deprecated` decorator |

## Trigger decorators

| Decorator | Arguments | Fires on |
|---|---|---|
| `command(*names)` / `commands` | Command names | `<prefix>name [args]` |
| `nickname_command(*names)` / `nickname_commands` | Command names | `BotNick: name [args]` (also `,` or a space after the nick) |
| `action_command(*names)` / `action_commands` | Command names | `/me name [args]` |
| `rule(*patterns)` | Strings or compiled patterns | `re.match` on the text |
| `rule_lazy(*loaders)` | `loader(settings) -> [pattern, …]` | As `rule`. The loaders are called when the plugin is registered. |
| `find(*patterns)` / `find_lazy(*loaders)` | Patterns / loaders | Every non-overlapping match (one call per match) |
| `search(*patterns)` / `search_lazy(*loaders)` | Patterns / loaders | The first `re.search` match |
| `url(*patterns)` / `url_lazy(*loaders)` | Patterns / loaders | Each URL found in a message that matches the pattern |
| `event(*events)` | `'JOIN'`, `'001'`, … | Any line with that command (case-insensitive) |
| `ctcp(*commands)` / `intent(*commands)` | CTCP names. Bare `@ctcp` or `@ctcp()` means `ACTION`. | A CTCP request in a PRIVMSG |
| `interval(*seconds)` | Numbers | Periodically. The function receives `(bot)` only. |

Patterns may contain `$nick`, which is replaced by the escaped bot nick plus `[:,\s]\s*`. See [Dispatch: pattern compilation](../architecture/dispatch.md#pattern-compilation).

## Restriction decorators

All of them take `message=None, reply=False`. With a message, a refused call answers with `bot.say(message)`, or `bot.reply(message)` if `reply=True`. Without one, it's dropped silently. `require_admin`, `require_owner`, `require_chanmsg`, `require_privmsg` and `require_account` can also be used bare (`@plugin.require_admin`).

| Decorator | Condition |
|---|---|
| `require_admin` | `trigger.admin` |
| `require_owner` | `trigger.owner` |
| `require_chanmsg` | Not a private message |
| `require_privmsg` | A private message |
| `require_account` | `trigger.account` is set |
| `require_privilege(level, message=None, reply=False)` | In a channel: the caller's privilege is `>= level`, or the caller is an admin. In a PM it **always fails**. |
| `require_bot_privilege(level, message=None, reply=False)` | In a channel: the bot's privilege is `>= level`. In a PM it always passes. |

> **Note:** `require_privilege` and `require_bot_privilege` must be called with a level: `@plugin.require_privilege(plugin.OP)`.

## Behaviour decorators

| Decorator | Default | Effect |
|---|---|---|
| `thread(bool)` | `True` | `False` runs the handler inline on the event loop |
| `priority('high' \| 'medium' \| 'low')` | `'medium'` | Order within a handler list |
| `unblockable` | off | Ignore `nick_blocks`/`host_blocks` |
| `allow_bots` | off | Receive messages tagged as coming from bots |
| `echo` | off | Receive messages sent by the bot itself |
| `output_prefix(prefix)` | `''` | Prepended to `say`, `reply`, `notice` and `action` output |

> **Warning:** With `output_prefix`, `bot.reply()` adds the prefix **twice**: once before `nick:` and once after it.

## Rate-limit decorators

| Decorator | Signature |
|---|---|
| `rate` | `rate(user=0, channel=0, server=0, *, message=None, include_admins=False)` |
| `rate_user` | `rate_user(seconds, message=None, include_admins=False)` |
| `rate_channel` | `rate_channel(seconds, message=None, include_admins=False)` |
| `rate_global` | `rate_global(seconds, message=None, include_admins=False)` |

`rate()` only sets scopes that haven't already been set by another rate decorator. Return `plugin.NOLIMIT` from the handler to stop a call counting. See [Dispatch: rate limiting](../architecture/dispatch.md#rate-limiting).

## Metadata decorators

| Decorator | Stored as | Used by ibot |
|---|---|---|
| `example(text, help_text=None, *, user_help=False, online=False, result=None, extra=None)` | `func._examples` (a list of dicts) | ❌ Metadata only |
| `label(value)` | `func._label` | ❌ Metadata only |

## Constants

| Name | Value |
|---|---|
| `plugin.NOLIMIT` | `1` |
| `plugin.VOICE` / `HALFOP` / `OP` / `ADMIN` / `OWNER` / `OPER` | `1` / `2` / `4` / `8` / `16` / `32` |
| `sopel.privileges.AccessLevel.*` | The same values |

The privilege values are bit flags. Comparisons such as `>= plugin.OP` treat them as levels.

## Trigger

`trigger` is a `str` subclass equal to the message text.

| Attribute | Type | Description |
|---|---|---|
| `nick` | `Identifier` | The sender's nick |
| `user`, `host` | `str` | The sender's ident and host |
| `hostmask` | `str` | `nick!user@host` |
| `sender` | `Identifier` | The channel, or the sender's nick in a PM |
| `is_privmsg` | `bool` | Not from a channel. A channel is anything starting with `#`, `&`, `+` or `!`. |
| `event` | `str` | The IRC command or numeric |
| `args` | `list` | The IRC parameters |
| `tags` | `dict` | IRCv3 tags (escapes decoded). A tag without a value maps to `None`. |
| `time` | `datetime` (UTC) | `server-time`, or the time it was received |
| `account` | `str` / `None` | The `account` tag, or the tracked account |
| `admin`, `owner` | `bool` | See [Permissions](../administration/permissions.md) |
| `ctcp` | `str` / `None` | The CTCP command |
| `urls` | `tuple` | URLs found in the text |
| `plain` | `str` | The text with formatting stripped |
| `raw` | `str` | The original IRC line |
| `status_prefix` | `None` | Always `None`: status-message prefixes aren't parsed. A `PRIVMSG @#chan` gets `sender == '@#chan'`, which is treated as a PM. |
| `match`, `group`, `groups`, `groupdict` | — | The regex match |
| `text` | `str` | The message text |

**Example.** This handler was tested against the dispatcher with `tags`, PM and channel input:

```python
from sopel import plugin


@plugin.command('whoami')
@plugin.require_chanmsg('Use this in a channel.')
def whoami(bot, trigger):
    acct = trigger.account or 'not logged in'
    role = 'owner' if trigger.owner else 'admin' if trigger.admin else 'user'
    bot.reply(f'{acct}, {role}, args={trigger.group(2)!r}')
```

```text
<alice> .whoami foo bar          (in #c, with account-tag "alice")
<bot>   alice: alice, user, args='foo bar'
<bob>   .whoami                  (in a private message)
<bot>   Use this in a channel.
```

## The bot object

Handlers receive a `SopelWrapper`. Its full API:

| Member | Description |
|---|---|
| `say(text, destination=None, max_messages=1, truncation=None, trailing=None)` | PRIVMSG. Splits on newlines and at 400 bytes, sending at most `max_messages` lines. When text is cut, `truncation`+`trailing` are appended to the last line. |
| `reply(text, destination=None, reply_to=None, notice=False)` | `nick: text` |
| `notice(text, destination=None)` | NOTICE. One NOTICE per line of `text`, each split into 400-byte chunks; all chunks are sent |
| `action(text, destination=None)` | CTCP ACTION. One per line of `text`, not split by length (the line is cut at 510 bytes on the wire) |
| `msg(recipient, text)` | PRIVMSG. Split on newlines and at 400 bytes; all chunks are sent |
| `write(args, text=None)` | A raw line: `' '.join(args)` + ` :text`. CR/LF in either part become spaces. |
| `join(channel, password=None)`, `part(channel, msg=None)`, `kick(nick, channel=None, text=None)` | IRC commands (each argument is forced onto one line) |
| `quit(message=None)` | Send `QUIT` and shut the bot down for good (no reconnect), like `.bquit`. Called from a handler thread, it waits up to about 11 s for the quit to finish. |
| `restart(message='Restarting')` | Quit like `quit()`, then re-execute the process with the same arguments (`python -m ibot …`) once shutdown hooks have run |
| `reload_plugin(name)` | Reload one plugin by name, exactly like `.reload`. Raises on failure (the old version is kept). |
| `nick` | The bot's current nick |
| `settings`, `config` | The configuration object |
| `db` | `SopelDB`. See [Database](../architecture/database.md). |
| `memory` | A shared `SopelMemory` |
| `channels`, `users` | Tracked state (below) |
| `has_channel_privilege(channel, level)` | Whether the bot holds at least `level` |
| *anything else* | Looked up on the core `IRCBot` object (public names only; names starting with `_` raise `AttributeError`) |

> **Warning:** The fallback reaches ibot's **core** object, whose attributes aren't a stable API. Sopel attributes such as `bot.privileges`, `bot.hostmask`, `bot.search_url_callbacks`, `bot.register_url_callback()`, and `bot.rate_limit_info()` don't exist there either, so they still raise `AttributeError`. `bot.isupport` *is* reached this way, but it's a plain `dict` of upper-case token → string value (an empty string for tokens without `=`), not Sopel's `ISupport` object.

## Channel and user state

`bot.channels` maps `Identifier` → `Channel`, and `bot.users` maps `Identifier` → `User`. The lookups are case-insensitive. Read them; don't change them.

| `Channel` member | Description |
|---|---|
| `name` | `Identifier` |
| `users` | nick → `User` |
| `privileges` | nick → a bitmask of the levels above |
| `topic` | From `332`/`TOPIC` |
| `has_privilege(nick, level)` | `privileges[nick] >= level` |
| `is_voiced`, `is_halfop`, `is_op`, `is_admin`, `is_owner` `(nick)` | Bit tests |

| `User` member | Description |
|---|---|
| `nick`, `user`, `host`, `hostmask` | Identity |
| `account` | From the `account-tag` message tag, extended-join, or `ACCOUNT` messages (account-notify isn't requested) |
| `realname` | From extended-join only |
| `channels` | A set of channel `Identifier`s |
| `away` | Present, but **never updated** by the core |
| `is_bot` | Set to `True` (and never cleared) when a message carrying the `bot` tag reaches a handler that gets past the ignore/bot filters. Otherwise stays `False` |

## Memory classes

| Class | Behaviour |
|---|---|
| `tools.SopelMemory` | A `dict` whose individual operations are protected by a lock |
| `tools.SopelMemoryWithDefault(factory)` | Like `defaultdict` |
| `tools.SopelIdentifierMemory` | Keys are converted to `Identifier` (case-insensitive) |

## Lifecycle hooks

| Function | Called | Notes |
|---|---|---|
| `setup(bot)` | Exactly once per load: at startup (before connecting), and on `.load`, `.reload` and `.rehash` | Called as `setup()` if it takes no parameters. If it raises, the plugin is unregistered (startup, `.load`) or the previous version is restored (`.reload`, `.rehash`). |
| `shutdown(bot)` | `.unload`, `.reload`, `.rehash` (replaced or removed plugins), and process exit (every plugin loaded at that moment) | Receives a bot wrapper. Exceptions are logged and reported, and don't stop the unload. |
| `configure(config)` | **Never.** ibot has no configuration wizard. | — |

## See also

- [Writing plugins](writing-plugins.md)
- [Tools reference](tools-reference.md)
- [Sopel compatibility](sopel-compatibility.md)
- [Dispatch](../architecture/dispatch.md)

---
[← Back to docs home](../index.md)
