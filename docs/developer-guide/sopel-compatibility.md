[Docs home](../index.md) › Developer guide › Sopel compatibility

# Sopel compatibility

ibot runs most Sopel 7/8 plugins without changes, by putting a compatibility package named `sopel` into `sys.modules`. This page lists what's supported, where the behaviour differs from Sopel, what's missing, and how to port a plugin that doesn't work straight away.

## In this article

- [Prerequisites](#prerequisites)
- [How the shim works](#how-the-shim-works)
- [Support matrix](#support-matrix)
- [Behavioural differences](#behavioural-differences)
- [Not supported](#not-supported)
- [Porting checklist](#porting-checklist)
- [Coexisting with a real Sopel install](#coexisting-with-a-real-sopel-install)
- [See also](#see-also)

## Prerequisites

- A Sopel plugin you want to run
- [Writing plugins](writing-plugins.md), for the ibot basics

## How the shim works

1. Before any plugin is imported, `ibot.loader.install_sopel_shim()` registers `ibot.sopel_shim` and its submodules under the `sopel.*` names. See [Plugin API reference: importable modules](plugin-api-reference.md#importable-modules).
2. Plugins are imported as `ibot_plugins.<name>` from the configured directories.
3. Decorators store their metadata as function attributes, and mark the function with `_ibot_plugin`.
4. The loader scans each module's functions for that marker. The dispatcher compiles the patterns and routes lines to them.

> **Note:** The shim **replaces** any installed `sopel` package inside the ibot process. You don't need Sopel installed, and an installed Sopel isn't used.

A typical Sopel plugin header works unchanged. This one was tested against the shim:

```python
from sopel import plugin, tools, formatting
from sopel.config import types
from sopel.tools import web
from sopel.tools.time import parse_duration


class MySection(types.StaticSection):
    api_key = types.SecretAttribute('api_key')


def setup(bot):
    bot.config.define_section('mything', MySection)
```

Importing a name the shim doesn't provide fails at load time, for example:

```text
2026-10-22 14:03:11 [ERROR] ibot.loader: Failed to execute plugin module 'compat': cannot import name 'seconds_to_human' from 'ibot.sopel_shim.tools.time'
```

## Support matrix

| Feature | Status | Notes |
|---|---|---|
| `@plugin.command`, `commands`, `nickname_command(s)`, `action_command(s)` | ✅ | |
| `@plugin.rule`, `find`, `search`, `url`, and their `_lazy` versions | ✅ | Rule patterns are case-insensitive (and `re.VERBOSE` when multi-line), as in Sopel |
| `@plugin.event`, `ctcp`, `intent`, `interval` | ✅ | See the differences below |
| `require_*` decorators | ✅ | |
| `rate`, `rate_user`, `rate_channel`, `rate_global`, `NOLIMIT` | ✅ | The message isn't formatted |
| `thread`, `priority`, `unblockable`, `allow_bots`, `echo`, `output_prefix`, `example`, `label` | ✅ | `example` and `label` are metadata only |
| `bot.say/reply/notice/action/msg/write/join/part/kick/quit/restart` | ✅ | `restart()` re-executes the process |
| `bot.db` (the Sopel schema) | ✅ | Existing Sopel databases work |
| `bot.memory`, `bot.channels`, `bot.users` | ✅ | |
| `config.types` sections (`StaticSection`, `ValidatedAttribute`, `ListAttribute`, …) | ✅ | See [Plugin configuration](../configuration/plugin-config.md) |
| `setup(bot)` / `shutdown(bot)` | ✅ | Each called exactly once per load/unload |
| `sopel.formatting` | ✅ | `colors` are integers |
| `sopel.tools.web`, `time`, `events`, `target`, `identifiers` | ⚠️ Partial | See [Tools reference](tools-reference.md) |
| `configure(config)` / the `sopel configure` wizard | ❌ | |
| `bot.privileges`, `bot.hostmask`, `bot.server_capabilities` | ❌ | Use `bot.channels[chan].privileges` |
| `bot.isupport` | ⚠️ | Reached through the core-bot fallback. A plain `dict` of token → string, not Sopel's `ISupport` object, so `bot.isupport.NICKLEN` doesn't work; use `bot.isupport.get('NICKLEN')` |
| `bot.register_url_callback` / `bot.search_url_callbacks` | ❌ | Use `@plugin.url` |
| Packages and entry-point plugins (`sopel.plugins` API) | ❌ | Single `.py` files only |
| `sopel.irc`, `sopel.plugins.exceptions` contents | ❌ | Empty stub modules |
| Plugin help (`.help`, built from docstrings and `@example`) | ❌ | No help plugin is included |

## Behavioural differences

| Area | Sopel | ibot |
|---|---|---|
| Several command handlers with the same name | All matching handlers run | **Only the first, in sort order.** If that one is filtered out, none of them runs. |
| A line that starts with a command | Rules and URL callbacks still see it | **Command lines stop dispatch.** No rules, find, search or URL callbacks run. |
| `@event` + `@rule` together | The rule is applied to lines of that event | The function runs for every line of that event, **and** for PRIVMSGs matching the rule |
| Rate-limit `message` | A template (`{time_left}`, …) | Sent literally, as a NOTICE |
| `setup()` failure | The plugin isn't loaded | The plugin is unregistered at startup and on `.load`; on `.reload`/`.rehash` the previous version is restored |
| `colors.*` | `'04'` (str) | `4` (int) |
| `trigger.status_prefix` | Parsed | Always `None` |
| `reply()` with `output_prefix` | The prefix once | The prefix twice |
| Per-channel disabling | `[#chan] disable_plugins` / `disable_commands` in the config | `[#chan] disable_plugins` is supported; `disable_commands` isn't read. ibot adds runtime `.disable`/`.enable`, stored in the database. See [Per-channel settings](../configuration/per-channel.md). |
| Owner check | Owner nick + account | `owner_account` if the user's account is known, otherwise the owner nick; plus `extra_owners` (account or nick) |
| `require_privilege` | Admins aren't exempt | Admins pass in channels |

## Not supported

Beyond the items marked ❌ in the [support matrix](#support-matrix):

- Sopel CLI subcommands (`sopel start/stop/restart/configure/plugins`). ibot's command line is `python3 -m ibot [config] [-v] [--generate-config [FILE]]`, or the `ibot` console script when it's installed with pip. See [Quickstart](../getting-started/quickstart.md).
- The PID file and daemonisation. Use a process supervisor. See [Running as a service](../getting-started/running-as-a-service.md).
- Sopel's regex semantics for ignore lists. In ibot, `nick_blocks` entries are exact nicks, and `host_blocks` entries are `*`-wildcard hostmasks matched against the full `nick!user@host`. See the [Core reference](../configuration/core-reference.md#nick_blocks).
- Many Sopel `[core]` keys, such as the logging keys, are accepted but have no effect. The [Core reference](../configuration/core-reference.md) marks the status of every key.

## Porting checklist

1. **Copy** the file into a plugin directory and run `.load <name>`. Watch the log with `-v`.
2. **ImportError for `sopel.x`?** The module doesn't exist in the shim. Replace it with the standard library or your own helper.
3. **AttributeError on `bot.x`?** The wrapper forwards unknown public names to ibot's core bot, so an `AttributeError` means neither has that attribute (names starting with `_` are never forwarded). Use the [bot object API](plugin-api-reference.md#the-bot-object), or go through `bot.channels`/`bot.users`.
4. **The command never answers?** Look for a command with the same name in another plugin (`grep -rn "command('name'" <dirs>`).
5. **The URL or rule handler never fires?** Check whether the test line starts with the command prefix.
6. **Output is cut off?** Pass `max_messages` to `say()`.
7. **Is it a package plugin (a directory with `__init__.py`)?** Flatten it into one file, or put the helper modules somewhere on `PYTHONPATH`.
8. **Does it use the `{time_left}`-style rate message?** Change it to fixed text.

## Coexisting with a real Sopel install

Plugins in `~/.sopel/scripts` can be shared with a real Sopel instance. Point `[core] extra` at that directory. Avoid running both bots with the **same database file** at the same time.

## See also

- [Plugin API reference](plugin-api-reference.md)
- [Tools reference](tools-reference.md)
- [Dispatch](../architecture/dispatch.md)
- [sopel-scripts](https://github.com/lord3nd3r/sopel-scripts)

---
[← Back to docs home](../index.md)
