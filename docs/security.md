[Docs home](index.md) › Security

# Security

This page describes ibot's security model, the controls it provides, and the gaps you have to cover yourself. It covers secrets, identity, logging, the commands that carry the most risk, and plugin code.

## In this article

- [Prerequisites](#prerequisites)
- [Security model](#security-model)
- [Protecting secrets on disk](#protecting-secrets-on-disk)
- [Owner and admin identity](#owner-and-admin-identity)
- [High-risk commands](#high-risk-commands)
- [Logging and privacy](#logging-and-privacy)
- [Invites and kicks](#invites-and-kicks)
- [Plugin code and outbound requests](#plugin-code-and-outbound-requests)
- [Message injection](#message-injection)
- [Hardening checklist](#hardening-checklist)
- [Known gaps](#known-gaps)
- [Reporting a vulnerability](#reporting-a-vulnerability)
- [See also](#see-also)

## Prerequisites

- A working bot. See [Quickstart](getting-started/quickstart.md).
- Familiarity with [Permissions](administration/permissions.md).

## Security model

ibot trusts three groups, each with different power:

| Who | Trusted with | How it's established |
|---|---|---|
| Whoever can write the config file or plugin directories | Everything: arbitrary Python code runs as the bot's Unix user | File system permissions |
| The **owner** | `rehash`, `reload`, `load`, `unload`, `plugins`, `raw`, `bnick`, `bquit`/`die`, plus all admin commands | `owner_account`, falling back to the `owner` nick |
| **Admins** | `bjoin`, `bpart`, `say`/`msg`, `act`, `bmode`, `bstatus`, `disable`, `enable`, `disabled`, and any plugin command marked `require_admin` | `admin_accounts` or the `admins` nick list |
| Everyone else | Unrestricted plugin commands, subject to [ignore lists](configuration/core-reference.md#nick_blocks) and [rate limits](architecture/dispatch.md#rate-limiting) | — |

> **Warning:** Plugins run in-process with no sandbox. A plugin can read the config (including every password), the database, and any file the bot's user can read. Only load plugins you have reviewed.

## Protecting secrets on disk

The config file holds credentials such as `auth_password` and plugin API keys (for example `api_key = YOUR_KEY_HERE`).

| Item | ibot's default | Recommendation |
|---|---|---|
| Config file mode | `--generate-config` creates a **new** file with mode `0600`. Files you create yourself, and existing files, keep whatever mode they have. `Config.save()` (used by plugins that write the config) writes with your `umask`. | `chmod 600 bot.cfg` |
| Database files | Created with your `umask` | `chmod 600 *.db` (they can hold user data, such as seen/tell records) |
| `.gitignore` | Ignores `*.cfg` (except `default.cfg`), `*.cfg.*`, `*.orig`, `*~`, `*.db`, `*.db-wal`, `*.db-shm`, `*.db-journal`, `*.log` and `logs/` | Check `git status` before committing; name backups so that they match one of these patterns |
| Raw traffic log (`log_raw`) | Directory created `0700`, file set to `0600` | Keep it off unless you need it |
| Directory | — | `chmod 700` the bot's directory if other users share the host |

```bash
cd ~/ibot
chmod 600 *.cfg *.db
git status --short --ignored   # configs and backups should appear only under "!!" (ignored)
```

> **Warning:** Backups whose names fall outside these patterns, such as `bot-backup.ini` or `secrets.txt`, **aren't ignored**. A careless `git add .` would commit them with every secret inside.

> **Note:** The repository's `.gitignore` contains `!default.cfg`, but `default.cfg` was removed from the repository in commit `5ef25de`. Use `python3 -m ibot --generate-config` instead.

## Owner and admin identity

ibot compares account names when the network provides them, and nicks otherwise. The full rules are in [Permissions](administration/permissions.md#how-the-owner-is-identified). In summary:

| Setting | Strength | Risk |
|---|---|---|
| `owner_account` | Strong while the account is known | **Falls back to the `owner` nick** whenever the sender's account is unknown |
| `owner` (nick) | Weak | Anyone who holds the nick is the owner |
| `extra_owners` | Weak | Each entry is accepted as an account **and** as a nick, even when the sender's account is known. Anyone holding a nick spelled like an entry is an owner. |
| `admin_accounts` | Strong | — |
| `admins` (nick list) | Weak | Always consulted, even for logged-in users |

For the strongest setup:

```ini
[core]
owner =
owner_account = YourAccountName
admins =
admin_accounts = TrustedAccount1,TrustedAccount2
```

Account names are only known when the server offers `account-tag` or `extended-join`, which ibot requests after `CAP LS` (it doesn't request `account-notify`). See [Where account names come from](administration/permissions.md#where-account-names-come-from).

> **Warning:** With `owner` set and `owner_account` empty, anyone who takes your nick while you're offline (for example after a netsplit, or when your nick isn't registered) gets full owner rights, including `.raw` and `.load`.

## High-risk commands

| Command | Level | Risk | Mitigation |
|---|---|---|---|
| `.raw <line>` | Owner | Sends any IRC line as the bot. The command you type, including any password in it, is visible to everyone in the channel and appears **unredacted** in debug and raw logs as an incoming line | Use it only in PM. Never type secrets into it |
| `.load` / `.reload` | Owner | Executes Python files from `plugin_dirs` | Make the plugin directories writable only by the bot's user |
| `.say` / `.msg` / `.act` | Admin | The bot speaks for you in any channel or PM | Grant admin sparingly |
| `.bmode` | Admin | Sets modes, which can affect channels where the bot is op | — |
| `.bjoin` | Admin | Joins are persisted in the database and survive restarts | Review them with `.bstatus` |

## Logging and privacy

ibot logs to standard error through Python `logging.basicConfig`. At the default level (`INFO`) it logs connection events, joins, plugin loads and errors. With `-v` (`DEBUG`) it logs **every line sent and received**. With `[core] log_raw = true` it also writes every line to `<logdir>/<config-name>.raw.log` (see [Core reference](configuration/core-reference.md#log_raw)).

Both the debug log and the raw log pass each line through the same redaction first:

| Line | Logged as | Redacted? |
|---|---|---|
| `AUTHENTICATE <payload>` | `AUTHENTICATE [redacted]` (mechanism names such as `PLAIN` and the `+`/`*` markers stay visible) | ✅ |
| `PASS <password>` | `PASS [redacted]` | ✅ |
| `OPER <name> <password>` | `OPER <name> [redacted]` | ✅ |
| `PRIVMSG`/`NOTICE`/`SQUERY` to `NickServ`, `NS` or the configured NickServ `auth_target` (any case, `@server` ignored) whose text starts with `IDENTIFY`, `ID`, `GHOST`, `RECOVER`, `REGAIN`, `RELEASE`, `REGISTER`, `GROUP`, `LOGIN`, `AUTH`, `CONFIRM`, `RESETPASS`, `SETPASS` or `SET PASSWORD`/`SET PASS` | `PRIVMSG NickServ :IDENTIFY [redacted]` | ✅ |
| `NS`/`NICKSERV`/`CS`/`CHANSERV` server commands with the same verbs | `NS IDENTIFY [redacted]` | ✅ |
| Bare `IDENTIFY …` / `LOGIN …` commands | `IDENTIFY [redacted]` | ✅ |
| `PRIVMSG ChanServ :IDENTIFY …` and other service bots not listed above | in full | ❌ |
| **Incoming** channel and private messages, including your own `.raw` commands as typed | in full | ❌ |
| Plugin output | in full | ❌ |

> **Warning:** Debug and raw logs contain private messages sent to the bot, and any secret typed in a command. Don't share them unredacted. Protect the log files (`chmod 600`), and rotate them. If you run under systemd, the journal is readable by the `adm`/`systemd-journal` groups.

Recommendations:

- Run production bots without `-v` and with `log_raw` off. Turn them on only while you troubleshoot.
- Prefer SASL (`auth_method = sasl`), whose payload is always redacted.
- Before you paste a log into an issue, search it for `IDENTIFY`, `OPER`, `PASS`, `.raw` and your passwords.

## Invites and kicks

| Behaviour | Setting (`[admin]`) | Default | Notes |
|---|---|---|---|
| Accept channel invites | `auto_accept_invite` | `false` | When it's `true`, the bot joins on an invite from the owner or an admin. Other invites are ignored and logged. |
| Rejoin after a kick | `hold_ground` | `false` | Rejoins after 5 seconds. Can cause kick/rejoin loops with channel bots |

> **Warning:** Admin status can be nick-based (`admins`, `owner`, `extra_owners`). With `auto_accept_invite = true`, anyone who can take one of those nicks can pull the bot into arbitrary channels. Use account-based admins if you enable it.

## Plugin code and outbound requests

- `sopel.tools.web.get()` refuses non-HTTP(S) schemes and hosts that resolve to private, loopback, link-local, multicast, reserved or unspecified addresses, re-checks every redirect, and reads at most 5 MiB by default. Plugins can opt out with `allow_private=True` or `max_bytes=0`. See [Tools reference](developer-guide/tools-reference.md#sopeltoolsweb).
- The address check resolves the host separately from the connection, and lets the request through when that resolution fails. It doesn't defend against DNS rebinding.
- Plugins that use `requests` or `urllib` directly get **no** protection. They can call `web.check_url(url)` before fetching.
- Plugin handlers run on a bounded pool (`handler_threads`, default 64) with a bounded queue (`handler_queue_size`, default 10000). Slow handlers can fill the pool and delay or drop other handlers' work, but can't create unlimited threads. See [Dispatch](architecture/dispatch.md#threading-model).

## Message injection

Every outgoing line goes through a final clean-up before it reaches the socket: CR, LF and NUL are replaced with spaces, and the line is cut to 510 bytes on a UTF-8 character boundary. A plugin therefore can't inject a **second** IRC command through user-controlled text. `say()`, `msg()`, `notice()` and `reply()` split multi-line text into separate messages first; `action()` sends one action per line; `write()`, `join()`, `part()` and `kick()` force each argument onto a single line.

> **Note:** User text can still add *parameters* to the single line a plugin builds. For example `bot.write(['MODE', trigger.group(2)])` lets the user choose any mode string. Validate input before you pass it to `write()`.

See [Flood control: line safety](architecture/flood-control.md#line-safety).

## Hardening checklist

| ✔ | Action |
|---|---|
| ☐ | `owner_account` set; `owner` empty, or a services-protected nick |
| ☐ | `admin_accounts` used instead of `admins` |
| ☐ | SASL authentication over TLS (`use_ssl = true`, `verify_ssl = true`) |
| ☐ | `chmod 600` on config and database files; backups ignored by git |
| ☐ | Plugin directories writable only by the bot's user |
| ☐ | `auto_accept_invite` off, or only account-based admins |
| ☐ | `extra_owners` empty, or listing only names that are protected as nicks too |
| ☐ | Production runs without `-v` and `log_raw`; logs protected and rotated |
| ☐ | The bot runs as an unprivileged, dedicated user |
| ☐ | Third-party plugins reviewed before you install them |

## Known gaps

These describe the code as documented. Check the [changelog](changelog.md) for fixes.

- Owner identity falls back to the nick when the account is unknown, and `admins` and `extra_owners` match nicks even for logged-in users.
- Incoming lines are never redacted, so `.raw` commands with secrets appear in logs and in the channel.
- `web.check_url()` doesn't stop DNS rebinding, and allows the request when the check's DNS lookup fails.
- Config and database file permissions aren't enforced on existing files, and `Config.save()` writes with the `umask`.

## Reporting a vulnerability

Report security issues privately to the maintainer (`lord3nd3r` on GitHub, `End3r` on IRC), not in a public issue. Include the ibot commit (`git rev-parse --short HEAD`), and redact all secrets from logs.

## See also

- [Permissions](administration/permissions.md)
- [Authentication](configuration/authentication.md)
- [Running as a service](getting-started/running-as-a-service.md)
- [Troubleshooting](troubleshooting.md)

---
[← Back to docs home](index.md)
