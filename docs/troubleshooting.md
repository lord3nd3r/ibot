[Docs home](index.md) › Troubleshooting

# Troubleshooting

This page lists common ibot problems by symptom. Each entry gives the likely causes, how to confirm them, and the fix.

## In this article

- [Prerequisites](#prerequisites)
- [Collecting diagnostics](#collecting-diagnostics)
- [The bot doesn't start](#the-bot-doesnt-start)
- [The bot doesn't connect or register](#the-bot-doesnt-connect-or-register)
- [Authentication fails](#authentication-fails)
- [The bot doesn't join channels](#the-bot-doesnt-join-channels)
- [The bot ignores all commands](#the-bot-ignores-all-commands)
- [The bot ignores my admin commands](#the-bot-ignores-my-admin-commands)
- [A plugin doesn't load](#a-plugin-doesnt-load)
- [A command runs the wrong handler or nothing at all](#a-command-runs-the-wrong-handler-or-nothing-at-all)
- [Changes don't take effect](#changes-dont-take-effect)
- [The bot is slow to reply or gets disconnected for flooding](#the-bot-is-slow-to-reply-or-gets-disconnected-for-flooding)
- [The bot goes silent or takes a long time to reconnect](#the-bot-goes-silent-or-takes-a-long-time-to-reconnect)
- [Database errors](#database-errors)
- [Interval jobs stop running](#interval-jobs-stop-running)
- [Log messages explained](#log-messages-explained)
- [See also](#see-also)

## Prerequisites

- Shell access to the machine that runs the bot
- The bot's config file. You'll read **key names** from it; you don't need to share the values.

## Collecting diagnostics

Start the bot in the foreground with debug logging:

```bash
cd ~/ibot
python3 -m ibot bot.cfg -v 2>&1 | tee /tmp/ibot-debug.log
```

`-v` logs every line sent (`>>>`) and received (`<<<`). To capture traffic without the rest of the debug output, set `log_raw = true` in `[core]` and restart; lines then go to `<logdir>/<config-name>.raw.log`.

> **Warning:** Debug and raw logs include private messages and anything typed into commands. Passwords in outgoing `AUTHENTICATE`, `PASS`, `OPER` and NickServ lines are redacted, but incoming lines aren't. Review them before you share them. See [Security: logging and privacy](security.md#logging-and-privacy).

Useful checks:

| Check | Command |
|---|---|
| ibot version | `python3 -c 'import ibot; print(ibot.__version__)'` |
| Commit | `git -C ~/ibot log -1 --oneline` |
| Python and SQLAlchemy | `python3 -V; python3 -c 'import sqlalchemy; print(sqlalchemy.__version__)'` |
| Config key names, without values | `grep -oE '^\s*[A-Za-z_]+\s*=' bot.cfg` |
| Live state, from IRC | `.bstatus` (admin) |

## The bot doesn't start

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: sqlalchemy` | Dependencies not installed in this interpreter | `pip install -e .` in the venv you run from |
| `No module named ibot` | Running from the wrong directory without an install | `cd ~/ibot`, or `pip install -e .` |
| `Config file not found: …`, then exit code 1 | The config path is wrong. The default is `ibot.cfg` in the **current directory** | Pass the path explicitly (`python3 -m ibot /path/bot.cfg`), or create one with `--generate-config` |
| Errors about the database driver | `db_type = mysql`/`postgres` without the driver | `pip install -e '.[mysql]'` or `'.[postgres]'` |
| Login fails after upgrading, with a password containing `%%` | Older builds needed `%` escaped as `%%`; this one reads values literally | Replace `%%` with `%`. See [Interpolation](configuration/overview.md#interpolation-and-the--character) |

## The bot doesn't connect or register

| Symptom (with `-v`) | Cause | Fix |
|---|---|---|
| `Connection error` with an SSL traceback | `use_ssl` on a plain-text port, or the reverse | Rizon and most networks use TLS on `6697`, plain on `6667` |
| `CERTIFICATE_VERIFY_FAILED` | Self-signed or mismatched certificate | Fix the server name in `host`, or set `verify_ssl = false` (less secure) |
| `Nick Bot unavailable (433: …); trying Bot_` | The nick is in use | Normal. ibot tries `Bot_`, `Bot__`, then `Bot_<number>`. With a NickServ or SASL password configured it then logs `Nick Bot is taken; asking NickServ to GHOST it` and switches back; without one it logs `… not attempting to regain it`. See [Nick collisions](architecture/connection-lifecycle.md#nick-collisions) |
| `No usable nick after 20 attempts; dropping connection to retry later` | Every candidate nick was refused | Change `nick`; check for a network-wide nick ban |
| Accounts never known | The `Server capabilities: …` line lists neither `account-tag` nor `extended-join` | Owner/admin checks fall back to nicks on that network. A `CAP NAK` warning is followed by one-at-a-time retries, so it's usually harmless. See [Registration and CAP](architecture/connection-lifecycle.md#registration-and-cap) |
| `Reconnecting` right after `No reply from server 60s after keepalive PING` | The link went dead | Normal recovery. If it repeats, check the network path |
| `Reconnecting in N seconds` loop | The server closes the link: K-line, throttling, wrong port | Read the `ERROR :` line just before it |

## Authentication fails

| Symptom | Cause | Fix |
|---|---|---|
| `SASL authentication failed (904): …` (also 902/905/906) | Wrong `auth_user`/`auth_password`, or the account doesn't exist | Check the credentials. ibot continues registering **without** SASL |
| `SASL is configured but the server does not offer the 'sasl' capability; continuing WITHOUT SASL`, or `Server refused (NAK) the SASL capability` | The network has no SASL (or not on this port) | Use `auth_method = nickserv` on that network |
| NickServ says "nickname is not registered" | `auth_target` is wrong, or the bot's current nick isn't the registered one | Check `nick`; NickServ identifies the **current** nick |
| Joins to `+R` channels fail | Joined before identification completed | ibot retries `477` with back-off, starting at 10 s. See below |

See [Authentication: failure modes](configuration/authentication.md#failure-modes).

## The bot doesn't join channels

| Log line | Meaning | What ibot does |
|---|---|---|
| `Failed to join #c: … (code 471)` | Channel full | Logs `Will retry joining #c in N seconds`, retrying after 10 s, 20 s, 40 s … (at most 300 s), up to 8 times, then `Giving up on joining #c after 8 retries` |
| `… (code 477)` | You need to be identified | The same retry schedule |
| `… (code 473)` | Invite-only | Gives up. Invite the bot and set `[admin] auto_accept_invite`, or use `.bjoin` after inviting |
| `… (code 474)` | Banned | Gives up |
| `… (code 475)` | Wrong or missing key | Gives up |

Also check:

- `channels` in `[core]`: write it as one comma-separated line (`channels = #main, #offtopic`). Indented lines that start with `#` are treated as comments, so a multi-line list silently loses its channels. See [Comments and the # character](configuration/overview.md#comments-and-the--character).
- Retries don't include a channel key, so a keyed (`+k`) channel that was full is retried without its key and then fails with `475`.
- Persistent channels added with `.bjoin` are joined in addition to `channels`. `.bpart` parts the channel and removes it from the persistent list, but a channel that's also in `channels` is joined again at the next connect. See [Per-channel settings](configuration/per-channel.md).

## The bot ignores all commands

Work through this list in order:

1. **Prefix.** The prefix is a regular expression. `prefix = $` or `prefix = .` doesn't do what you expect. Use `\$` or `\.`. See [`prefix`](configuration/core-reference.md#prefix).
2. **Ignore lists.** Are you in `nick_blocks`, or does your hostmask match `host_blocks`? See [`nick_blocks`](configuration/core-reference.md#nick_blocks).
3. **Plugin disabled in this channel.** In PM to the bot, run `.disabled #channel`. See [Per-channel settings](configuration/per-channel.md#disabling-plugins-per-channel).
4. **The plugin isn't loaded.** Owner: `.plugins`. Look for `Loaded plugin` lines at startup.
5. **Rate limited.** The handler has `@plugin.rate`, and you hit it recently.
6. **The bot isn't really in the channel**, or it's quieted or banned. Check `.bstatus`, and the channel's ban list.
7. **Another bot.** If your client is flagged as a bot (the `bot` message tag), handlers without `@plugin.allow_bots` skip you.

## The bot ignores my admin commands

The admin plugin's restrictions are **silent**: when a check fails, ibot doesn't reply.

| Cause | How to confirm | Fix |
|---|---|---|
| The command is owner-only | See the [command summary](administration/admin-commands.md#command-summary): `rehash`, `reload`, `load`, `unload`, `plugins`, `raw`, `bnick`, `bquit`/`die` are owner-only | Set `owner`/`owner_account` |
| You ran `disable`/`enable`/`disabled` in a channel | These are **PM-only** | `/msg Bot .disable #chan plugin` |
| `owner_account` is set but doesn't match your account **exactly** | Account comparison is case-sensitive | Copy the account name exactly as services report it (`/msg NickServ INFO yournick`) |
| You're logged in to a different account | When your account is known, the owner check uses only the account, not the nick | Log in to the right account, or update `owner_account` |
| You're identified with NickServ, but ibot doesn't know your account | ibot learns accounts from `account-tag`/`extended-join`. If neither cap is enabled, it compares nicks | Use `owner`/`admins` on that network, or rejoin a channel after identifying |
| Your nick differs from `owner`/`admins` | Comparison uses `str.lower()`, so `Ender|away` isn't `Ender` | Add the alternate nick, or use accounts |
| The config change hasn't been loaded | You edited the file but haven't reloaded it | `.rehash` (owner), or restart. If you aren't the owner yet, restart |
| Wrong prefix | glitchy uses `$`, not `.`, even though usage messages print `.` | Type `$bstatus` |
| Another plugin registers the same command name | Only the first matching command handler runs | See the next section |

See [Permissions](administration/permissions.md) and [Security: owner and admin identity](security.md#owner-and-admin-identity).

## A plugin doesn't load

| Log or reply | Cause | Fix |
|---|---|---|
| `Plugin not found` | The file isn't in `plugin_dirs`, or the name is different | The name is the file name without `.py`. See [Plugin search path](administration/plugin-management.md#plugin-search-path) |
| `Reload failed (previous version kept): …` | The new file didn't import, or its `setup()` raised. The old version is still running | Fix it, then `.reload` again |
| `Load failed: …` | Import error, or `setup()` raised. The plugin isn't loaded | Fix it, then `.load` again |
| `Plugin <name> disabled because its setup failed` at startup | `setup()` raised. The plugin is unregistered | Fix it, then `.load <name>` |
| A traceback while importing, after which the plugin is missing | Syntax or import error | `python3 -m py_compile file.py`; install missing modules into the bot's venv |
| Loaded, but `0 commands` | Functions aren't decorated, or are imported from another module | See [What counts as a plugin](administration/plugin-management.md#what-counts-as-a-plugin) |
| Skipped at startup | Listed in `exclude`, or not in a non-empty `enable` | See [Choosing which plugins load](administration/plugin-management.md#choosing-which-plugins-load) |
| A package directory isn't loaded | Only single `.py` files count as plugins | Flatten the plugin |

## A command runs the wrong handler or nothing at all

ibot sorts command handlers by `(priority, plugin name, function name)`, and **stops after the first command whose pattern matches**, even when that handler is then filtered out (for example by `require_admin`, `allow_bots`, or a per-channel disable).

- Two plugins defining `.weather`: only the first in sort order is considered.
- A line that matches a command doesn't reach URL handlers or `@rule` handlers.

Fix: rename one command, set `@plugin.priority('high')` on the one you want, or `exclude` the duplicate plugin. See [Dispatch: known limitations](architecture/dispatch.md#known-limitations).

## Changes don't take effect

| Change | Needs |
|---|---|
| Plugin code | `.reload name` |
| Plugin config sections, `prefix`, owner/admin lists, `nick_blocks`, `host_blocks`, `[#channel] disable_plugins` | `.rehash` |
| `flood_*`, `handler_threads`, `handler_queue_size`, `log_raw`, `logdir`, `db_*`, `extra` | Restart |
| `host`, `port`, `use_ssl`, `bind_host`, `user`, `name` | `.rehash`, then a reconnect (or restart) |

See the full table in [Applying changes](configuration/overview.md#applying-changes).

## The bot is slow to reply or gets disconnected for flooding

| Symptom | Cause | Fix |
|---|---|---|
| Replies trickle out about 1 per second after a burst | The token bucket is empty | Normal. Tune [`flood_burst`](configuration/core-reference.md#flood_burst) and [`flood_refill`](configuration/core-reference.md#flood_refill) |
| `Excess Flood` quits | The bucket is too generous for the network | Lower `flood_burst` (the burst size) and keep `flood_refill` at `1` |
| Nothing is ever sent | A negative `flood_burst` or `flood_refill` | Use positive values. See [Flood control](architecture/flood-control.md) |
| Long output truncated | `say()` sends one chunk by default (`max_messages=1`) | Use `bot.say(text, max_messages=3)` |
| Everything slow, or `Handler queue full (N workers busy); dropped N job(s) so far` | Slow handlers occupy all `handler_threads` workers | Find the slow plugin and add timeouts to its web requests. Raise `handler_threads` only if the work is legitimately slow |

## The bot goes silent or takes a long time to reconnect

- **Silent but still "connected":** after 240 s without any data ibot sends a keepalive `PING`, and reconnects if nothing arrives within another 60 s. A dead link is therefore noticed within about 5 minutes. See [Keepalive](architecture/connection-lifecycle.md#keepalive).
- **Reconnect waits up to 300 s:** the delay doubles on each failed attempt (5 s, 10 s, … 300 s) and resets to 5 s after a successful registration. See [Reconnects](architecture/connection-lifecycle.md#reconnects).
- **Nick changed with `.bnick` is lost after a reconnect:** each connection starts again from the nick the bot was started with.
- **Several seconds between registering and joining with `auth_method = nickserv`:** ibot waits 5 s after sending `IDENTIFY` so the login completes before it joins. During that wait it doesn't process incoming lines.

## Database errors

| Symptom | Cause | Fix |
|---|---|---|
| `database is locked` | Another process (a second bot, or `sqlite3` holding a transaction) held the SQLite file for more than the 10 s `busy_timeout` | Use one database per bot, and close other sessions |
| `<name>.db-wal` and `<name>.db-shm` files next to the database | Normal: ibot uses SQLite WAL mode | Back up all three files together, or stop the bot first |
| The database is in an unexpected place | Relative `db_filename` resolves against the **config file's directory** | Use an absolute path |
| Settings lost after a restart | A different `db_filename` or `db_url` | Check the `[core] db_*` key names in the config |

See [Database](architecture/database.md).

## Interval jobs stop running

A job that raises **5 times in a row** is disabled until the next reconnect, restart or reload of its plugin. Between failures it backs off: 5 s, 10 s, 20 s… up to the interval itself. Look for `Error in interval job plugin.func (failure N/5)` tracebacks in the log. `.reload <plugin>` cancels the old jobs and starts the new ones.

## Log messages explained

| Message | Meaning |
|---|---|
| `SASL authentication successful` | Logged in to services |
| `Server capabilities: …` | The capabilities the server offers (from `CAP LS`) |
| `SASL authentication failed (N): …` | See [Authentication fails](#authentication-fails) |
| `Failed to join #c: reason (code N)` | See [The bot doesn't join channels](#the-bot-doesnt-join-channels) |
| `Kicked from #c, rejoining in 5 seconds (hold_ground=true)` | `[admin] hold_ground` is on |
| `Received invite to #c from nick, joining` | `[admin] auto_accept_invite` is on and the inviter is an admin |
| `Ignoring invite to #c from non-admin nick` | `auto_accept_invite` is on, but the inviter isn't an admin or the owner |
| `Reconnecting in N seconds...` | The connection was lost; reconnect is pending |
| `Connection error` | An exception during connect or read. The traceback follows |
| `Skipping already loaded plugin: name` (debug) | A second file with the same name was found later in the search path, and ignored |
| `Config file not found: path` | The bot exited. See [The bot doesn't start](#the-bot-doesnt-start) |
| `CAP NAK: …` (warning) | The server refused a capability request. If it named several caps, ibot retries them one at a time |
| `No data from server for 240s; sending keepalive PING` | Keepalive check. Harmless on quiet networks |
| `Disabling interval job plugin.func after 5 consecutive failures` | See [Interval jobs stop running](#interval-jobs-stop-running) |

## See also

- [FAQ](faq.md)
- [Connection lifecycle](architecture/connection-lifecycle.md)
- [Dispatch](architecture/dispatch.md)
- [Security](security.md)

---
[← Back to docs home](index.md)
