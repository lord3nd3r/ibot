[Docs home](../index.md) › Administration › Admin commands

# Admin command reference

This page documents every command in ibot's built-in `admin` plugin (`ibot/plugins/admin.py`): syntax, who may run it, where it works, exactly what the bot replies, and any caveats. It also documents the plugin's two automatic event handlers.

## In this article

- [Prerequisites](#prerequisites)
- [Conventions](#conventions)
- [Command summary](#command-summary)
- [Plugin lifecycle](#plugin-lifecycle): [rehash](#rehash) · [reload](#reload) · [load](#load) · [unload](#unload) · [plugins](#plugins)
- [Channels](#channels): [bjoin](#bjoin) · [bpart](#bpart)
- [Messaging and raw IRC](#messaging-and-raw-irc): [say / msg](#say--msg) · [act](#act) · [raw](#raw)
- [Bot control](#bot-control): [bnick](#bnick) · [bmode](#bmode) · [bquit / die](#bquit--die) · [bstatus](#bstatus)
- [Per-channel plugin control](#per-channel-plugin-control): [disable](#disable) · [enable](#enable) · [disabled](#disabled)
- [Automatic behaviour](#automatic-behaviour): [Kick rejoin](#kick-rejoin-hold_ground) · [Invite accept](#invite-accept-auto_accept_invite)
- [See also](#see-also)

## Prerequisites

- The `admin` plugin is loaded. It always is, unless `[core] enable` is set without `admin` in it.
- You're the owner or an admin as defined in [Permissions](permissions.md).

## Conventions

- Examples use the default prefix `.`. On glitchy, type `$` instead (`$bstatus`), because its prefix is `\$`.
- The bot's own usage messages **always** show `.`, whatever the configured prefix.
- `<x>` is required and `[x]` is optional.
- Command names are case-insensitive (`.BSTATUS` works).
- "Denied" shows what a user without permission sees. *(silent)* means the bot doesn't reply at all.
- Replies go to wherever the command was typed: the channel, or the private query.

## Command summary

| Command | Aliases | Permission | Where | Purpose |
|---|---|---|---|---|
| [`rehash`](#rehash) | | Owner | Anywhere | Reload the config file and all plugins |
| [`reload`](#reload) | | Owner | Anywhere | Reload one plugin from disk |
| [`load`](#load) | | Owner | Anywhere | Load a plugin that isn't loaded |
| [`unload`](#unload) | | Owner | Anywhere | Unload a plugin |
| [`plugins`](#plugins) | | Owner | Anywhere | List loaded plugins |
| [`bjoin`](#bjoin) | | Admin | Anywhere | Join a channel and remember it |
| [`bpart`](#bpart) | | Admin | Anywhere | Part a channel and forget it |
| [`say`](#say--msg) | `msg` | Admin | Anywhere | Send a message to a nick or channel |
| [`act`](#act) | | Admin | Anywhere | Send a `/me` action |
| [`raw`](#raw) | | Owner | Anywhere | Send a raw IRC line |
| [`bnick`](#bnick) | | Owner | Anywhere | Show or change the bot's nick |
| [`bmode`](#bmode) | | Admin | Anywhere | Send a `MODE` command |
| [`bquit`](#bquit--die) | `die` | Owner | Anywhere | Quit IRC and stop the process |
| [`bstatus`](#bstatus) | | Admin | Anywhere | Show the nick, counts of channels, plugins and handlers |
| [`disable`](#disable) | | Admin | **PM only** | Disable a plugin in a channel |
| [`enable`](#enable) | | Admin | **PM only** | Re-enable a plugin in a channel |
| [`disabled`](#disabled) | | Admin | **PM only** | List disabled plugins |

That's 17 functions and 19 command names (`msg` and `die` are aliases).

> **Note:** ibot doesn't have a built-in `help` command. Help comes from a plugin, such as the `commands` plugin (`help`, `commands`, `cmds`) in [ibot-plugins](https://github.com/lord3nd3r/ibot-plugins), the official ibot plugin collection.

---

## Plugin lifecycle

### rehash

Reload the config file from disk and bring every plugin up to date with it, keeping the bot running. In order:

1. Re-read the config file. If it can't be parsed, stop here: nothing is changed.
2. Re-scan the plugin directories (applying `exclude`/`enable`) and **import every plugin first**. A plugin whose new code fails to import keeps running its current version.
3. Unload plugins that are gone or now excluded (their `shutdown()` runs).
4. For every other plugin: run the old version's `shutdown()`, swap in the new handlers, run the new `setup()`. If the new `setup()` fails, the previous version is restored.
5. Rebuild the ignore lists and the `[#channel] disable_plugins` lists, then reload the `.disable` lists from the database.

| | |
|---|---|
| Syntax | `.rehash` |
| Permission | Owner |
| Denied | `Only the bot owner can rehash.` |

**Example**

```text
<owner> .rehash
<bot>   Rehashing...
<bot>   Rehash complete: 12 plugins loaded (58 commands, 9 rules)
```

When something goes wrong, the problems are listed after the summary:

```text
<bot>   Rehash complete: 12 plugins loaded (58 commands, 9 rules)
<bot>   ⚠ 2 error(s):
<bot>     • weather import: SyntaxError: invalid syntax (weather.py, line 41)
<bot>     • tell setup: KeyError: 'api_key' (kept previous version)
```

When the config can't be parsed (for example a duplicate key), nothing is changed:

```text
<bot>   Config reload failed: While reading from 'mybot.cfg' [line 12]: option 'nick' in section 'core' already exists
```

| Detail | Behaviour |
|---|---|
| "commands" in the reply | The number of command **names** registered (aliases count separately) |
| Error lines | `<plugin> import: …` (old version kept), `<plugin> setup: … (kept previous version)`, `<plugin> shutdown: …`, `ignore lists: …` |
| Applied by rehash | Plugin sections, `prefix`, `exclude`/`enable`, owner/admin keys, `nick_blocks`/`host_blocks`, `[#channel] disable_plugins`, and keys read at connect time (`host`, `port`, `user`, `name`, `bind_host`, `auth_*`) for the **next** connection |
| Not applied by rehash | Flood settings, handler pool size, `log_raw`/`logdir`, database settings, `extra`, the SASL on/off decision, and the current connection (server, nick). See [What rehash does](plugin-management.md#what-rehash-does). |
| Interval jobs | Cancelled for each plugin that is swapped or unloaded, and started for the new version straight away |

### reload

Reload one plugin file from disk.

| | |
|---|---|
| Syntax | `.reload <plugin>` |
| Permission | Owner |
| Denied | `Only the bot owner can reload plugins.` |
| `<plugin>` | The file name without `.py`, **case-sensitive**. Don't add `.py`: the admin plugin looks the name up before stripping it, so `weather.py` gets `Plugin not found: weather.py` |

```text
<owner> .reload weather
<bot>   Reloaded weather (2 commands, 0 rules)

<owner> .reload nosuch
<bot>   owner: Plugin not found: nosuch

<owner> .reload weather
<bot>   Reload failed (previous version kept): invalid syntax (weather.py, line 41)

<owner> .reload
<bot>   owner: Usage: .reload <plugin_name>
```

Steps: find the file in the plugin directories (in search order) → **import the new code** (on failure, stop: the running version is untouched) → run the old version's `shutdown(bot)` → unregister its handlers and cancel its interval jobs → register the new handlers and start their interval jobs → run the new `setup(bot)`.

| Outcome | What you see |
|---|---|
| Success | `Reloaded <plugin> (N commands, M rules)` |
| Old `shutdown()` raised | The reload still completes; the error follows as `  ⚠ <plugin> shutdown: <Type>: <message>` |
| New code doesn't import | `Reload failed (previous version kept): <error>`. The old version keeps running. |
| New `setup()` raised | `Reload failed (previous version kept): <plugin> setup: <Type>: <message>`. The new version is removed and the old one is registered again; because its `shutdown()` already ran, its `setup()` is run again too. |

> **Note:** `setup()` is called exactly once per load, as `setup(bot)` (or `setup()` if it takes no arguments). A `TypeError` raised inside it is reported as a failure, not retried.

> **Note:** `.reload` on a plugin that isn't loaded loads it, just like `.load`. It also bypasses `[core] exclude`/`enable`.

### load

Load a plugin that isn't currently loaded.

| | |
|---|---|
| Syntax | `.load <plugin>` |
| Permission | Owner |
| Denied | `Only the bot owner can load plugins.` |
| `<plugin>` | The file name without `.py`, as for `.reload` |

```text
<owner> .load hello
<bot>   Loaded hello (2 commands)

<owner> .load hello
<bot>   owner: hello is already loaded. Use .reload instead.
```

| Detail | Behaviour |
|---|---|
| Search path | The same directories as at startup: built-in, `extra`, then `<config dir>/plugins`. The first match wins. |
| `exclude` / `enable` | Ignored, so `.load` can load an excluded plugin |
| Count | Counts command names. A single function with `@plugin.command('hi', 'hello')` counts as 2. |
| Failure | `Plugin not found: <name>`, or `Load failed: <error>` (import error, or `<name> setup: …` when `setup()` raised; the plugin is then not loaded) |
| Interval jobs | Start immediately when the bot is connected |

### unload

Run a plugin's `shutdown()` and remove its handlers.

| | |
|---|---|
| Syntax | `.unload <plugin>` |
| Permission | Owner |
| Denied | `Only the bot owner can unload plugins.` |

```text
<owner> .unload weather
<bot>   Unloaded weather

<owner> .unload admin
<bot>   owner: Can't unload the admin plugin.

<owner> .unload nosuch
<bot>   owner: Plugin not loaded: nosuch
```

If `shutdown(bot)` raises, the plugin is unloaded anyway and the error follows as `  ⚠ <plugin> shutdown: <Type>: <message>`. The plugin's interval jobs are cancelled.

> **Note:** Unloading a plugin doesn't stop **threads** it started itself, and handler calls already running finish normally. Stop your own threads in `shutdown()`.

### plugins

List loaded plugins in alphabetical order.

| | |
|---|---|
| Syntax | `.plugins` |
| Permission | Owner |
| Denied | *(silent)* |

```text
<owner> .plugins
<bot>   Loaded plugins (3): admin, hello, weather
```

---

## Channels

### bjoin

Join a channel and add it to the persistent auto-join list stored in the database, so that it's rejoined after every restart or reconnect.

| | |
|---|---|
| Syntax | `.bjoin <#channel> [key]` |
| Permission | Admin |
| Denied | `Only admins can make the bot join channels.` |

```text
<admin> .bjoin #newchan
<bot>   Joining #newchan
<bot>   #newchan will rejoin on restart.

<admin> .bjoin #NewChan
<bot>   Joining #NewChan
<bot>   #NewChan is already in persistent channel list.
```

| Detail | Behaviour |
|---|---|
| Key | Used for this `JOIN` only and **not** saved. For keyed channels, put `"#chan key"` in `[core] channels`. |
| Join result | The bot says `Joining …` before the server answers. A ban or `+i` failure is only logged. |
| Validation | None. `.bjoin foo` sends `JOIN foo` and saves `foo`. |
| Database error | `⚠ Warning: Failed to save #chan for auto-rejoin` |

### bpart

Part a channel and remove it from the persistent list.

| | |
|---|---|
| Syntax | `.bpart <#channel> [message]` |
| Permission | Admin |
| Denied | `Only admins can make the bot part channels.` |

```text
<admin> .bpart #newchan see you
<bot>   #newchan removed from auto-rejoin list.
```

If the channel wasn't in the persistent list, for example because it comes from `[core] channels`, the bot parts **silently** and rejoins it on the next connect.

---

## Messaging and raw IRC

### say / msg

| | |
|---|---|
| Syntax | `.say <target> <message>` · `.msg <target> <message>` |
| Permission | Admin |
| Denied | *(silent)* |

```text
<admin> .say #main Hello, world!
(in #main) <bot> Hello, world!

<admin> .msg SomeNick hi there
```

Long messages are split into 400-byte chunks, and every chunk is sent.

### act

| | |
|---|---|
| Syntax | `.act <target> <action text>` |
| Permission | Admin |
| Denied | *(silent)* |

```text
<admin> .act #main waves
(in #main) * bot waves
```

### raw

Send any line to the server.

| | |
|---|---|
| Syntax | `.raw <IRC line>` |
| Permission | Owner |
| Denied | `Only the bot owner can send raw commands.` |

```text
<owner> .raw PRIVMSG ChanServ :OP #main
<bot>   owner: Sent.
```

> **Warning:** The line is sent unchanged through the flood queue, so a mistake can get the bot killed or banned. Anything you type, passwords included, also appears in the channel where you typed it and in debug logs. Use `.raw` in a private message.

---

## Bot control

### bnick

| | |
|---|---|
| Syntax | `.bnick [newnick]` |
| Permission | Owner |
| Denied | `Only the bot owner can change the nick.` |

```text
<owner> .bnick
<bot>   owner: Current nick: MyBot

<owner> .bnick MyBot2
<bot>   Changing nick to MyBot2
```

| Detail | Behaviour |
|---|---|
| Persistence | Lasts for the current connection only. After a reconnect or restart the bot registers with `[core] nick` again (and may try to regain it). |
| Nick refused | If the server answers `432`/`433`/`436`/`437`, the bot keeps its current nick and logs `Nick change to <nick> refused (…); keeping <current>`. The channel reply `Changing nick to …` is sent regardless, so check `.bnick` with no argument. |
| Nick-based patterns | `$nick` rules and `MyBot: cmd` nickname commands follow the new nick as soon as the server confirms the change |

### bmode

Send a `MODE` command with the given arguments.

| | |
|---|---|
| Syntax | `.bmode <target> <modes> [params…]` |
| Permission | Admin |
| Denied | *(silent)* |

```text
<admin> .bmode #main +o TrustedFriend
<admin> .bmode #main +b *!*@spam.example.net
```

There's no reply. The arguments are sent as-is (`MODE <args>`), and the bot needs the matching channel privileges for the server to accept them.

> **Note:** Because the arguments aren't checked, an admin can use `.bmode` to change the **bot's own user modes** (`.bmode MyBot +i`).

### bquit / die

| | |
|---|---|
| Syntax | `.bquit [message]` · `.die [message]` |
| Permission | Owner |
| Denied | `Only the bot owner can shut down the bot.` |

```text
<owner> .bquit Maintenance, back soon
*** MyBot has quit (Quit: Maintenance, back soon)
```

The default quit message is `Shutting down.`. The process then stops: it doesn't reconnect, it runs the plugins' `shutdown()` functions, and it exits. A process supervisor configured with `Restart=always` starts it again. See [Running as a service](../getting-started/running-as-a-service.md).

### bstatus

| | |
|---|---|
| Syntax | `.bstatus` |
| Permission | Admin |
| Denied | *(silent)* |

```text
<admin> .bstatus
<bot>   Nick: MyBot | Channels: 3 | Plugins: 1 | Commands: 19 | Rules: 0 | Events: 2
```

| Field | Meaning |
|---|---|
| Nick | The current nick |
| Channels | Channels the bot is in right now (tracked state) |
| Plugins | Loaded plugins |
| Commands | Registered command names, aliases included (the `admin` plugin alone gives 19) |
| Rules | Registered rule patterns |
| Events | Registered event handlers (`admin` has 2: `KICK` and `INVITE`) |

---

## Per-channel plugin control

These three commands only work in a **private message** to the bot. The PM check runs **before** the admin check, so anyone who tries them in a channel sees `This command must be used in PM.`. See [Per-channel settings](../configuration/per-channel.md) for what "disabled" means.

### disable

| | |
|---|---|
| Syntax | `/msg <bot> .disable <plugin> <#channel>` |
| Permission | Admin |
| Denied | In a channel: `This command must be used in PM.` In PM: `Only admins can disable plugins.` |

```text
<admin> .disable weather #main
<bot>   admin: Disabled plugin "weather" in #main
```

| Error reply | Cause |
|---|---|
| `Usage: disable <plugin> <#channel>` | Missing arguments |
| `Channel must start with # or &` | Invalid channel |
| `Cannot disable protected plugin: admin` | `admin` is protected |
| `Plugin not found: <name>` | No loaded plugin has that name. Plugin names are compared case-insensitively and stored lowercase. |
| `"<name>" is already disabled in <#channel>` | No change |

### enable

| | |
|---|---|
| Syntax | `/msg <bot> .enable <plugin> <#channel>` |
| Permission | Admin |
| Denied | In a channel: `This command must be used in PM.` In PM: `Only admins can enable plugins.` |

```text
<admin> .enable weather #main
<bot>   admin: Enabled plugin "weather" in #main
```

Errors: `Usage: enable <plugin> <#channel>`, `Channel must start with # or &`, `"<name>" is not disabled in <#channel>`.

### disabled

| | |
|---|---|
| Syntax | `/msg <bot> .disabled [#channel]` |
| Permission | Admin |
| Denied | In a channel: `This command must be used in PM.` In PM: *(silent)* |

```text
<admin> .disabled
<bot>   admin: #main: weather, youtube
<bot>   admin: #offtopic: chat

<admin> .disabled #main
<bot>   admin: Disabled in #main: weather, youtube

<admin> .disabled #quiet
<bot>   admin: No plugins disabled in #quiet
```

With nothing disabled anywhere, it replies `No plugins disabled in any channel.`.

---

## Automatic behaviour

These handlers are marked `@plugin.unblockable`, so they run even for users in `nick_blocks`/`host_blocks`.

### Kick rejoin (hold_ground)

When the bot itself is kicked and `[admin] hold_ground` is true, it logs `Kicked from #chan, rejoining in 5 seconds (hold_ground=true)`, waits 5 seconds, and sends `JOIN #chan`. Nothing is said in the channel.

### Invite accept (auto_accept_invite)

When the bot receives an `INVITE` and `[admin] auto_accept_invite` is true, it joins the channel, but **only** if the inviting user is the owner or an admin. Other invites are ignored and logged as `Ignoring invite to #chan from non-admin <nick>`. Accepted invites log `Received invite to #chan from <nick>, joining`. The channel isn't added to the persistent list. See [Plugin configuration](../configuration/plugin-config.md#the-admin-section).

## See also

- [Permissions](permissions.md)
- [Plugin management](plugin-management.md)
- [Per-channel settings](../configuration/per-channel.md)
- [Security](../security.md)

---
[← Back to docs home](../index.md)
