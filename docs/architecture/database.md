[Docs home](../index.md) › Architecture › Database

# Database

ibot stores persistent data with SQLAlchemy, using **the same schema as Sopel**. An existing Sopel database works as it is, and plugins use the familiar `bot.db` API. This page covers configuration, the schema, the API, the data ibot itself stores, and backups.

## In this article

- [Prerequisites](#prerequisites)
- [Choosing a database](#choosing-a-database)
- [Schema](#schema)
- [Value encoding](#value-encoding)
- [The bot.db API](#the-botdb-api)
- [Data stored by ibot itself](#data-stored-by-ibot-itself)
- [Concurrency](#concurrency)
- [Backups and inspection](#backups-and-inspection)
- [Migrating from Sopel](#migrating-from-sopel)
- [See also](#see-also)

## Prerequisites

- SQLAlchemy 2.x (installed from `requirements.txt`).
- For MySQL or PostgreSQL, a driver such as `pymysql` or `psycopg2`, plus a database and user created in advance.

## Choosing a database

The database is opened once, when `IRCBot` is created, and the tables are created if they don't exist.

| Configuration | Resulting URL |
|---|---|
| Nothing set | `sqlite:///<config dir>/<config basename>.db`. For `glitchy.cfg`, that's `glitchy.db` next to it. |
| `db_filename = bot.db` | `sqlite:///<config dir>/bot.db` (relative paths are resolved against the config directory, and `~` is expanded) |
| `db_url = postgresql://user:PASSWORD@localhost/ibot` | Used as given. It takes priority over every other `db_*` key. |
| `db_type = mysql` with `db_user`, `db_pass`, `db_host`, `db_port`, `db_name` | `mysql://user:pass@host:port/name` |
| `db_driver = mysql+pymysql` | Replaces the scheme part of the built URL |

Driver map, used when `db_driver` isn't set:

| `db_type` | Scheme |
|---|---|
| `mysql` | `mysql` |
| `postgres`, `postgresql` | `postgresql` |
| `oracle` | `oracle` |
| `mssql` | `mssql+pymssql` |
| anything else | used as it is |

`db_host` defaults to `localhost`. The engine is created with `pool_recycle=3600`. See [Core reference](../configuration/core-reference.md#db_type) for each key.

> **Warning:** `db_pass` and `db_url` contain credentials. Keep the config file readable only by the bot's user (`chmod 600`). The password isn't URL-encoded, so passwords containing `@`, `/` or `:` need `db_url` with percent-encoding.

## Schema

| Table | Columns | Purpose |
|---|---|---|
| `nick_ids` | `nick_id` (PK) | One row per nick *group* |
| `nicknames` | `nick_id` (FK), `slug` (PK), `canonical` | Maps lower-cased nicks (slugs) to a group, so aliases share data |
| `nick_values` | `nick_id` (PK, FK), `key` (PK), `value` (Text) | Per-nick data |
| `channel_values` | `channel` (PK), `key` (PK), `value` (Text) | Per-channel data. The channel is stored lower-cased (IRC casefold). |
| `plugin_values` | `plugin` (PK), `key` (PK), `value` (Text) | Per-plugin data. The plugin name is stored lower-cased. |

Nick slugs and channel names use ibot's `Identifier` lower-casing.

## Value encoding

Values are stored as JSON (`json.dumps(value, ensure_ascii=False)`) and decoded with `json.loads` when they're read. If a stored value isn't valid JSON, for example one written by hand, it's returned as a plain string.

| You store | You get back |
|---|---|
| `42` | `42` |
| `['#a', '#b']` | `['#a', '#b']` |
| `{'k': 1}` | `{'k': 1}` |
| `('a', 'b')` | `['a', 'b']`: tuples become lists |
| `datetime` | ❌ `TypeError`: JSON can't encode it, so store `isoformat()` instead |

## The bot.db API

Every method opens and commits its own session.

| Method | Description |
|---|---|
| `get_nick_id(nick, create=False)` | Returns the group ID. Raises `ValueError` if the nick is unknown and `create` is false. |
| `alias_nick(nick, alias)` | Adds `alias` to `nick`'s group. Raises `ValueError('Alias already exists.')`. |
| `unalias_nick(alias)` | Removes an alias. Raises `ValueError` if it's the only entry in its group. |
| `merge_nick_groups(first, second)` | Merges `second` into `first` in one transaction. Values `first` already has win; merging a group with itself is a no-op. |
| `forget_nick_group(nick)` | Deletes a group and all its values |
| `set_nick_value(nick, key, value)` / `get_nick_value(nick, key, default=None)` | Per-nick data |
| `get_nick_values(nick)` | All of a nick's values |
| `delete_nick_value(nick, key)` | Deletes one value. An unknown nick is ignored. |
| `set_channel_value` / `get_channel_value` / `get_channel_values` / `delete_channel_value` / `forget_channel` | Per-channel equivalents |
| `set_plugin_value` / `get_plugin_value` / `get_plugin_values` / `delete_plugin_value` / `forget_plugin` | Per-plugin equivalents |
| `get_nick_or_channel_value(name, key, default=None)` | Channel or nick lookup, depending on the name |
| `get_preferred_value(names, key)` | The first non-`None` value from a list of names |
| `session()` | A SQLAlchemy `Session` for custom queries |
| `connect()` | A raw DBAPI connection (legacy) |
| `get_uri()` | The database URL. **It contains the password if one is configured**, so never send it to IRC. |
| `close()` | Disposes of the engine (called at shutdown) |

```python
from sopel import plugin

@plugin.command('seen')
def seen(bot, trigger):
    who = trigger.group(2)
    if not who:
        bot.reply('Usage: .seen <nick>')
        return
    last = bot.db.get_nick_value(who.strip(), 'seen_text')
    bot.reply(last or "I haven't seen them.")
```

## Data stored by ibot itself

| Table | Key | Written by | Content |
|---|---|---|---|
| `plugin_values` | plugin `admin`, key `persistent_channels` | `.bjoin`, `.bpart` | A JSON list of channel names to join on connect |
| `channel_values` | key `disabled_plugins` | `.disable`, `.enable` | A JSON list of plugin names disabled in that channel |

The disabled-plugin lists are read into `bot.memory['disabled_plugins']` at startup and on `.rehash`. Editing the table directly takes effect only after one of those.

## Concurrency

- Handlers run in many threads, and each call opens its own session from a thread-local `scoped_session`.
- With SQLite, every new connection runs `PRAGMA busy_timeout = 10000` and `PRAGMA journal_mode = WAL`. WAL lets readers and one writer work at the same time; the busy timeout makes a writer wait up to 10 s for the lock instead of failing at once with `database is locked`. If WAL can't be enabled (for example on a read-only filesystem), the default journal mode is kept and a DEBUG message is logged.
- In WAL mode SQLite keeps two side files next to the database, `<name>.db-wal` and `<name>.db-shm`. They're part of the database: don't delete them while the bot runs, and include them in file-level backups (or use `.backup`, below). The repository's `.gitignore` excludes them.
- `get_nick_id(..., create=True)` is serialised inside the process and retries on `IntegrityError` or a locked database, so concurrent calls don't create duplicate nick groups. On SQLite ibot also creates a unique index `ix_ibot_nicknames_slug_unique` on `nicknames.slug`, but only if the table has no duplicate slugs already (otherwise it logs a warning and carries on).
- Read-modify-write sequences (`get` → change → `set`) aren't atomic. Two concurrent `.bjoin`s can lose an update.

## Backups and inspection

```bash
# Consistent online backup of the SQLite database
sqlite3 ~/ibot/mybot.db ".backup '/backups/mybot-$(date +%F).db'"

# List the tables without printing any data
sqlite3 ~/ibot/mybot.db '.tables'
```

> **Warning:** The database can contain personal data stored by plugins: nicks, messages, locations, API tokens. Protect it like the config file (`chmod 600`), and think twice before sharing dumps.

## Migrating from Sopel

1. Stop Sopel.
2. Copy its database (by default `~/.sopel/<basename>.db`) next to your ibot config, or point `db_filename` at it.
3. Start ibot. The schema is identical, so no migration step is needed.

> **Note:** ibot doesn't use Sopel's Alembic migration history. Databases created by ibot have the tables but no `alembic_version` table. On SQLite, ibot also adds the extra index `ix_ibot_nicknames_slug_unique` (see [Concurrency](#concurrency)); Sopel ignores it.

> **Warning:** After ibot has opened a SQLite file it's in WAL mode, which persists in the file. Copy the `-wal` file too (or checkpoint first, for example with `sqlite3 file.db 'PRAGMA wal_checkpoint(TRUNCATE);'` while the bot is stopped) when moving the database back to Sopel.

## See also

- [Core reference: database keys](../configuration/core-reference.md#db_type)
- [Plugin API reference](../developer-guide/plugin-api-reference.md)
- [Security](../security.md)

---
[← Back to docs home](../index.md)
