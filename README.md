# ibot

A lightweight, asyncio-powered IRC bot that runs **existing Sopel plugins** with zero modifications.

Drop in your Sopel config, database, and scripts — they just work.

## Features

- **Drop-in Sopel compatibility** — uses the same config format, database schema, and plugin API
- **Hot-reload** — IRCd-style `rehash` reloads config and all plugins without disconnecting
- **Admin controls** — load/unload/reload individual plugins at runtime via IRC
- **SQLAlchemy database** — identical schema to Sopel (`nick_ids`, `nicknames`, `nick_values`, `channel_values`, `plugin_values`)
- **Custom config sections** — full support for `StaticSection`, `ValidatedAttribute`, `ListAttribute`, etc.
- **asyncio core** — efficient I/O with SSL/TLS, auto-reconnect, and flood protection

## Quick Start

```bash
# Generate a fresh config file
python -m ibot --generate-config mybot.cfg

# Edit it with your server, nick, channels, etc.
nano mybot.cfg

# Run
python -m ibot mybot.cfg

# Run with debug logging
python -m ibot -v mybot.cfg
```

## Using Your Existing Sopel Setup

Point ibot at your Sopel config and it works:

```bash
python -m ibot /path/to/your/sopel.cfg
```

Or copy your files over and adjust paths:

```ini
[core]
nick = glitchy
host = irc.rizon.net
port = 6697
use_ssl = true
owner = YourNick
prefix = \$
auth_method = nickserv
auth_password = your_pass
db_filename = glitchy.db
extra = /path/to/your/sopel-scripts
channels =
    "#channel1"
    "#channel2"
```

## Admin Commands

All admin commands use your configured prefix (e.g. `$`, `.`).

| Command | Access | Description |
|---------|--------|-------------|
| `rehash` | Owner | Reload config + all plugins from disk |
| `reload <name>` | Owner | Hot-reload a single plugin |
| `load <name>` | Owner | Load a new plugin at runtime |
| `unload <name>` | Owner | Unload a plugin |
| `plugins` | Owner | List loaded plugins |
| `bjoin #chan` | Admin | Join a channel |
| `bpart #chan` | Admin | Part a channel |
| `raw <cmd>` | Owner | Send a raw IRC command |
| `say <target> <msg>` | Admin | Send a message |
| `bnick <nick>` | Owner | Change bot nick |
| `bmode #chan +o nick` | Admin | Set channel mode |
| `bquit [msg]` | Owner | Shut down the bot |
| `bstatus` | Admin | Show bot status |

## Sopel Plugin Compatibility

Plugins using standard Sopel APIs work without modification:

```python
from sopel import plugin

@plugin.command('hello')
def hello(bot, trigger):
    bot.say(f"Hello, {trigger.nick}!")
```

### Supported APIs

| Feature | Status |
|---------|--------|
| **Decorators** | |
| `@plugin.command()` / `@plugin.rule()` | ✅ |
| `@plugin.event()` / `@plugin.interval()` | ✅ |
| `@plugin.nickname_command()` / `@plugin.action_command()` | ✅ |
| `@plugin.find()` / `@plugin.search()` / `@plugin.url()` | ✅ |
| `@plugin.ctcp()` / `@plugin.intent()` | ✅ |
| `@plugin.require_admin` / `require_owner` / `require_chanmsg` | ✅ |
| `@plugin.require_privmsg` / `require_privilege` / `require_account` | ✅ |
| `@plugin.require_bot_privilege` | ✅ |
| `@plugin.rate()` / `thread()` / `priority()` | ✅ |
| `@plugin.unblockable` / `allow_bots` / `echo` | ✅ |
| `@plugin.example()` / `output_prefix()` | ✅ |
| **Bot Object** | |
| `bot.say()` (max_messages / truncation / trailing) / `reply()` / `notice()` / `action()` | ✅ |
| `bot.kick()` / `join()` / `part()` / `write()` | ✅ |
| `bot.nick` / `bot.settings` / `bot.config` | ✅ |
| `bot.db` (SQLAlchemy — Sopel schema + `get_*_values` bulk) | ✅ |
| `bot.memory` (SopelMemory) | ✅ |
| `bot.channels` / `bot.users` (account + is_bot tracking) | ✅ |
| `sopel.tools.target` (`User` / `Channel`, `is_op()`/`is_voiced()`/…) | ✅ |
| `sopel.tools.web` (`search_urls` / `quote` / `get` / `decode` / …) | ✅ |
| IRCv3 `account-tag` / `extended-join` / `multi-prefix` / `server-time` | ✅ |
| `nick_blocks` / `host_blocks` ignore lists | ✅ |
| **Trigger Object** | |
| `trigger.nick` / `.sender` / `.host` / `.account` | ✅ |
| `trigger.group()` / `.match` / `.args` / `.tags` | ✅ |
| `trigger.admin` / `.owner` / `.is_privmsg` | ✅ |
| **Config Types** | |
| `StaticSection` / `define_section()` | ✅ |
| `ValidatedAttribute` / `BooleanAttribute` / `SecretAttribute` | ✅ |
| `ListAttribute` / `ChoiceAttribute` / `FilenameAttribute` | ✅ |
| **Legacy** | |
| `from sopel import module` | ✅ |
| `setup()` / `shutdown()` hooks | ✅ |

## Plugin Directories

Plugins are loaded from (in order):
1. `ibot/plugins/` — built-in plugins
2. `plugins/` — next to your config file
3. Directories listed in `extra` under `[core]`

## Architecture

- **Pure Python** — only external dependency is `sqlalchemy`
- **asyncio** — non-blocking I/O with SSL/TLS
- **Sopel shim** — injects into `sys.modules` so `import sopel` resolves to the compatibility layer
- **Thread-per-handler** — plugin functions run in threads (like Sopel)
- **Flood protection** — token bucket rate limiting
- **Auto-reconnect** — exponential backoff on disconnection

## License

MIT
