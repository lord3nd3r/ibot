# ibot documentation

This is the documentation for **ibot**, an asyncio IRC bot framework that runs Sopel-compatible plugins. It covers installation, configuration, day-to-day administration, internals and plugin development.

> **Applies to:** ibot 1.0.0 (`ibot/__init__.py`) · Python 3.8+ · SQLAlchemy 2.x
> **Source:** <https://github.com/lord3nd3r/ibot>

## In this article

- [Prerequisites](#prerequisites)
- [Five-minute start](#five-minute-start)
- [How these docs are organized](#how-these-docs-are-organized)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Administration](#administration)
- [Architecture](#architecture)
- [Developer guide](#developer-guide)
- [Reference](#reference)
- [Conventions used in these docs](#conventions-used-in-these-docs)
- [Related projects](#related-projects)
- [See also](#see-also)

## Prerequisites

- A Linux, macOS or other Unix-like host with Python 3.8 or later
- Git
- An IRC network to connect to (the reference deployment uses Rizon)

## Five-minute start

```bash
git clone https://github.com/lord3nd3r/ibot.git ~/ibot
cd ~/ibot
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
python3 -m ibot --generate-config mybot.cfg   # then edit nick, host, channels, owner
python3 -m ibot mybot.cfg -v
```

The full walkthrough is in [Quickstart](getting-started/quickstart.md).

## How these docs are organized

| If you want to… | Start with |
|---|---|
| Install ibot and get a bot online | [Quickstart](getting-started/quickstart.md) |
| Keep a bot running permanently | [Running as a service](getting-started/running-as-a-service.md) |
| Look up a configuration key | [Core reference](configuration/core-reference.md) |
| Control a running bot from IRC | [Admin commands](administration/admin-commands.md) |
| Understand how ibot works inside | [Architecture overview](architecture/overview.md) |
| Write or port a plugin | [Writing plugins](developer-guide/writing-plugins.md) |
| Check whether a Sopel feature works | [Sopel compatibility](developer-guide/sopel-compatibility.md) |
| Fix something that's broken | [Troubleshooting](troubleshooting.md) |

## Getting started

| Page | Summary |
|---|---|
| [Installation](getting-started/installation.md) | System requirements, cloning, virtual environments, optional database drivers, verifying the install |
| [Quickstart](getting-started/quickstart.md) | Generating a config, the first connection, and the first commands |
| [Running as a service](getting-started/running-as-a-service.md) | systemd system and user units, tmux and screen, logs, permissions, running several networks |

## Configuration

| Page | Summary |
|---|---|
| [Configuration overview](configuration/overview.md) | INI syntax, how values are parsed, lists and quoting, literal `%` values, applying changes |
| [Core reference](configuration/core-reference.md) | Every `[core]` key: type, default, whether the core uses it, and examples |
| [Per-channel settings](configuration/per-channel.md) | Startup channels, persistent channels, per-channel plugin disabling |
| [Plugin configuration](configuration/plugin-config.md) | Plugin sections, `StaticSection`, attribute types, environment variable overrides, the `[admin]` section |
| [Authentication](configuration/authentication.md) | SASL PLAIN, NickServ, owner and admin identity |

## Administration

| Page | Summary |
|---|---|
| [Admin commands](administration/admin-commands.md) | All 19 built-in commands and 2 event handlers in the `admin` plugin |
| [Permissions](administration/permissions.md) | Owner, admin, channel privileges, ignore lists, and how checks are evaluated |
| [Plugin management](administration/plugin-management.md) | Plugin directories, load order, `enable`/`exclude`, hot reload, name collisions |

## Architecture

| Page | Summary |
|---|---|
| [Architecture overview](architecture/overview.md) | Components, startup sequence, threading model, diagrams |
| [Connection lifecycle](architecture/connection-lifecycle.md) | TCP/TLS, CAP, SASL, registration, joins, state tracking, reconnects, shutdown |
| [Dispatch](architecture/dispatch.md) | How an incoming line is matched, filtered and handed to a plugin function |
| [Flood control](architecture/flood-control.md) | The outgoing token bucket, message splitting, incoming rate limits |
| [Database](architecture/database.md) | Schema, URL resolution, the key/value API, backends |

## Developer guide

| Page | Summary |
|---|---|
| [Writing plugins](developer-guide/writing-plugins.md) | Step-by-step tutorial: commands, rules, config, storage, intervals, permissions |
| [Plugin API reference](developer-guide/plugin-api-reference.md) | Every decorator, `bot` method, `trigger` attribute and `bot.db` method |
| [Sopel compatibility](developer-guide/sopel-compatibility.md) | The compatibility matrix and porting notes |
| [Tools reference](developer-guide/tools-reference.md) | `sopel.tools`, `tools.web`, `tools.time`, `formatting`, `privileges`, `events` |
| [Testing](developer-guide/testing.md) | Running the suite, writing tests with a fake bot, current status |

## Reference

| Page | Summary |
|---|---|
| [Security](security.md) | The trust model, secrets on disk, log redaction, SSRF and injection protections, a hardening checklist, known gaps |
| [Troubleshooting](troubleshooting.md) | Common problems and how to fix them |
| [FAQ](faq.md) | Short answers to common questions |
| [Glossary](glossary.md) | IRC and ibot terminology |
| [Changelog](changelog.md) | Release and commit history |
| [Contributing](../CONTRIBUTING.md) | How to contribute (repository root) |
| [README](../README.md) | Project overview (repository root) |

## Conventions used in these docs

- **Command prefix.** Examples use `.` because that is the default (`prefix = \.`). If your bot uses another prefix, substitute it. The `glitchy` deployment uses `$`, for example `$bstatus`.
- **Placeholders.** Values such as `YOUR_PASSWORD_HERE`, `YourNick` and `#yourchannel` must be replaced with your own. Never paste real secrets into documentation, issues or IRC.
- **Callouts.**
  > **Note:** Extra information that is useful but not critical.

  > **Warning:** Something that can cause outages, data loss or a security problem.
- **"Parsed but not used".** Some configuration keys are recognised by the config layer (for Sopel compatibility) but the ibot core never reads them. The [Core reference](configuration/core-reference.md) marks these keys explicitly.
- **Code references.** Paths such as `ibot/bot.py` are relative to the repository root.

## Related projects

| Project | Relationship |
|---|---|
| [Sopel](https://sopel.chat/) | The upstream bot whose plugin API ibot implements |
| [lord3nd3r/sopel-scripts](https://github.com/lord3nd3r/sopel-scripts) | Plugin collection used by the `glitchy` deployment, with its own `docs/` and `commands.md` |

## See also

- [Project README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [ibot on GitHub](https://github.com/lord3nd3r/ibot)

---
[← Back to docs home](index.md) · [Project README](../README.md)
