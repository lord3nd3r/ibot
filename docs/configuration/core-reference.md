[Docs home](../index.md) › Configuration › Core reference

# `[core]` configuration reference

This page lists every key that ibot's `[core]` section recognises (`ibot/sopel_shim/config/core_section.py`), with its type, default, whether the core actually uses it, and an example. It also lists keys you may know from Sopel that ibot **does not** recognise.

## In this article

- [Prerequisites](#prerequisites)
- [How to read this reference](#how-to-read-this-reference)
- [Summary table](#summary-table)
- [Connection](#connection)
- [Identity and access](#identity-and-access)
- [Commands](#commands)
- [Authentication](#authentication)
- [Database](#database)
- [Plugins](#plugins)
- [Flood control](#flood-control)
- [Ignore lists](#ignore-lists)
- [Logging](#logging)
- [Performance](#performance)
- [Derived (read-only) values](#derived-read-only-values)
- [Keys ibot does not recognise](#keys-ibot-does-not-recognise)
- [See also](#see-also)

## Prerequisites

- Read the [Configuration overview](overview.md) for the list and boolean syntax and for the `#` pitfall.

## How to read this reference

| Column | Meaning |
|---|---|
| **Type** | `str`, `int`, `bool` or `list` (see [Lists](overview.md#lists)) |
| **Default** | The value used when the key is missing **or fails to parse** |
| **Used** | ✅ the core reads it · ⚠️ partly · ❌ parsed for Sopel compatibility but **not used by ibot's core** (plugins can still read it as `bot.config.core.<key>`) |

## Summary table

| Key | Type | Default | Used |
|---|---|---|---|
| [`nick`](#nick) | str | `ibot` | ✅ |
| [`host`](#host) | str | `irc.libera.chat` | ✅ |
| [`port`](#port) | int | `6697` | ✅ |
| [`use_ssl`](#use_ssl) | bool | `true` | ✅ |
| [`verify_ssl`](#verify_ssl) | bool | `true` | ✅ |
| [`reconnect_on_disconnect`](#reconnect_on_disconnect) | bool | `true` | ✅ |
| [`bind_host`](#bind_host) | str | *(none)* | ✅ |
| [`user`](#user) | str | *(none)* → nick | ✅ |
| [`name`](#name) | str | *(none)* → `<nick> - ibot` | ✅ |
| [`channels`](#channels) | list | *(empty)* | ✅ |
| [`owner`](#owner) | str | *(empty)* | ✅ |
| [`owner_account`](#owner_account) | str | *(empty)* | ✅ |
| [`admins`](#admins) | list | *(empty)* | ✅ |
| [`admin_accounts`](#admin_accounts) | list | *(empty)* | ✅ |
| [`extra_owners`](#extra_owners) | list | *(empty)* | ✅ |
| [`prefix`](#prefix) | str (regex) | `\.` | ✅ |
| [`help_prefix`](#help_prefix) | str | `.` | ❌ |
| [`auth_method`](#auth_method) | str | *(empty)* | ✅ |
| [`auth_user`](#auth_user) | str | *(empty)* → nick | ✅ (SASL only) |
| [`auth_password`](#auth_password) | str | *(empty)* | ✅ |
| [`auth_target`](#auth_target) | str | `NickServ` | ✅ (NickServ only) |
| [`db_type`](#db_type) | str | `sqlite` | ✅ |
| [`db_filename`](#db_filename) | str | *(empty)* → `<basename>.db` | ✅ |
| [`db_url`](#db_url) | str | *(none)* | ✅ |
| [`db_user`](#db_user-db_pass-db_host-db_port-db_name) | str | *(none)* | ✅ (non-SQLite) |
| [`db_pass`](#db_user-db_pass-db_host-db_port-db_name) | str | *(none)* | ✅ (non-SQLite) |
| [`db_host`](#db_user-db_pass-db_host-db_port-db_name) | str | *(none)* → `localhost` | ✅ (non-SQLite) |
| [`db_port`](#db_user-db_pass-db_host-db_port-db_name) | str | *(none)* | ✅ (non-SQLite) |
| [`db_name`](#db_user-db_pass-db_host-db_port-db_name) | str | *(none)* | ✅ (non-SQLite) |
| [`db_driver`](#db_driver) | str | *(none)* → derived | ✅ (non-SQLite) |
| [`db_dir`](#db_dir) | str | config directory | ❌ |
| [`extra`](#extra) | list | *(empty)* | ✅ |
| [`exclude`](#exclude) | list | *(empty)* | ✅ |
| [`enable`](#enable) | list | *(empty)* | ✅ |
| [`flood_burst`](#flood_burst) | int | `4` | ✅ |
| [`flood_refill`](#flood_refill) | int | `1` | ✅ |
| [`flood_empty_wait`](#flood_empty_wait) | int | `0` | ❌ |
| [`nick_blocks`](#nick_blocks) | list | *(empty)* | ✅ |
| [`host_blocks`](#host_blocks) | list | *(empty)* | ✅ |
| [`logging_level`](#logging_level) | str | `INFO` | ⚠️ no effect (see below) |
| [`logging_format`](#logging_format-logging_datefmt) | str | *(none)* | ❌ |
| [`logging_datefmt`](#logging_format-logging_datefmt) | str | *(none)* | ❌ |
| [`logging_channel`](#logging_channel-keys) | str | *(none)* | ❌ |
| [`logging_channel_level`](#logging_channel-keys) | str | *(none)* | ❌ |
| [`logging_channel_format`](#logging_channel-keys) | str | *(none)* | ❌ |
| [`logging_channel_datefmt`](#logging_channel-keys) | str | *(none)* | ❌ |
| [`log_raw`](#log_raw) | bool | `false` | ✅ |
| [`logdir`](#logdir) | str (path) | `<config dir>/logs` | ✅ (raw log only) |
| [`handler_threads`](#handler_threads) | int | `64` | ✅ |
| [`handler_queue_size`](#handler_queue_size) | int | `10000` | ✅ |

---

## Connection

### `nick`

| | |
|---|---|
| Type | str |
| Default | `ibot` |
| Read | Once, at startup (the bot returns to it on every reconnect) |

The nickname the bot registers with. Unless [`user`](#user) and [`name`](#name) are set, it's also used as the IRC ident and in the realname: ibot sends `USER <user or nick> 0 * :<name or "<nick> - ibot">`.

If the server refuses the nick during registration (`432`, `433`, `436` or `437`), ibot tries variants of the **configured** nick: `nick_`, then `nick__`, then `nick_` plus a random three-digit number, each cut to the server's `NICKLEN`. After 20 refusals it drops the connection and reconnects. Once registered on a different nick, it tries to reclaim the configured one with services `GHOST` when [`auth_password`](#auth_password) is set and [`auth_method`](#auth_method) is `nickserv` or `sasl`. See [Connection lifecycle](../architecture/connection-lifecycle.md#nick-collisions).

```ini
nick = MyBot
```

> **Note:** The `$nick` placeholder in plugin `@rule` patterns and the `MyBot: command` pattern used by `@nickname_command` follow the bot's **current** nick: they are recompiled whenever it changes.

> **Note:** The configured nick is read once, at startup. On every reconnect the bot goes back to it, so a nick set with `.bnick` lasts only until the next reconnect.

### `host`

| | |
|---|---|
| Type | str |
| Default | `irc.libera.chat` |

The server hostname or IP address. It is read at every (re)connect.

```ini
host = irc.rizon.net
```

### `port`

| | |
|---|---|
| Type | int |
| Default | `6697` |

The TCP port. Typical values are `6697` (TLS) and `6667` (plaintext). A non-integer value silently falls back to `6697`.

### `use_ssl`

| | |
|---|---|
| Type | bool |
| Default | `true` |

When `true`, the connection is wrapped in TLS using `ssl.create_default_context()`, which loads the system CA store and uses the TLS versions your Python's OpenSSL supports.

### `verify_ssl`

| | |
|---|---|
| Type | bool |
| Default | `true` |

When `false`, both hostname checking and certificate verification are switched off (`check_hostname = False`, `CERT_NONE`). Only do this for servers with self-signed certificates that you trust.

> **Warning:** Setting `verify_ssl = false` makes the connection vulnerable to interception. Any credentials you send (SASL, NickServ) can then be captured by a man in the middle.

### `reconnect_on_disconnect`

| | |
|---|---|
| Type | bool |
| Default | `true` |

When `true`, ibot reconnects after a disconnect or a connection error. The first wait is 5 seconds and each attempt doubles it, up to `MAX_RECONNECT_DELAY` = 300 seconds. The delay goes back to 5 seconds once a connection completes registration (`001`). When `false`, the process exits after the first disconnect. See [Connection lifecycle](../architecture/connection-lifecycle.md#reconnects).

### `bind_host`

| | |
|---|---|
| Type | str |
| Default | *(none)*: the operating system picks the source address |
| Read | At every (re)connect |

The local address to bind the outgoing connection to, for hosts with several addresses or a vhost. ibot passes it as the socket's local address with port `0` (any port) and logs `Binding outgoing connection to <address>`.

```ini
bind_host = 203.0.113.10
```

> **Note:** Use an address of the same family (IPv4 or IPv6) as the server you connect to, or the connection fails.

### `user`

| | |
|---|---|
| Type | str |
| Default | *(none)*: the current nick is used |
| Read | At every (re)connect |

The ident (username) sent in `USER`. Many networks prefix it with `~` when the host doesn't run an identd.

```ini
user = mybot
```

### `name`

| | |
|---|---|
| Type | str |
| Default | *(none)*: `<nick> - ibot` |
| Read | At every (re)connect |

The realname (`GECOS`) sent in `USER`. Spaces are allowed.

```ini
name = Friendly channel helper
```

### `channels`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |
| Read | When registration completes (`001`) |

The channels to join. An item may include a key, separated by a space (`#secret thekey`), and it is sent verbatim as `JOIN <item>`. This list is merged with the persistent channels saved by `.bjoin` (see [Per-channel settings](per-channel.md)).

```ini
channels =
    "#main"
    "#ops opskey"
```

---

## Identity and access

See [Permissions](../administration/permissions.md) for how these are evaluated.

### `owner`

| | |
|---|---|
| Type | str |
| Default | *(empty)* |

The owner's nickname, compared case-insensitively. The owner passes every `require_owner` and `require_admin` check.

### `owner_account`

| | |
|---|---|
| Type | str |
| Default | *(empty)* |

The owner's services account name. When it is set **and** ibot knows the sender's account (from `account-tag` or `extended-join`), ownership is decided by comparing accounts (case-sensitive), and `owner` is ignored for that message. When the sender's account is **unknown**, ibot falls back to the `owner` nick comparison.

> **Warning:** Because of the fallback, setting `owner_account` alone doesn't protect you on a network that doesn't send account information. Make sure the owner nick is registered and protected by services. See [Security](../security.md#owner-and-admin-identity).

### `admins`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |

Nicknames treated as bot admins, compared case-insensitively.

```ini
admins = alice, bob
```

### `admin_accounts`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |

Services accounts treated as bot admins (exact, case-sensitive match against the sender's account).

### `extra_owners`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |
| Read | On every message |

Additional bot owners. A sender is an owner if their services account (when known) **or** their nick matches an entry, case-insensitively. Owners are also admins.

```ini
extra_owners = alice, bobs_account
```

> **Warning:** Entries are also compared with the **nick**, even when ibot knows the sender's account. Anyone who can use a listed name as a nick gets owner rights, so list only nicks that are registered and enforced by services. See [Security](../security.md#owner-and-admin-identity).

---

## Commands

### `prefix`

| | |
|---|---|
| Type | str, a **regular expression** |
| Default | `\.` |

The command prefix. Commands are compiled as `^<prefix>(<command>)(?:\s+(.*))?$` with `re.IGNORECASE`, so the prefix is a regex fragment:

| You want users to type | Set `prefix =` |
|---|---|
| `.cmd` | `\.` |
| `!cmd` | `!` |
| `$cmd` | `\$` |
| `.cmd` **or** `!cmd` | `[.!]` |
| `~cmd` | `~` |

> **Warning:** An unescaped `$` or `.` is a regex metacharacter. `prefix = $` matches *end of string* and no command will ever trigger. `prefix = .` matches **any** character, so `xhelp` and `!help` would both run `help`.

> **Note:** The built-in admin plugin's usage messages always show `.` (for example `Usage: .reload <plugin_name>`), whatever prefix is configured.

### `help_prefix`

| | |
|---|---|
| Type | str |
| Default | `.` |
| Used | ❌ |

Kept for Sopel compatibility. ibot has no built-in help command, so the core never reads this key. Help plugins can read it as `bot.config.core.help_prefix`.

---

## Authentication

Full details and examples are in [Authentication](authentication.md).

### `auth_method`

| | |
|---|---|
| Type | str |
| Default | *(empty)*, meaning no authentication |
| Values | `sasl` or `nickserv` (case-insensitive). Any other value is treated as none. |

| Value | Behaviour |
|---|---|
| `sasl` | Requests the `sasl` capability (if the server offers it in `CAP LS`) and performs SASL `PLAIN` before registration completes. If the server doesn't offer SASL, a warning is logged and the bot connects unauthenticated. |
| `nickserv` | After `001`, sends `PRIVMSG <auth_target> :IDENTIFY <auth_password>` and waits 5 seconds before joining channels |

### `auth_user`

| | |
|---|---|
| Type | str |
| Default | *(empty)*, in which case the current nick is used |

The SASL username, used as both authzid and authcid. It is **ignored** by the `nickserv` method, which always sends `IDENTIFY <password>` without an account name.

### `auth_password`

| | |
|---|---|
| Type | str |
| Default | *(empty)* |

The password for SASL or NickServ. With `sasl` and no password, ibot aborts the exchange (`AUTHENTICATE *`) and carries on without logging in.

> **Note:** Write the password exactly as it is. `%` has no special meaning (see [Interpolation](overview.md#interpolation-and-the--character)); if you escaped it as `%%` for an older build, undo that.

### `auth_target`

| | |
|---|---|
| Type | str |
| Default | `NickServ` |

The target that receives `IDENTIFY` when `auth_method = nickserv`.

> **Note:** Log redaction covers messages to `NickServ` and `NS` (any case, with or without `@server`) and, when `auth_method = nickserv`, to the nick part of `auth_target`. The password in `IDENTIFY`, `GHOST` and similar commands is replaced with `[redacted]` in debug (`-v`) logs and in the [raw log](#log_raw).

---

## Database

See [Database](../architecture/database.md) for how the URL is resolved.

### `db_type`

| | |
|---|---|
| Type | str |
| Default | `sqlite` |
| Values | `sqlite`, `mysql`, `postgres`, `postgresql`, `oracle`, `mssql`, or any SQLAlchemy dialect name |

It is ignored when `db_url` is set.

### `db_filename`

| | |
|---|---|
| Type | str (path) |
| Default | *(empty)*, in which case `<config dir>/<config basename>.db` is used |

The SQLite database file. `~` is expanded, and relative paths are resolved against the config file's directory.

```ini
db_filename = glitchy.db
```

### `db_url`

| | |
|---|---|
| Type | str (SQLAlchemy URL) |
| Default | *(none)* |

A full SQLAlchemy URL. When set, it **overrides** every other `db_*` key.

```ini
db_url = postgresql+psycopg2://ibot:YOUR_PASSWORD_HERE@localhost/ibot
```

### `db_user`, `db_pass`, `db_host`, `db_port`, `db_name`

| Key | Default | Notes |
|---|---|---|
| `db_user` | *(none)* | |
| `db_pass` | *(none)* | Only used when `db_user` is also set. It is **not URL-encoded**, so characters such as `@`, `/`, `:` and `#` break the URL. Use `db_url` with percent-encoding instead. |
| `db_host` | `localhost` | |
| `db_port` | *(none)* | |
| `db_name` | *(empty)* | |

These are used only when `db_type` isn't `sqlite` and `db_url` isn't set. The resulting URL is `<driver>://<user>[:<pass>]@<host>[:<port>]/<name>`.

### `db_driver`

| | |
|---|---|
| Type | str |
| Default | Derived from `db_type`: `mysql`→`mysql`, `postgres`/`postgresql`→`postgresql`, `oracle`→`oracle`, `mssql`→`mssql+pymssql`, anything else is passed through |

The SQLAlchemy dialect and driver prefix. Set `mysql+pymysql` if you installed the `mysql` extra.

### `db_dir`

| | |
|---|---|
| Type | str |
| Default | the config directory |
| Used | ❌ |

The value is exposed as `settings.core.db_dir`, but `SopelDB` doesn't use it. Relative `db_filename` values are always resolved against the config directory.

---

## Plugins

See [Plugin management](../administration/plugin-management.md).

### `extra`

| | |
|---|---|
| Type | list of directories |
| Default | *(empty)* |

Extra directories to scan for `*.py` plugins. They are scanned **after** the built-in `ibot/plugins` and **before** `<config dir>/plugins`. A directory that doesn't exist produces the warning `Plugin directory not found: …`.

```ini
extra = /home/ender/.sopel/scripts
```

### `exclude`

| | |
|---|---|
| Type | list of plugin names (file name without `.py`) |
| Default | *(empty)* |

Plugins to skip. This applies at startup and during `.rehash`. `.load <name>` ignores this list.

### `enable`

| | |
|---|---|
| Type | list of plugin names |
| Default | *(empty)*, meaning load everything |

When it isn't empty, **only** the listed plugins load. Add `admin` to the list if you still want the built-in admin plugin.

> **Warning:** `enable = weather` on its own also skips `admin`, which leaves you with no way to rehash or quit from IRC.

---

## Flood control

See [Flood control](../architecture/flood-control.md).

### `flood_burst`

| | |
|---|---|
| Type | int |
| Default | `4` (`0` is also treated as 4) |
| Read | Once, at startup |

The token-bucket capacity: how many queued lines can be sent back to back.

### `flood_refill`

| | |
|---|---|
| Type | int (whole numbers only) |
| Default | `1` (`0` is also treated as 1) |
| Read | Once, at startup |

Tokens added per second. Fractional values such as `0.5` aren't valid integers and fall back to `1`.

### `flood_empty_wait`

| | |
|---|---|
| Type | int |
| Default | `0` |
| Used | ❌ |

Kept for Sopel compatibility only.

---

## Ignore lists

Messages from ignored users never reach plugin functions, unless a function is decorated with `@plugin.unblockable`. The built-in admin plugin's `KICK` and `INVITE` handlers are unblockable.

> **Note:** Both lists are compiled when the dispatcher is created and rebuilt by `.rehash`.

### `nick_blocks`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |

Nicknames to ignore. Matching is exact and IRC-case-insensitive, with no wildcards.

```ini
nick_blocks =
    OtherBot
    AnnoyingUser
```

### `host_blocks`

| | |
|---|---|
| Type | list |
| Default | *(empty)* |

Hostmask patterns matched against the **full** `nick!user@host`, case-insensitively. `*` is the only wildcard and `?` is literal. The pattern must match from the start of the hostmask.

| Pattern | Matches |
|---|---|
| `*!*@spam.example.net` | anyone from `spam.example.net` |
| `*!*@*.example.net` | any subdomain of `example.net` |
| `baduser!*@*` | the nick `baduser` from any host |
| `spam.example.net` | ❌ nothing: there is no `nick!user@` part, so it can't match from the start |

---

## Logging

### `logging_level`

| | |
|---|---|
| Type | str (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| Default | `INFO` |
| Used | ⚠️ read, but **has no effect** |

`__main__.py` reads this value and calls `logging.basicConfig()` a second time. That call does nothing, because the root logger was already configured at `INFO` (or `DEBUG` with `-v`). In practice the level is always `INFO` without `-v` and `DEBUG` with it.

### `logging_format`, `logging_datefmt`

Not used. The format is fixed: `%(asctime)s [%(levelname)s] %(name)s: %(message)s` with date format `%Y-%m-%d %H:%M:%S`.

### `logging_channel` keys

`logging_channel`, `logging_channel_level`, `logging_channel_format` and `logging_channel_datefmt` are not used. ibot doesn't send log records to IRC.

### `log_raw`

| | |
|---|---|
| Type | bool |
| Default | `false` |
| Read | Once, at startup |

When `true`, every line sent and received is written to `<logdir>/<basename>.raw.log`, prefixed with `>>>` (sent) or `<<<` (received). Passwords are redacted the same way as in debug logs. The file rotates at 10 MiB and keeps 3 backups. ibot creates the directory with mode `0700` (if it doesn't exist yet) and sets the file to `0600`.

```ini
log_raw = true
```

> **Warning:** The raw log still contains every message the bot can see, including private messages to it. Treat it as sensitive.

### `logdir`

| | |
|---|---|
| Type | str (path) |
| Default | `logs` in the config file's directory |

The directory for the raw log. `~` is expanded. A relative path is used as it is, relative to the **current working directory**. It isn't used for anything else: the normal log still goes to standard error.

---

## Performance

### `handler_threads`

| | |
|---|---|
| Type | int |
| Default | `64` |
| Read | Once, at startup |

The maximum number of worker threads that run plugin handlers. Workers are started only when needed. `0` or an invalid value means the default. See [Dispatch: Threading model](../architecture/dispatch.md#threading-model).

### `handler_queue_size`

| | |
|---|---|
| Type | int |
| Default | `10000` |
| Read | Once, at startup |

How many handler calls can wait for a free worker. When the queue is full, new calls are dropped and a warning is logged.

```ini
handler_threads = 16
handler_queue_size = 1000
```

---

## Derived (read-only) values

These are attributes of `settings.core`, not keys you set in the file.

| Attribute | Value |
|---|---|
| `settings.core.homedir` | The directory containing the config file |
| `settings.homedir` | Same as above |
| `settings.basename` | The config file name without its extension |
| `settings.filename` | The config path as given on the command line |

---

## Keys ibot does not recognise

`CoreSection` has **no catch-all**. Reading a `[core]` attribute that isn't in the table above (for example `bot.config.core.default_timezone`) raises `AttributeError` in the plugin, even if the key is present in the file.

Sopel keys that ibot neither recognises nor honours include `pid_dir`, `timeout`, `default_timezone`, `default_time_format`, `auto_url_schemes`, `throttle_*`, `modes`, `not_configured`, `commands_on_connect`, `server_auth_*` and `alias_nicks`. You can leave them in the file without causing an error, but they do nothing.

## See also

- [Configuration overview](overview.md)
- [Authentication](authentication.md)
- [Plugin configuration](plugin-config.md)
- [Database](../architecture/database.md)
- [Flood control](../architecture/flood-control.md)

---
[← Back to docs home](../index.md)
