[Docs home](../index.md) › Configuration › Overview

# Configuration overview

ibot reads a single INI file in the same format as Sopel. This page explains the file structure, how values are parsed, how lists and booleans work, the pitfalls of Python's `configparser`, and which changes can be applied without a restart.

## In this article

- [Prerequisites](#prerequisites)
- [Where the config file lives](#where-the-config-file-lives)
- [File structure](#file-structure)
- [How values are parsed](#how-values-are-parsed)
- [Lists](#lists)
- [Booleans](#booleans)
- [Interpolation and the % character](#interpolation-and-the--character)
- [Comments and the # character](#comments-and-the--character)
- [Path resolution](#path-resolution)
- [Invalid values and error handling](#invalid-values-and-error-handling)
- [Applying changes](#applying-changes)
- [Keeping secrets out of the file](#keeping-secrets-out-of-the-file)
- [A complete example](#a-complete-example)
- [See also](#see-also)

## Prerequisites

- A config file, either generated with `python -m ibot --generate-config FILE` or copied from an existing Sopel install.
- Basic familiarity with INI syntax.

## Where the config file lives

The file is the first positional argument:

```bash
python -m ibot /home/ender/ibot/glitchy.cfg
```

| Detail | Behaviour |
|---|---|
| Default name | `ibot.cfg` in the current working directory |
| Missing file | `Config file not found: <path>` is logged and the process exits with status 1 |
| `homedir` | The directory **containing the config file**. It is used to resolve `db_filename` and to find the auto-loaded `plugins/` directory. |
| `basename` | The config file name without its extension (`glitchy.cfg` → `glitchy`). It is used for the default database name `<basename>.db`. |

## File structure

```ini
[core]                 ; bot-wide settings, see the Core reference
nick = MyBot
host = irc.example.net

[admin]                ; options for the built-in admin plugin
hold_ground = true

[weather]              ; options read by a plugin
weather_api_key = YOUR_KEY_HERE

[#somechannel]         ; channel-named sections are valid INI; see Per-channel settings
```

| Section | Read by | Documented in |
|---|---|---|
| `[core]` | The ibot core and the shim (`settings.core`) | [Core reference](core-reference.md) |
| `[admin]` | The built-in `admin` plugin | [Plugin configuration](plugin-config.md#the-admin-section) |
| Any other name | Plugins, through `bot.config.<section>` or `define_section()` | [Plugin configuration](plugin-config.md) |

Option names are **case-insensitive** (`configparser` lowercases them). Section names are case-sensitive.

## How values are parsed

ibot uses `configparser.ConfigParser(allow_no_value=True)` with the default settings:

| Rule | Effect |
|---|---|
| Delimiters | `key = value` and `key: value` are both accepted |
| Whitespace | Leading and trailing whitespace around values is stripped |
| Multi-line values | Continuation lines must be **indented** |
| Keys without a value | Allowed (`allow_no_value=True`). The value reads as `None`. |
| Inline comments | **Not** supported. `key = value ; note` keeps `; note` as part of the value. |
| Duplicate sections or keys | Raise an error. On startup that aborts the process; during `.rehash` you get `Config reload failed: …` and the old settings stay active. |
| Encoding | The platform default (UTF-8 on modern Linux) |

## Lists

`[core]` list keys (`channels`, `admins`, `admin_accounts`, `extra`, `exclude`, `enable`, `host_blocks`, `nick_blocks`) accept two forms.

**Comma-separated, on one line:**

```ini
admins = alice, bob, carol
exclude = example, debugtools
```

**One item per line (indented):**

```ini
channels =
    "#main"
    "#offtopic"
    "#ops opskey"
```

| Rule | Detail |
|---|---|
| Format detection | If the value contains a newline, it is split **only on newlines** and commas are kept as part of each item. Otherwise it is split on commas. |
| Quotes | Matching `"…"` or `'…'` around an item are removed |
| Empty items | Ignored |

Plugin `ListAttribute`s behave slightly differently: they strip commas at the end of lines, and they only remove double quotes around items that start with `#`. See [Plugin configuration](plugin-config.md#listattribute).

## Booleans

`[core]` booleans use `configparser.getboolean`:

| True | False |
|---|---|
| `1`, `yes`, `true`, `on` | `0`, `no`, `false`, `off` |

Matching is case-insensitive. Any other value falls back to the key's **default** (see [Invalid values](#invalid-values-and-error-handling)).

## Interpolation and the % character

The file is read with `RawConfigParser`, so there is **no interpolation**. A `%` is an ordinary character, and `%(name)s` is not substituted. Write values exactly as they are:

```ini
auth_password = abc%123      ; the real password is abc%123
```

> **Warning:** Earlier builds used `ConfigParser` with `BasicInterpolation`, where a bare `%` had to be written as `%%`. If you escaped a value that way, change `%%` back to `%`. Otherwise the doubled sign is now taken literally and, for example, the password sent to services is wrong.

## Comments and the # character

Lines that **start** with `#` or `;` are comments, and that includes indented continuation lines. This matters for channel lists:

```ini
; WRONG: the indented lines start with '#', so they are treated as comments
channels =
    #main
    #offtopic

; RIGHT: quote them
channels =
    "#main"
    "#offtopic"

; ALSO RIGHT: single line, comma-separated
channels = #main, #offtopic
```

## Path resolution

| Key | Resolution |
|---|---|
| `db_filename` | `~` is expanded. Relative paths are joined to the **config file's directory**. |
| `extra` | `~` is expanded and the path made absolute with `realpath` relative to the **current working directory** |
| auto `plugins/` | `<config dir>/plugins` is loaded if it exists |
| Plugin `FilenameAttribute` | `~` is expanded only. Relative paths are **not** anchored to the config directory, so prefer absolute paths. |

## Invalid values and error handling

| Situation | `[core]` behaviour | Plugin `StaticSection` behaviour |
|---|---|---|
| Key missing | Default used | `default` returned (or `None`) |
| Wrong type (e.g. `port = abc`) | **Silently** uses the default | `parse()` raises when the attribute is read |
| Unknown key | Ignored | Ignored |
| Not one of the `ChoiceAttribute` choices | n/a | `ValueError` when the attribute is read |

> **Note:** Nothing is validated at load time. A typo like `use_ssl = ture` silently becomes `True` (the default) rather than an error. Check startup logs and `.bstatus` after you edit.

## Applying changes

| Change | How to apply |
|---|---|
| Plugin sections (`[weather]`, `[admin]`, …) | `.rehash`, since plugins re-read config on access or in `setup()` |
| `[core] exclude`, `enable` | `.rehash` (plugins are re-discovered in the existing directories) |
| `[core] extra` | **Restart**. The plugin directory list is built once at startup. |
| `[core] prefix` | `.rehash` (command regexes are rebuilt) |
| `[core] owner`, `owner_account`, `admins`, `admin_accounts` | `.rehash`. These are read on every message, so they apply immediately once the file is reloaded. |
| `[core] nick_blocks`, `host_blocks` | `.rehash` (the ignore lists are rebuilt after the file is reloaded) |
| `[#channel] disable_plugins` | `.rehash` |
| `[core] handler_threads`, `handler_queue_size` | **Restart** (the handler pool is created once) |
| `[core] user`, `name`, `bind_host` | Read at each (re)connect, after `.rehash`. Restart, or wait for the next reconnect. |
| `[core] log_raw`, `logdir` | **Restart** (the raw log is set up when the bot object is created) |
| `[core] extra_owners` | `.rehash` (read on every message) |
| `[core] flood_burst`, `flood_refill` | **Restart** (read once at startup) |
| `[core] host`, `port`, `use_ssl`, `verify_ssl` | Read at each (re)connect. Restart, or wait for the next reconnect. |
| `[core] nick` | Restart. `.bnick` changes the nick for the current connection only: on every reconnect the bot goes back to the nick it was started with. |
| `[core] channels` | Read when registration completes, so a restart or reconnect applies it. Use `.bjoin` to join now. |
| `[core] db_*` | **Restart** (the database engine is created once) |
| `[core] auth_method` | Whether to use **SASL** is decided once, at startup. The `nickserv` method, `auth_password`, `auth_user` and `auth_target` are re-read at each (re)connect, after `.rehash`. |

See [Plugin management](../administration/plugin-management.md#what-rehash-does) for exactly what `.rehash` does.

## Keeping secrets out of the file

- `[core]` keys have **no** environment-variable override.
- Plugin attributes defined with `StaticSection` **do**: `SOPEL_<SECTION>_<NAME>` overrides the file. For example, `SOPEL_WEATHER_WEATHER_API_KEY` overrides `[weather] weather_api_key`. See [Plugin configuration](plugin-config.md#environment-variable-overrides).
- Whatever you do, run `chmod 600` on the config file. See [Security](../security.md).

> **Warning:** `Config.save()` (which plugins can call) rewrites the whole file from the parsed contents. That **drops every comment** and reformats the file, and it uses the process umask for the file mode.

## A complete example

```ini
[core]
nick = MyBot
host = irc.rizon.net
port = 6697
use_ssl = true
verify_ssl = true

owner = YourNick
admins = TrustedFriend
prefix = \$

channels =
    "#yourchannel"
    "#another"

auth_method = nickserv
auth_password = YOUR_PASSWORD_HERE

db_filename = mybot.db
extra = ~/.sopel/scripts
exclude = example

nick_blocks =
    SomeOtherBot
host_blocks = *!*@spam.example.net

flood_burst = 4
flood_refill = 1

[admin]
hold_ground = true
auto_accept_invite = false

[weather]
weather_api_key = YOUR_KEY_HERE
```

## See also

- [Core reference](core-reference.md)
- [Plugin configuration](plugin-config.md)
- [Per-channel settings](per-channel.md)
- [Authentication](authentication.md)

---
[← Back to docs home](../index.md)
