[Docs home](../index.md) › Configuration › Per-channel settings

# Per-channel settings

ibot has two per-channel mechanisms: **persistent channels**, which the bot rejoins on every connect, and **per-channel plugin disabling**. Persistent channels and `.disable` settings are stored in the bot's database and managed with admin commands. Plugins can also be disabled per channel in the config file, with a Sopel-style `[#channel]` section.

## In this article

- [Prerequisites](#prerequisites)
- [Channels the bot joins](#channels-the-bot-joins)
- [Persistent channels (.bjoin / .bpart)](#persistent-channels-bjoin--bpart)
- [Disabling plugins per channel](#disabling-plugins-per-channel)
- [What "disabled" means](#what-disabled-means)
- [Sopel-style \[#channel\] sections](#sopel-style-channel-sections)
- [Where the data is stored](#where-the-data-is-stored)
- [See also](#see-also)

## Prerequisites

- Admin access to the bot (see [Permissions](../administration/permissions.md)).
- The built-in `admin` plugin loaded.

## Channels the bot joins

When registration completes (numeric `001`), ibot builds its join list from two sources:

1. `[core] channels` in the config file.
2. The `persistent_channels` list that `.bjoin` saves in the database.

The two lists are combined into a set, sorted, and each entry is queued as `JOIN <entry>`. The `JOIN`s go through the [flood-control queue](../architecture/flood-control.md), so a long channel list is joined at the bucket's pace instead of all at once. The same thing happens on every reconnect.

> **Note:** De-duplication is **case-sensitive** at this stage. `#Main` in the config and `#main` saved by `.bjoin` produce two `JOIN` lines. That's harmless, because the server ignores the second one.

### Join failures

| Numeric | Meaning | ibot behaviour |
|---|---|---|
| `471` | Channel is full (+l) | Logs a warning and retries `JOIN <channel>` (without the key) with back-off: 10 s, 20 s, 40 s, … up to 300 s, at most **8** retries, then logs `Giving up on joining …` |
| `473` | Invite only (+i) | Logs a warning and does not retry |
| `474` | Banned (+b) | Logs a warning and does not retry |
| `475` | Bad channel key (+k) | Logs a warning and does not retry |
| `477` | Need a registered nick | Same retry schedule as `471` |

A pending retry is cancelled when the bot joins, parts or is kicked from the channel, or when it sends a `PART` for it. All retries are cancelled on reconnect.

## Persistent channels (.bjoin / .bpart)

```text
<you>   .bjoin #newchan
<bot>   Joining #newchan
<bot>   #newchan will rejoin on restart.

<you>   .bpart #newchan bye!
<bot>   #newchan removed from auto-rejoin list.
```

| Behaviour | Detail |
|---|---|
| What's stored | The channel name **as typed**. A key given to `.bjoin #chan key` is used for this join only and is **not** saved. |
| Duplicates | Matched case-insensitively, so `.bjoin #NewChan` after `#newchan` replies `… is already in persistent channel list.` |
| Config channels | `.bpart` on a channel listed in `[core] channels` parts it, but the bot rejoins it on the next connect. Remove it from the config to make that permanent. |
| Keyed channels | Put `"#chan key"` in `[core] channels`, because `.bjoin` doesn't remember keys. |

Full syntax is in [Admin commands](../administration/admin-commands.md#bjoin).

## Disabling plugins per channel

All three commands must be sent **in a private message** to the bot, by an admin.

```text
/msg MyBot .disable weather #main
<bot> You: Disabled plugin "weather" in #main

/msg MyBot .disabled
<bot> You: #main: weather

/msg MyBot .disabled #main
<bot> You: Disabled in #main: weather

/msg MyBot .enable weather #main
<bot> You: Enabled plugin "weather" in #main
```

| Rule | Detail |
|---|---|
| Plugin name | The plugin's file name without `.py`, case-insensitive. It must be **currently loaded** for `.disable` to accept it. |
| Channel | Must start with `#` or `&` |
| Protected | `admin` can't be disabled (`Cannot disable protected plugin: admin`) |
| Persistence | Saved immediately to the database and reloaded on startup and `.rehash` |
| Config-file disables | Independent. See [Sopel-style \[#channel\] sections](#sopel-style-channel-sections). |
| Effect | Immediate |

## What "disabled" means

When a message arrives **in a channel** where a plugin is disabled, **none** of that plugin's handlers run for it: commands, rules, nick commands, events, CTCP and URL callbacks are all skipped.

- This applies to everyone, **including the owner and admins**.
- Private messages to the bot are not affected.
- Events whose "sender" isn't a channel (`NICK`, `QUIT`) are not affected.
- Interval jobs (`@plugin.interval`) keep running. They have no channel context.
- The plugin's own code can still send to the channel (for example from an interval job).

> **Warning:** If the disabled plugin defines a **command** that another plugin also defines, the command is still "consumed" by the disabled plugin, and the other plugin doesn't run it either. See [Dispatch](../architecture/dispatch.md#known-limitations).

## Sopel-style [#channel] sections

Sopel 8 lets you write:

```ini
[#somechannel]
disable_plugins = weather, youtube
disable_commands = {"wiki": ["wikipedia"]}
```

ibot reads **`disable_plugins`** from every config section whose name starts with `#` or `&`:

| Detail | Behaviour |
|---|---|
| Format | Comma-separated plugin names (file name without `.py`), case-insensitive. Whitespace around names is ignored. |
| `*` | Disables **every** plugin in that channel, except `admin` |
| Channel name | Case-insensitive |
| `admin` | Can't be disabled; listing it has no effect |
| Applied | At startup and on `.rehash`. The startup log lists them: `Per-channel disable_plugins from config: #somechannel=weather,youtube` |
| Relation to `.disable` | Checked **in addition to** the database list. A plugin disabled in the config can't be re-enabled with `.enable`; remove it from the config and `.rehash`. `.disabled` shows only the database list. |

> **Important:** `disable_commands` is **not** read. It's valid INI and causes no error, but has no effect. Disable the whole plugin instead.

> **Note:** Only commas separate names here. Unlike `[core]` lists, newlines and quotes aren't supported, so keep the list on one line.

Plugins can still read such a section themselves:

```python
section = bot.config['#somechannel']       # KeyError if missing
value = section.disable_plugins             # raw string or None
```

## Where the data is stored

| Data | Table | Key |
|---|---|---|
| Persistent channels | `plugin_values` | plugin `admin`, key `persistent_channels` (JSON list) |
| Disabled plugins | `channel_values` | channel *(lowercased)*, key `disabled_plugins` (JSON list) |

See [Database](../architecture/database.md). You normally don't need to edit these by hand.

## See also

- [Admin commands](../administration/admin-commands.md)
- [Plugin management](../administration/plugin-management.md)
- [Core reference: channels](core-reference.md#channels)

---
[← Back to docs home](../index.md)
