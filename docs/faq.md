[Docs home](index.md) › FAQ

# Frequently asked questions

Short answers to common questions about ibot, with links to the full documentation.

## In this article

- [Prerequisites](#prerequisites)
- [General](#general)
- [Configuration](#configuration)
- [Administration](#administration)
- [Plugins](#plugins)
- [Operations](#operations)
- [See also](#see-also)

## Prerequisites

None. This page is a starting point.

## General

### What is ibot?

ibot is an IRC bot framework written in Python with `asyncio`. It loads plugins written for [Sopel](https://sopel.chat/) by providing its own `sopel` package. It stores data in a Sopel-schema SQL database through SQLAlchemy. See the [Architecture overview](architecture/overview.md).

### Is ibot a fork of Sopel?

No. It's a separate implementation that imitates Sopel's plugin API. Sopel itself doesn't need to be installed. If it is, ibot's shim replaces it in `sys.modules` before plugins load, so plugins always get ibot's version. Submodules the shim doesn't provide fail to import. See [Sopel compatibility](developer-guide/sopel-compatibility.md).

### Which Python versions are supported?

`pyproject.toml` requires Python 3.8 or later. The reference deployment runs Python 3.13 with SQLAlchemy 2.0.

### Is it production-ready?

Version 1.0.0 is described in the README as "stable-ish / somewhat beta".

> **Note:** The reference bot `glitchy` runs on ibot full-time on Rizon, but the test suite currently has 3 failing tests. See [Testing](developer-guide/testing.md#current-test-status).

 Read the "Known limitations" sections, particularly in [Connection lifecycle](architecture/connection-lifecycle.md#known-limitations) and [Dispatch](architecture/dispatch.md#known-limitations).

### Can one process connect to several networks?

No. One process handles one connection. Run one process per network, each with its own config and database. See [Running as a service](getting-started/running-as-a-service.md).

## Configuration

### Where do I get a config file?

Run `python3 -m ibot --generate-config mybot.cfg`. The older `default.cfg` was removed from the repository. See [Quickstart](getting-started/quickstart.md).

### Why doesn't `prefix = $` work?

The prefix is a regular expression, and `$` means end of line. Use `prefix = \$`. See [`prefix`](configuration/core-reference.md#prefix).

### Can I use my existing Sopel config?

Mostly. ibot reads `[core]` keys with Sopel's names, and plugin sections are unchanged. Some Sopel keys are ignored. The [Core reference](configuration/core-reference.md) marks each one.

### How do I keep passwords out of the config file?

Plugin settings declared with `StaticSection` can be overridden with environment variables. `[core]` keys can't. See [Plugin configuration](configuration/plugin-config.md) and [Keeping secrets out of the file](configuration/overview.md#keeping-secrets-out-of-the-file).

### Do I need to restart after editing the config?

Often not:

| You changed | Apply with |
|---|---|
| Plugin sections, `prefix`, owner/admin lists, `exclude`/`enable` | `.rehash` |
| Plugin code | `.reload name` |
| `extra`, `nick_blocks`, `host_blocks`, `flood_*`, `db_*` | Restart |

See [Applying changes](configuration/overview.md#applying-changes).

## Administration

### How do I make myself the owner?

Set `owner_account` to your services account name, and optionally `owner` to your nick, then restart. See [Permissions](administration/permissions.md).

### The bot ignores `.reload`. Why?

`.reload` is owner-only, and permission failures are silent. See [The bot ignores my admin commands](troubleshooting.md#the-bot-ignores-my-admin-commands).

### How do I turn a plugin off in one channel?

Send the bot a private message: `.disable #channel pluginname`. It's stored in the database and survives restarts. The `admin` plugin can't be disabled. See [Per-channel settings](configuration/per-channel.md).

### How do I make the bot join a channel permanently?

Add it to `[core] channels`, or use `.bjoin #channel`, which saves it in the database. See [Admin commands](administration/admin-commands.md#bjoin).

### Is there a help command?

ibot has no built-in help command. Help is provided by plugins, for example the `commands` plugin in ibot-plugins, the official ibot plugin collection. See [Using the ibot-plugins collection](administration/plugin-management.md#using-the-ibot-plugins-collection).

## Plugins

### Where do plugins go?

Into a directory listed in `[core] extra` (for example `extra = ~/.sopel/scripts`), or into a `plugins/` directory next to the config file. The built-in `ibot/plugins/` directory is searched first. ibot doesn't search `~/.sopel/plugins` automatically. Changing `extra` needs a restart. See [Plugin search path](administration/plugin-management.md#plugin-search-path).

### Will my Sopel plugin work?

Most single-file plugins using decorators, `bot.say`/`reply`, `bot.db`, `bot.memory` and config sections work unchanged. Check the [support matrix](developer-guide/sopel-compatibility.md#support-matrix) and the [porting checklist](developer-guide/sopel-compatibility.md#porting-checklist).

### Why does only one of my two `.foo` commands run?

ibot runs only the **first** matching command handler. See [Dispatch: known limitations](architecture/dispatch.md#known-limitations).

### Can I reload a plugin without restarting?

Yes: `.reload name` (owner). The new file is imported first; if the import or its `setup()` fails, the previous version keeps running. The plugin's interval jobs are cancelled and restarted with the new code. See [Hot reloading](administration/plugin-management.md#hot-reloading).

### How do I test a plugin without connecting to IRC?

Drive the dispatcher with a fake bot. See [Testing](developer-guide/testing.md#unit-testing-a-plugin).

## Operations

### Does ibot reconnect by itself?

Yes, when `reconnect_on_disconnect = true` (the default). The delay starts at 5 s, doubles up to 300 s, and resets to 5 s after a successful registration. A dead link is detected by a keepalive `PING` after 240 s of silence. See [Reconnects](architecture/connection-lifecycle.md#reconnects).

### Does ibot daemonize or write a PID file?

No. Run it under systemd, tmux or screen. See [Running as a service](getting-started/running-as-a-service.md).

### Where are the logs?

On standard error. Redirect them, or let systemd's journal collect them. `-v` turns on debug logging. See [Logging and privacy](security.md#logging-and-privacy).

### How do I back up the bot?

Back up the config file and the database. For SQLite, use the online backup command, which is safe while the bot is running:

```bash
sqlite3 bot.db ".backup bot-backup.db"
cp bot.cfg bot-backup.cfg && chmod 600 bot-backup.cfg
```

> **Warning:** Backup copies of the config contain your passwords. A name like `bot-backup.cfg` matches `.gitignore`, but `bot.cfg.bak` doesn't. See [Protecting secrets on disk](security.md#protecting-secrets-on-disk).

See [Database](architecture/database.md).

## See also

- [Troubleshooting](troubleshooting.md)
- [Glossary](glossary.md)

---
[← Back to docs home](index.md)
