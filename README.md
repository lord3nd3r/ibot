# ibot

**ibot** is a small asyncio IRC bot framework that runs **[Sopel](https://sopel.chat/) plugins** with little or no modification. A compatibility shim sits in front of your plugins, so `from sopel import plugin` works without Sopel being installed.

ibot is not a fork of Sopel. It has its own IRC client core (`ibot.bot`), its own dispatcher (`ibot.dispatch`), and a reimplementation of the Sopel plugin API (`ibot.sopel_shim`). That shim is registered in `sys.modules` as `sopel` at startup.

| | |
|---|---|
| **Version** | 1.0.0 (`ibot/__init__.py`), described by the project as "stable-ish / somewhat beta" |
| **Python** | `requires-python >= 3.8` (production deployment runs Python 3.13) |
| **Runtime dependency** | [SQLAlchemy](https://www.sqlalchemy.org/) `>=2.0,<3.0` |
| **License** | MIT. See [LICENSE](LICENSE) |
| **Repository** | <https://github.com/lord3nd3r/ibot> |
| **Maintainer** | lord3nd3r (IRC: `End3r`) |
| **Reference deployment** | `glitchy` on Rizon, which loads plugins from [lord3nd3r/sopel-scripts](https://github.com/lord3nd3r/sopel-scripts) |

---

## In this article

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Command-line usage](#command-line-usage)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [Sopel compatibility at a glance](#sopel-compatibility-at-a-glance)
- [Plugin collection: sopel-scripts](#plugin-collection-sopel-scripts)
- [Running the tests](#running-the-tests)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Runs Sopel plugins.** Supports the Sopel decorators (`@plugin.command`, `@plugin.rule`, `@plugin.event`, `@plugin.interval`, `@plugin.url`, `@plugin.ctcp`, the `require_*` family, the `rate*` family, `@plugin.priority` and others), plus the `bot`, `trigger`, `bot.db` and `bot.config` objects and the commonly used `sopel.tools` modules.
- **asyncio IRC core.** TLS with optional certificate verification, SASL PLAIN or NickServ `IDENTIFY` authentication, automatic reconnects with exponential backoff (5 s up to 300 s, reset after each successful registration), a keepalive `PING` after 240 s of silence, and nick fallback with NickServ `GHOST` regain.
- **IRCv3.** Negotiates with `CAP LS 302` and requests whichever of `account-tag`, `extended-join`, `multi-prefix` and `server-time` the server offers, plus `sasl` when SASL is configured.
- **Safe by default.** Outgoing lines are stripped of CR/LF/NUL and length-capped, credentials are redacted from debug and raw logs, `tools.web.get()` refuses private addresses and caps response size, and plugin handlers run on a bounded thread pool. See [Security](docs/security.md).
- **State tracking.** Keeps track of channels, users, channel privileges (`+v +h +o +a +q`), topics and services accounts.
- **Outgoing flood control.** A token bucket (`flood_burst`, `flood_refill`) applies to all plugin output.
- **Sopel-compatible database.** Uses SQLAlchemy with Sopel's table layout (`nick_ids`, `nicknames`, `nick_values`, `channel_values`, `plugin_values`). SQLite is the default; MySQL/MariaDB, PostgreSQL and other engines work through a URL.
- **Hot reload.** `rehash` reloads the config and every plugin, and `load`/`unload`/`reload` handle single plugins, all without dropping the IRC connection. New code is imported first; if it fails to import or set up, the previous version keeps running.
- **Built-in admin plugin.** Covers joining and parting channels (persisted in the database), say/act/raw/mode/nick/quit, status, and per-channel plugin disabling (persisted).
- **Ignore lists and rate limits.** `nick_blocks` and `host_blocks` (the `*` wildcard is supported). Per-user, per-channel and global rate limits are available, and admins can be exempted.

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.8 or newer | Declared in `pyproject.toml`. Python 3.13 is used in production. |
| SQLAlchemy 2.x | Installed automatically (`sqlalchemy>=2.0,<3.0`) |
| Network access to an IRC server | TLS on port 6697 is the default |
| *Optional:* `pymysql` | `pip install -e ".[mysql]"` for MySQL/MariaDB |
| *Optional:* `psycopg2-binary` | `pip install -e ".[postgres]"` for PostgreSQL |
| *Optional (development):* `pytest`, `pytest-asyncio`, `mypy` | `pip install -e ".[dev]"` |

## Quick start

```bash
git clone https://github.com/lord3nd3r/ibot.git
cd ibot
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# 1. Write a starter config
python -m ibot --generate-config mybot.cfg
chmod 600 mybot.cfg

# 2. Edit nick, host, owner, channels, prefix and authentication
${EDITOR:-nano} mybot.cfg

# 3. Run in the foreground with debug logging
python -m ibot mybot.cfg -v
```

Then, in a channel the bot has joined (default prefix is `.`):

```text
<you>   .bstatus
<mybot> Nick: mybot | Channels: 1 | Plugins: 1 | Commands: 19 | Rules: 0 | Events: 2
```

> **Note:** `.bstatus` works for the owner and for admins. The full walkthrough is in [Quickstart](docs/getting-started/quickstart.md).

## Command-line usage

```text
usage: ibot [-h] [--generate-config [FILE]] [-v] [config]
```

| Argument | Default | Description |
|---|---|---|
| `config` | `ibot.cfg` | Path to the INI configuration file |
| `--generate-config [FILE]` | `ibot.cfg` when no file is named | Writes a starter config and exits. An existing file is never overwritten. |
| `-v`, `--verbose` | off | Turns on `DEBUG` logging, including raw `>>>`/`<<<` IRC traffic |
| `-h`, `--help` | | Shows help |

The `ibot` console script (`ibot = ibot.__main__:main`) is equivalent to `python -m ibot`.

## Project layout

```text
ibot/
├── ibot/
│   ├── __init__.py          # __version__ = '1.0.0'
│   ├── __main__.py          # CLI entry point, startup sequence, setup()/shutdown() hooks
│   ├── bot.py               # IRCBot: connection, CAP/SASL, tracking, flood queue, intervals
│   ├── config.py            # load_config(), create_default_config()
│   ├── dispatch.py          # Dispatcher, HandlerPool, RateLimitTracker
│   ├── loader.py            # install_sopel_shim(), load_plugins(), reload_plugin_live(), rehash_live()
│   ├── plugins/
│   │   └── admin.py         # Built-in administration plugin
│   └── sopel_shim/          # Installed as the `sopel` package at runtime
│       ├── plugin.py        # Decorators and privilege constants
│       ├── bot.py           # SopelWrapper (the `bot` passed to plugins)
│       ├── trigger.py       # PreTrigger / Trigger
│       ├── db.py            # SopelDB (SQLAlchemy models + key/value API)
│       ├── config/          # Config, CoreSection, StaticSection and attribute types
│       ├── tools/           # Identifier, SopelMemory, web, time, target, events
│       ├── formatting.py    # IRC colour/formatting helpers
│       ├── privileges.py    # AccessLevel constants
│       ├── target.py        # sopel.tools.target re-exports
│       └── module.py        # legacy `sopel.module` aliases
├── tests/                   # pytest suite
├── docs/                    # This documentation set
├── pyproject.toml / setup.py / requirements.txt
├── CONTRIBUTING.md
└── LICENSE
```

## Documentation

All documentation is under [`docs/`](docs/index.md).

| Area | Page | What it covers |
|---|---|---|
| Start here | [Documentation home](docs/index.md) | Map of the docs set |
| Getting started | [Installation](docs/getting-started/installation.md) | Installing from source, virtual environments, optional DB drivers |
| | [Quickstart](docs/getting-started/quickstart.md) | Getting from nothing to a connected bot in ten minutes |
| | [Running as a service](docs/getting-started/running-as-a-service.md) | systemd units, tmux/screen, logging, file permissions |
| Configuration | [Configuration overview](docs/configuration/overview.md) | File format, parsing rules, lists, booleans, reloading |
| | [Core reference](docs/configuration/core-reference.md) | Every `[core]` key with its type, default and effect |
| | [Per-channel settings](docs/configuration/per-channel.md) | Channel lists, persistent channels, per-channel plugin disabling |
| | [Plugin configuration](docs/configuration/plugin-config.md) | `StaticSection`, attribute types, environment overrides, `[admin]` |
| | [Authentication](docs/configuration/authentication.md) | SASL PLAIN, NickServ, owner and admin identity |
| Administration | [Admin commands](docs/administration/admin-commands.md) | Every built-in command, with syntax, permission and output |
| | [Permissions](docs/administration/permissions.md) | Owner, admin, channel privileges, ignore lists |
| | [Plugin management](docs/administration/plugin-management.md) | Plugin discovery, enable/exclude, hot reload |
| Architecture | [Architecture overview](docs/architecture/overview.md) | Components and data flow (with diagrams) |
| | [Connection lifecycle](docs/architecture/connection-lifecycle.md) | Connect, CAP, SASL, registration, joins, reconnect, shutdown |
| | [Dispatch](docs/architecture/dispatch.md) | How a line becomes a handler call |
| | [Flood control](docs/architecture/flood-control.md) | Outgoing token bucket and incoming rate limits |
| | [Database](docs/architecture/database.md) | Schema, URL resolution, key/value API |
| Developer guide | [Writing plugins](docs/developer-guide/writing-plugins.md) | Tutorial that builds a full plugin step by step |
| | [Plugin API reference](docs/developer-guide/plugin-api-reference.md) | Decorators, `bot`, `trigger`, `bot.db`, config |
| | [Sopel compatibility](docs/developer-guide/sopel-compatibility.md) | What matches Sopel, what differs, and what is missing |
| | [Tools reference](docs/developer-guide/tools-reference.md) | `sopel.tools`, `web`, `time`, `formatting`, `privileges` |
| | [Testing](docs/developer-guide/testing.md) | Running and writing tests |
| Reference | [Security](docs/security.md) | Hardening guidance and known risks |
| | [Troubleshooting](docs/troubleshooting.md) | Symptoms, causes, fixes |
| | [FAQ](docs/faq.md) | Frequently asked questions |
| | [Glossary](docs/glossary.md) | Terms used in these docs |
| | [Changelog](docs/changelog.md) | History compiled from the git log |

## Sopel compatibility at a glance

| Area | Status |
|---|---|
| `from sopel import plugin` / `sopel.module` | ✅ Shimmed |
| Commands, nickname commands, action commands, rules, find, search, URL, events, CTCP, intervals | ✅ Wired into dispatch |
| `require_admin` / `require_owner` / `require_chanmsg` / `require_privmsg` / `require_account` / `require_privilege` / `require_bot_privilege` | ✅ |
| `rate`, `rate_user`, `rate_channel`, `rate_global`, `NOLIMIT` | ✅ (see the caveats in [Flood control](docs/architecture/flood-control.md)) |
| `thread`, `priority`, `unblockable`, `allow_bots`, `echo`, `output_prefix` | ✅ |
| `example`, `label` | ⚠️ Stored as metadata only. ibot has no built-in help command. |
| `bot.say/reply/notice/action/msg/kick/join/part/quit/write` | ✅ |
| `bot.db` (nick/channel/plugin values, aliases) | ✅ Same schema as Sopel |
| `StaticSection` + `ValidatedAttribute` / `ListAttribute` / `ChoiceAttribute` / … | ✅ (validation isn't enforced at load time) |
| Package plugins and entry-point plugins | ❌ Only flat `*.py` files are loaded |
| `bot.restart()`, `bot.reload_plugin()` | ✅ |
| `bot.isupport` | ⚠️ A plain `dict` (through the core-bot fallback), not Sopel's `ISupport` object |
| `bot.has_plugin()`, `bot.capabilities`, `bot.privileges`, `bot.hostmask` | ❌ Not present |

The full matrix, with every known difference, is on the [Sopel compatibility](docs/developer-guide/sopel-compatibility.md) page.

## Plugin collection: sopel-scripts

ibot ships with a single built-in plugin, `admin`. The plugins used by the `glitchy` deployment are in a separate repository, **[lord3nd3r/sopel-scripts](https://github.com/lord3nd3r/sopel-scripts)**, which has its own per-plugin documentation (`docs/`) and a command reference (`commands.md`). It includes AI chat (multi-backend), moderation (anti-flood, anti-spam, auto-op/voice, oper scanning), games and economy (trivia, hunt, mug, beer), and utilities (weather, stock, wiki, seen, tell, quotes, polls, URL and YouTube titles, feeds, channel statistics). To use them, point `[core] extra` at a checkout. See [Plugin management](docs/administration/plugin-management.md).

## Running the tests

```bash
pip install -e ".[dev]"
python -m pytest -q
```

See [Testing](docs/developer-guide/testing.md) for the current state of the suite.

## Contributing

Bug reports and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

ibot is released under the [MIT License](LICENSE).
