[Docs home](../index.md) › Administration › Plugin management

# Plugin management

This page explains where ibot finds plugins, the order it loads them in, how to include or exclude them, how to reload them while the bot is running, and what `.rehash` does and doesn't change.

## In this article

- [Prerequisites](#prerequisites)
- [Plugin search path](#plugin-search-path)
- [What counts as a plugin](#what-counts-as-a-plugin)
- [Load order and name collisions](#load-order-and-name-collisions)
- [Command collisions between plugins](#command-collisions-between-plugins)
- [Choosing which plugins load](#choosing-which-plugins-load)
- [Hot reloading](#hot-reloading)
- [What rehash does](#what-rehash-does)
- [Plugin lifecycle hooks](#plugin-lifecycle-hooks)
- [Using the ibot-plugins collection](#using-the-ibot-plugins-collection)
- [Known issues](#known-issues)
- [See also](#see-also)

## Prerequisites

- Owner access, for `.load`, `.unload`, `.reload`, `.rehash` and `.plugins`.
- Shell access to the bot's host, to add plugin files.

## Plugin search path

The bot works out its plugin directories **once at startup**, in this order:

| # | Directory | Notes |
|---|---|---|
| 1 | `ibot/plugins/` inside the package | Built-in plugins. In this version that's just `admin`. |
| 2 | Each directory in `[core] extra` | `~` is expanded, and relative paths are resolved against the **current working directory**, not the config file. Missing directories log `Plugin directory not found: …` and are skipped. Duplicates are ignored. |
| 3 | `<config file's directory>/plugins` | Used only if it exists |

The resolved list is logged at startup:

```text
2026-10-22 14:03:11 [INFO] ibot: Plugin directories: ['/home/me/ibot/ibot/plugins', '/home/me/.sopel/scripts']
```

> **Note:** Changing `extra` takes effect only after a **restart**. `.rehash`, `.load` and `.reload` reuse the directory list from startup.

## What counts as a plugin

- A single `*.py` file directly in a plugin directory. Subdirectories and package plugins (`myplugin/__init__.py`) are **not** loaded.
- Files whose names start with `_` (e.g. `_helpers.py`) are skipped.
- The plugin **name** is the file name without `.py`. It's used by `.load`, `.reload`, `.unload`, `.disable`, `exclude` and `enable`.
- The module is imported as `ibot_plugins.<name>`.
- A plugin function is any module-level function carrying ibot's decorator marker: `@plugin.command`, `@plugin.rule`, `@plugin.event`, `@plugin.interval`, `@plugin.url`, and so on. See the [Plugin API reference](../developer-guide/plugin-api-reference.md).

> **Warning:** Decorated functions **imported** from another module (`from otherplugin import handler`) also appear at module level, so they're registered **again** under the importing plugin. Import modules, not decorated functions.

## Load order and name collisions

Files are loaded directory by directory, in the search-path order above, and alphabetically within each directory.

| Situation | Result |
|---|---|
| The same plugin name in two directories | The **first** directory wins, and the later file is skipped (debug log `Skipping already loaded plugin`). A built-in `admin.py` therefore can't be overridden. |
| The first copy fails to import | It isn't counted as loaded, so a same-named file in a **later** directory is loaded instead |
| A plugin raises an exception during import | Logged with a traceback (`Failed to load plugin '<name>' from <path>`), and the bot carries on without it |

## Command collisions between plugins

If two plugins register the same command name, handlers are sorted by:

1. Priority: `high`, then `medium` (the default), then `low` (see `@plugin.priority`).
2. Plugin name, alphabetically.
3. Function name, alphabetically.

The **first** command handler whose pattern matches handles the message. No other command handler runs for that message, although rules and other handler types still do.

| Example | Who handles `.status` |
|---|---|
| `alpha.py` and `beta.py` both define `status`, both at default priority | `alpha` |
| `beta.py` uses `@plugin.priority('high')` | `beta` |

> **Warning:** The winning handler is chosen **before** per-channel disabling and permission checks. If the winner is disabled in a channel, or its checks fail, the command simply doesn't run, and the other plugin doesn't get a turn. See [Dispatch](../architecture/dispatch.md#known-limitations).

## Choosing which plugins load

Both keys hold comma-separated plugin names. Matching is **exact and case-sensitive** against file names.

```ini
[core]
# Load everything except these:
exclude = ipython, reddit

# Or: load ONLY these (an empty value means "all")
enable = admin, help, weather
```

| Key | Effect |
|---|---|
| `exclude` | Skip the listed plugins at startup and on `.rehash` |
| `enable` | If non-empty, load **only** the listed plugins. Remember to include `admin`. |

> **Warning:** If you set `enable` and leave out `admin`, the admin plugin doesn't load, and the bot has no runtime management commands at all.

`.load` and `.reload` **ignore** both lists, so the owner can load an excluded plugin by hand.

## Hot reloading

Workflow for editing a plugin while the bot is running:

1. Edit the file, for example `~/.sopel/scripts/weather.py`.
2. Optional: check it for syntax errors first. A failed reload keeps the running version, but checking first saves a round trip:

   ```bash
   python3 -m py_compile ~/.sopel/scripts/weather.py && echo OK
   ```

3. In IRC, as the owner:

   ```text
   .reload weather
   ```

4. Check the reply: `Reloaded weather (2 commands, 0 rules)`.

| Command | Use it when |
|---|---|
| `.reload <name>` | You changed one plugin |
| `.load <name>` | You added a new plugin file |
| `.unload <name>` | You want to switch a plugin off temporarily, for all channels |
| `.disable <name> <#chan>` | You want to switch a plugin off in one channel only (see [Per-channel settings](../configuration/per-channel.md)) |
| `.rehash` | You changed the config file or several plugins |
| Restart | You changed ibot's core code, `extra`, flood or handler-pool settings, `log_raw`/`logdir`, or the database settings |

> **Note:** Reloading only re-imports the plugin file itself. Helper modules that it imports (anything already in `sys.modules`) are **not** re-imported, so restart the bot to pick up changes to those.

## What rehash does

`.rehash` performs these steps, in order:

| Step | Action |
|---|---|
| 1 | Re-read and parse the config file. If parsing fails, it replies `Config reload failed: …` and stops **without changing anything**. |
| 2 | Re-scan the plugin directories (with the new `exclude`/`enable`) and import every plugin. Import failures are collected; those plugins keep running their **current** version. |
| 3 | Swap the new settings into the bot and the dispatcher |
| 4 | Unload plugins that no longer exist or are now excluded: `shutdown(bot)`, then unregister |
| 5 | For each newly imported plugin: old version's `shutdown(bot)` → unregister its handlers and interval jobs → register the new handlers (`$nick` patterns use the current nick) and start its interval jobs → `setup(bot)`. If `setup()` fails, the previous version is put back. |
| 6 | Carry config-section definitions over from the old settings, so plugins kept from before still find their sections |
| 7 | Rebuild the `nick_blocks`/`host_blocks` ignore lists and the `[#channel] disable_plugins` lists |
| 8 | Reload the per-channel `.disable` lists from the database |
| 9 | Report the counts and every import, setup and shutdown error |

What takes effect after a rehash, and what doesn't:

| Setting or state | After `.rehash` |
|---|---|
| `owner`, `owner_account`, `extra_owners`, `admins`, `admin_accounts` | ✅ Applied immediately |
| `prefix`, `help_prefix` | ✅ Applied (command patterns are rebuilt) |
| `exclude`, `enable` | ✅ Applied |
| `[admin]` and other plugin sections | ✅ Applied (read fresh by the plugins) |
| `nick_blocks`, `host_blocks` | ✅ Applied (ignore lists are rebuilt) |
| `[#channel] disable_plugins` | ✅ Applied |
| `extra` (plugin directories) | ❌ Restart required |
| `nick`, `host`, `port`, `use_ssl`, `verify_ssl`, `bind_host`, `user`, `name` | ⏳ Used at the next **reconnect** |
| `channels` | ⏳ Used at the next reconnect. Channels aren't joined or parted right away. |
| `auth_*` | ⏳ At the next reconnect, with exceptions; see [Applying changes](../configuration/overview.md#applying-changes) |
| `flood_*`, `handler_threads`, `handler_queue_size` | ❌ Restart required |
| `db_*` | ❌ Restart required |
| `logging_*`, `log_raw`, `logdir` | ❌ Restart required |
| Interval jobs | ✅ Each reloaded plugin's old jobs are cancelled and its new jobs started |
| `bot.memory` | Kept, not cleared |

> **Note:** "Imported every plugin first" means a plugin whose new file has a syntax error doesn't take the bot down or disappear: it is listed as `<name> import: <error>` and the old code keeps running.

## Plugin lifecycle hooks

| Hook | Called | Argument |
|---|---|---|
| `setup(bot)` | Exactly once per load: after startup registration (**before** connecting), and after each `.load`, `.reload` or `.rehash` of that plugin | A bot wrapper. A `setup()` that takes no parameters is called as `setup()`. |
| `shutdown(bot)` | Before `.reload`/`.unload`, during `.rehash` for each replaced or removed plugin, and at process exit | A bot wrapper |

| Situation | Result |
|---|---|
| `setup()` raises at startup | Logged as `Setup failed for plugin <name>`, the plugin is **unregistered**, and a summary line `N plugin(s) disabled because setup failed: …` is logged |
| `setup()` raises on `.reload`/`.rehash` | The new version is removed and the previous version restored (its `setup()` runs again) |
| `setup()` raises on `.load` | The plugin isn't loaded |
| `shutdown()` raises | Logged as `Shutdown error in plugin <name>` and reported; the unload or swap continues |
| Process exit | `shutdown()` runs for every plugin loaded **at that moment**, including ones added with `.load` or replaced with `.reload` |

## Using the ibot-plugins collection

[lord3nd3r/ibot-plugins](https://github.com/lord3nd3r/ibot-plugins) is the **official ibot plugin collection**, and most of glitchy's features come from it. To use it with any ibot instance:

```bash
git clone https://github.com/lord3nd3r/ibot-plugins.git ~/.sopel/scripts
```

```ini
[core]
extra = ~/.sopel/scripts
```

Then restart the bot. That repository documents each plugin's commands, configuration sections and dependencies in its `docs/` folder and `commands.md`, and that's the place to look for them. These ibot docs don't duplicate that material.

> **Note:** Install the Python dependencies of the plugins you use into the same environment that runs ibot. For the whole collection, that's `pip install requests beautifulsoup4 defusedxml yfinance`. A plugin whose import fails is skipped and logged at startup.

## Known issues

These are behaviours of the current code that you should plan around:

| Issue | Impact | Workaround |
|---|---|---|
| Helper modules aren't re-imported | Changes in a module a plugin imports (anything already in `sys.modules`) need a restart | Restart, or keep helpers inside the plugin file |
| A config-file `[#channel] disable_plugins` entry can't be overridden at runtime | `.enable` doesn't re-enable it, and `.disabled` doesn't list it | Edit the config and `.rehash` |
| `extra` is resolved once at startup | New plugin directories need a restart | Restart |
| Threads a plugin starts itself aren't stopped on unload | They keep running old code | Stop them in `shutdown()` |

## See also

- [Admin commands](admin-commands.md)
- [Writing plugins](../developer-guide/writing-plugins.md)
- [Core reference: extra](../configuration/core-reference.md#extra)
- [Dispatch](../architecture/dispatch.md)

---
[← Back to docs home](../index.md)
