# ibot

**ibot** is a lightweight, asyncio IRC bot that runs **existing [Sopel](https://sopel.chat/) plugins** with little or no modification.

Point it at a Sopel-style INI config (and optional Sopel SQLite/MySQL/Postgres database), drop your `.py` scripts into a plugin directory, and they load through a compatibility shim that makes `import sopel` resolve to ibot’s own API layer.

| | |
|---|---|
| **Version** | 1.0.0 (stable-ish / somewhat beta) |
| **Python** | 3.8+ |
| **License** | MIT |
| **Core dependency** | [SQLAlchemy](https://www.sqlalchemy.org/) 2.x |
| **Repository** | https://github.com/lord3nd3r/ibot |

---

## Why ibot?

Sopel is a mature IRC bot framework with a large plugin ecosystem. ibot reimplements the **plugin surface and data model** on a smaller asyncio core so you can:

- Keep writing plugins against the familiar `sopel.plugin` / `bot` / `trigger` / `bot.db` APIs
- Reuse Sopel-compatible config files and databases
- Hot-reload config and plugins without disconnecting
- Avoid pulling in the full Sopel runtime when you only need a thin, modern client

ibot is **not** a fork of Sopel’s codebase. It is a separate IRC client plus a **compatibility shim** (`ibot.sopel_shim`) that is injected into `sys.modules` at startup.

---

## Features

- **Sopel plugin compatibility** — decorators, trigger context, config sections, DB schema, and common tools modules
- **asyncio IRC core** — SSL/TLS, NickServ and SASL PLAIN auth, flood control, auto-reconnect with exponential backoff
- **IRCv3 capabilities** — requests `account-tag`, `extended-join`, `multi-prefix`, `server-time` (and `sasl` when configured)
- **Hot-reload** — owner `rehash` reloads config + all plugins; per-plugin `load` / `unload` / `reload`
- **Admin controls** — join/part, say/act, modes, status, per-channel plugin disable, persistent channel list
- **SQLAlchemy database** — Sopel-compatible tables for nick/channel/plugin key-value storage
- **Ignore lists** — `nick_blocks` / `host_blocks` with `@plugin.unblockable` escape hatch
- **Rate limiting & priority** — per-user / channel / global rate limits; high → medium → low dispatch order
- **Built-in example + admin plugins** — ship with the package for a working baseline

---

## Requirements

- Python **3.8** or newer
- **SQLAlchemy** `>=2.0,<3.0` (installed automatically)
- Optional drivers for non-SQLite databases:
  - MySQL/MariaDB: `pip install ibot[mysql]` (pymysql)
  - PostgreSQL: `pip install ibot[postgres]` (psycopg2-binary)

No other runtime packages are required for a standard SSL IRC connection.

---

## Installation

### From a clone (development)

```bash
git clone https://github.com/lord3nd3r/ibot.git
cd ibot

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"     # includes pytest, pytest-asyncio, mypy
# or, runtime only:
pip install -e .
```

### As a library / entry point

After install, the `ibot` console script is available:

```bash
ibot --generate-config mybot.cfg
ibot mybot.cfg
```

Equivalent module form:

```bash
python -m ibot --generate-config mybot.cfg
python -m ibot mybot.cfg
python -m ibot -v mybot.cfg    # debug logging
```

---

## Quick start

```bash
# 1. Generate a starter config
python -m ibot --generate-config mybot.cfg

# 2. Edit server, nick, owner, channels, and auth
nano mybot.cfg

# 3. Run
python -m ibot mybot.cfg
```

Default config sketch (what `--generate-config` writes):

```ini
[core]
nick = ibot
host = irc.libera.chat
port = 6697
use_ssl = true
verify_ssl = true
owner = yournick
channels = #yourchannel
prefix = \.
db_filename = ibot.db

# auth_method = sasl
# auth_user = ibot
# auth_password = yourpassword

# admins = admin1, admin2
# admin_accounts = account1, account2

# extra = /path/to/plugins
# exclude = plugin1, plugin2
# flood_burst = 4
# flood_refill = 1
# logging_level = INFO
```

CLI summary:

| Argument | Meaning |
|----------|---------|
| `config` | Path to INI file (default: `ibot.cfg`) |
| `--generate-config [FILE]` | Write a default config and exit (default file: `ibot.cfg`) |
| `-v` / `--verbose` | Force debug logging (overrides `logging_level`) |

---

## Migrating from Sopel

In many cases you can run ibot **against your existing Sopel config path**:

```bash
python -m ibot ~/.sopel/default.cfg
```

What transfers cleanly:

| Asset | Notes |
|-------|--------|
| **Config INI** | Same `[core]` style options; custom plugin sections via `StaticSection` |
| **SQLite DB** | Same table names and layout; copy the file and set `db_filename` |
| **MySQL / Postgres** | Same schema; use `db_url` or `db_type` + host/user/pass (see below) |
| **Plugin `.py` files** | Put directories in `extra = ...` or `plugins/` next to the config |
| **`from sopel import plugin`** | Resolved by the shim — no package rename required |

What to check after moving:

1. **`prefix`** — Sopel treats this as a regex (e.g. `\.` for a literal dot, `\$` for `$`).
2. **`owner` / `owner_account` / `admins` / `admin_accounts`** — account-based checks need IRCv3 `account-tag` (requested automatically) or extended-join.
3. **`extra` / `enable` / `exclude`** — only **flat** `*.py` files in those directories are loaded (not package plugins or entry points).
4. **Large DB values on MySQL/Postgres** — new installs use unbounded `TEXT` for value columns; existing DBs created with short `VARCHAR` may need a manual migration.
5. **`bot.say(..., max_messages=...)`** — default is **1** message (Sopel-compatible). Pass a higher `max_messages` for multi-chunk replies.

Example config aimed at an existing Sopel scripts tree:

```ini
[core]
nick = glitchy
host = irc.rizon.net
port = 6697
use_ssl = true
owner = YourNick
owner_account = YourAccount
prefix = \$
auth_method = nickserv
auth_password = your_pass
db_filename = glitchy.db
extra = /home/you/sopel-scripts
channels =
    "#channel1"
    "#channel2"
nick_blocks = spammer
host_blocks = *!*@bad.example.com
```

---

## Configuration reference (`[core]`)

All options are read from the INI `[core]` section unless noted. Lists accept multi-line or comma-separated values; channel names may be quoted to protect `#`.

### Connection

| Option | Default | Description |
|--------|---------|-------------|
| `nick` | `ibot` | Nickname |
| `host` | `irc.libera.chat` | Server hostname |
| `port` | `6697` | Server port |
| `use_ssl` | `true` | TLS |
| `verify_ssl` | `true` | Verify TLS certificates |
| `channels` | _(empty)_ | Channels to join on connect |
| `reconnect_on_disconnect` | `true` | Auto-reconnect with backoff |

### Identity & access

| Option | Default | Description |
|--------|---------|-------------|
| `owner` | _(empty)_ | Owner nick (case-insensitive) |
| `owner_account` | _(empty)_ | Owner services account (preferred when set) |
| `admins` | _(empty)_ | Admin nicks |
| `admin_accounts` | _(empty)_ | Admin services accounts |
| `prefix` | `\.` | Command prefix **regex** |
| `help_prefix` | `.` | Display prefix for help-style text |
| `nick_blocks` | _(empty)_ | Nicks to ignore (unless `@unblockable`) |
| `host_blocks` | _(empty)_ | Hostmasks with `*` wildcards to ignore |

### Authentication

| Option | Default | Description |
|--------|---------|-------------|
| `auth_method` | _(empty)_ | `sasl` or `nickserv` |
| `auth_user` | _(empty)_ | SASL username (defaults to nick) |
| `auth_password` | _(empty)_ | Password / SASL secret |
| `auth_target` | `NickServ` | NickServ target when using `nickserv` |

With `auth_method = nickserv`, ibot waits briefly after `IDENTIFY` before joining channels (helps with `+R` / registered-only channels). With `sasl`, capability negotiation includes SASL PLAIN.

### Database

| Option | Default | Description |
|--------|---------|-------------|
| `db_filename` | _(derived)_ | SQLite path (relative to config dir / homedir) |
| `db_type` | `sqlite` | `sqlite`, `mysql`, `postgres`, … |
| `db_url` | _(empty)_ | Full SQLAlchemy URL (overrides type/host pieces) |
| `db_user` / `db_pass` / `db_host` / `db_port` / `db_name` | | Non-SQLite connection fields |
| `db_driver` | _(auto)_ | Optional SQLAlchemy driver override |
| `db_dir` | config homedir | Directory used when resolving relative SQLite paths |

Examples:

```ini
# SQLite (default)
db_filename = ibot.db

# Explicit URL
db_url = postgresql+psycopg2://user:pass@localhost/ibot

# MySQL-style discrete fields
db_type = mysql
db_host = 127.0.0.1
db_user = ibot
db_pass = secret
db_name = ibot
```

### Plugins & logging

| Option | Default | Description |
|--------|---------|-------------|
| `extra` | _(empty)_ | Extra plugin directories |
| `exclude` | _(empty)_ | Plugin basenames to skip |
| `enable` | _(empty)_ | If non-empty, **only** these plugins load |
| `logging_level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, … |
| `flood_burst` | `4` | Token-bucket burst size |
| `flood_refill` | `1` | Tokens refilled per second |

Plugin custom sections use Sopel’s `StaticSection` / attribute descriptors and `bot.config.define_section(...)` / `bot.settings.define_section(...)` in `setup()`.

---

## Plugin directories

Plugins are discovered as **top-level `*.py` files** (names starting with `_` are skipped) from:

1. **Built-in** — `ibot/plugins/` inside the package (`admin`, `example`, …)
2. **`extra`** — each directory listed under `[core] extra`
3. **Config-local** — `plugins/` next to the config file (if present)

Load filters: `exclude` skips names; non-empty `enable` is an allowlist.

Each plugin module may define:

- Decorated callables (`@plugin.command`, `@plugin.rule`, …)
- Optional `setup(bot)` or `setup(settings)`
- Optional `shutdown(bot)`

### Minimal plugin

```python
# plugins/hello.py
from sopel import plugin

@plugin.command('hello')
def hello(bot, trigger):
    """Greet the user."""
    bot.say(f"Hello, {trigger.nick}!")

@plugin.interval(3600)
def hourly(bot):
    # No default destination — pass an explicit target to bot.say()
    pass
```

### Decorators (supported)

| Decorator | Role |
|-----------|------|
| `@command` / `@commands` | Prefix commands (`prefix` + name) |
| `@nickname_command` | `BotNick: command` |
| `@action_command` | CTCP ACTION (`/me`) word commands |
| `@rule` / `@rule_lazy` | Regex on message text (`$nick` / `$nickname` expanded) |
| `@find` / `@find_lazy` | `finditer` matches |
| `@search` / `@search_lazy` | First `search` match |
| `@url` / `@url_lazy` | URL callbacks |
| `@event` | IRC numeric or named events (`JOIN`, `PRIVMSG`, `001`, …) |
| `@interval` | Periodic jobs (seconds); receive `bot` only |
| `@ctcp` / `@intent` | CTCP handlers |
| `@require_admin` / `@require_owner` | Access control |
| `@require_chanmsg` / `@require_privmsg` | Channel vs PM |
| `@require_privilege` / `@require_bot_privilege` | Channel privilege levels |
| `@require_account` | Services account present on trigger |
| `@rate` / `@rate_user` / `@rate_channel` / `@rate_global` | Rate limits |
| `@thread` | Run in a worker thread (default `True`) |
| `@priority` | `high` / `medium` / `low` dispatch order |
| `@unblockable` | Bypass nick/host ignore lists |
| `@allow_bots` | Allow messages tagged/tracked as bots |
| `@echo` | Allow the bot’s own nick as trigger source |
| `@example` / `@output_prefix` / `@label` | Docs / output prefix / rule label |

Privilege constants: `VOICE`, `HALFOP`, `OP`, `ADMIN`, `OWNER`, `OPER` (also on `AccessLevel`).  
Return `plugin.NOLIMIT` from a handler to skip rate-limit accounting for that call.

### Bot object (plugin-facing)

Plugins receive a `SopelWrapper` with:

| API | Notes |
|-----|--------|
| `say(text, destination=None, max_messages=1, truncation=None, trailing=None)` | PRIVMSG; counts newline **and** byte splits toward `max_messages` |
| `reply` / `notice` / `action` / `msg` | Messaging helpers |
| `kick` / `join` / `part` / `quit` / `write` | Channel / connection control |
| `nick`, `settings` / `config`, `db`, `memory` | Core state |
| `channels`, `users` | Live tracking (`Identifier` keys) |
| `has_channel_privilege(channel, level)` | Bot’s privilege in a channel |

### Trigger object

`trigger` is a `str` subclass of the message text, plus:

`nick`, `sender`, `host`, `user`, `hostmask`, `event`, `args`, `tags`, `account`, `admin`, `owner`, `is_privmsg`, `match` / `group` / `groups` / `groupdict`, `urls`, `plain`, `ctcp`, `time`, `raw`, …

### Database API

Tables (Sopel-compatible): `nick_ids`, `nicknames`, `nick_values`, `channel_values`, `plugin_values`.

Common methods:

```text
get/set/delete_nick_value, get_nick_values, alias_nick, unalias_nick,
merge_nick_groups, forget_nick_group, get_nick_id

get/set/delete_channel_value, get_channel_values, forget_channel

get/set/delete_plugin_value, get_plugin_values, forget_plugin

get_nick_or_channel_value, get_preferred_value
```

Values are JSON-serialized. Bulk `get_*_values` returns a `dict` of all keys for that entity.

### Tools modules

```python
from sopel.tools import Identifier, SopelMemory, SopelIdentifierMemory
from sopel.tools import web, time, target, events
from sopel.tools.web import search_urls, quote, unquote, get, decode, iri_to_uri
from sopel.tools.target import User, Channel   # same classes the core tracks
from sopel import formatting, privileges
```

`from sopel.tools import web` and `import sopel.tools.web` refer to the **same** module.

---

## Admin commands

Prefix is your configured `prefix` (examples below use `.`).

| Command | Access | Description |
|---------|--------|-------------|
| `.rehash` | Owner | Reload config from disk and all plugins |
| `.reload <name>` | Owner | Hot-reload one plugin module |
| `.load <name>` | Owner | Load a plugin by basename |
| `.unload <name>` | Owner | Unload a plugin |
| `.plugins` | Owner | List loaded plugins |
| `.bjoin #chan` | Admin | Join a channel (persisted for restart when possible) |
| `.bpart #chan` | Admin | Part a channel (updates persistent list) |
| `.raw <irc line>` | Owner | Send a raw IRC command |
| `.say` / `.msg <target> <text>` | Admin | Send a PRIVMSG |
| `.act <target> <text>` | Admin | Send a CTCP ACTION |
| `.bnick <nick>` | Owner | Change nick |
| `.bmode <channel> <modes> [args]` | Admin | Set channel modes |
| `.bquit` / `.die [reason]` | Owner | Quit |
| `.bstatus` | Admin | Connection / plugin status |
| `.disable <plugin>` | Admin (PM) | Disable a plugin in the current context’s channel store |
| `.enable <plugin>` | Admin (PM) | Re-enable a plugin for a channel |
| `.disabled` | Admin (PM) | List per-channel disabled plugins |

Owner/admin checks use nicks and, when available, services accounts (`owner_account`, `admin_accounts`).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  python -m ibot cfg                                         │
│    load config → install sopel shim → load plugins          │
│    IRCBot (asyncio)  ←→  Dispatcher  ←→  plugin callables   │
└─────────────────────────────────────────────────────────────┘

ibot/
  __main__.py          CLI entry
  bot.py               IRC client: CAP, auth, tracking, flood, intervals
  config.py            Config load / default file generator
  dispatch.py          Match commands/rules/events; filters; rate limits
  loader.py            Shim install + .py plugin discovery
  plugins/
    admin.py           Runtime control
    example.py         Sample commands
  sopel_shim/          Drop-in stand-in for the sopel package
    plugin.py          Decorators & metadata
    bot.py             SopelWrapper (plugin-facing bot)
    trigger.py         PreTrigger / Trigger parsing
    db.py              SQLAlchemy Sopel schema
    config/            CoreSection + StaticSection types
    tools/             Identifier, memory, web, time, target, events
    formatting.py      IRC formatting helpers
    privileges.py      Access level constants
    module.py          Legacy sopel.module re-exports
```

**Request path (PRIVMSG):**

1. `IRCBot` reads a line, handles PING/CAP/tracking, then `dispatcher.dispatch(line)`
2. `PreTrigger` parses tags (unescaped), hostmask, CTCP, URLs
3. Handlers match by type (command, rule, find, URL, CTCP, …), sorted by **priority**
4. Filters: own-nick echo, ignore lists, bot flag, per-channel plugin disable, predicates, rate limits
5. Callable runs in a **daemon thread** by default (`@thread(False)` for sync on the caller path)

**Sopel shim:** `install_sopel_shim()` registers `sopel`, `sopel.plugin`, `sopel.tools`, … in `sys.modules` so third-party plugins keep their imports. If a real Sopel install is present on `sys.path`, the shim still wins once installed at startup.

---

## Known limitations

Honest gaps relative to full Sopel:

| Area | Status |
|------|--------|
| Flat `.py` plugins only | No multi-file packages or setuptools entry-point plugins |
| CAP set | `account-tag`, `extended-join`, `multi-prefix`, `server-time`, optional `sasl` — not full CAP LS shopping cart |
| `@echo` | Filters own nick when seen; does **not** request `echo-message`, so many servers never deliver the bot’s own PRIVMSGs |
| Bot detection | Message `bot` tag and `User.is_bot`; not full bot-mode / WHOX coverage on every network |
| `tools.web.get` | urllib-based GET helper; not a full browser/session stack |
| Casemapping | RFC1459-style `Identifier` folding; does not yet honor `005` CASEMAPPING variants |
| DB migrations | `create_all` only — no automatic ALTER for existing remote schemas |
| Help system | No built-in Sopel `.help` command browser (use examples / your own plugin) |

When a decorator or API is listed as supported above, it is **wired into dispatch or the runtime**, not merely stubbed as metadata.

---

## Testing

```bash
pip install -e ".[dev]"
pytest
# or
python -m pytest tests/ -q
```

Current suite covers config, loader, plugin decorators, dispatcher (lazy rules, NOLIMIT, priority, ignore, bots, echo, account tags), tools/web identity, DB bulk APIs, `say()` limits, and `require_bot_privilege`.

```bash
pytest --cov=ibot --cov-report=html   # if pytest-cov is installed
```

---

## Development

```bash
git clone https://github.com/lord3nd3r/ibot.git
cd ibot
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for PR expectations.

Suggested workflow for plugin work:

1. Put scripts under `./plugins` or an `extra` path
2. Run with `-v` against a test network
3. Use `.reload myplugin` or `.rehash` while connected

---

## Project status

ibot is **1.0.0** — feature-complete enough to call a real release, still **somewhat beta** in spirit. The Sopel compatibility surface is broad and under active use, but edge-case parity with every Sopel release is not guaranteed. Prefer the test suite and a staging network before production cutover.

---

## License

MIT — see [LICENSE](LICENSE).
