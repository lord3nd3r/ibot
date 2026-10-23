[Docs home](../index.md) › Configuration › Authentication

# Authentication (SASL, NickServ and oper)

This page explains how ibot logs in to network services with SASL `PLAIN` or a NickServ `IDENTIFY`, what happens when authentication fails, and how IRC operator (`OPER`) credentials relate to ibot.

## In this article

- [Prerequisites](#prerequisites)
- [Choosing a method](#choosing-a-method)
- [SASL PLAIN](#sasl-plain)
- [NickServ IDENTIFY](#nickserv-identify)
- [Capability negotiation details](#capability-negotiation-details)
- [Verifying that you are logged in](#verifying-that-you-are-logged-in)
- [Failure modes](#failure-modes)
- [IRC operator (OPER) credentials](#irc-operator-oper-credentials)
- [Account-based permissions](#account-based-permissions)
- [See also](#see-also)

## Prerequisites

- A services account registered for the bot's nick, for example with `/msg NickServ REGISTER …` on Rizon or Libera.Chat.
- The account password. Store it only in the config file and run `chmod 600` on that file.

## Choosing a method

| | `sasl` | `nickserv` |
|---|---|---|
| When you're logged in | **Before** registration completes, so before any channel is joined | After `001`, plus a fixed 5-second wait |
| Works with `+R` / registered-only channels on the first join | Yes | Usually, thanks to the 5-second wait |
| Exposes the password in plaintext on the wire | Base64 only. Use TLS. | Yes, as a `PRIVMSG`. Use TLS. |
| Needs IRCv3 `CAP` support | Yes | No |
| Custom service target | No | `auth_target` |
| Separate account name | `auth_user` | No. `IDENTIFY <password>` only, against the current nick. |

> **Note:** Use `sasl` wherever the network supports it (Libera.Chat, OFTC, Rizon and most modern networks). Use `nickserv` for networks or services packages without SASL.

## SASL PLAIN

```ini
[core]
nick = MyBot
host = irc.libera.chat
port = 6697
use_ssl = true
auth_method = sasl
auth_user = MyBotAccount       ; optional, defaults to the nick
auth_password = YOUR_PASSWORD_HERE
```

The exchange looks like this (with `-v`, credentials redacted):

```text
>>> CAP LS 302
>>> NICK MyBot
>>> USER MyBot 0 * :MyBot - ibot
<<< :server CAP * LS :account-tag extended-join multi-prefix sasl=PLAIN,EXTERNAL server-time …
>>> CAP REQ :account-tag extended-join multi-prefix sasl server-time
<<< :server CAP MyBot ACK :account-tag extended-join multi-prefix sasl server-time
>>> AUTHENTICATE PLAIN
<<< AUTHENTICATE +
>>> AUTHENTICATE [redacted]
<<< :server 903 MyBot :SASL authentication successful
>>> CAP END
<<< :server 001 MyBot :Welcome …
```

| Detail | Value |
|---|---|
| Mechanism | `PLAIN` only. `EXTERNAL` (CertFP) and `SCRAM` aren't supported. |
| Credential string | `<user>\0<user>\0<password>`, with `<user>` = `auth_user` or the current nick |
| Long credentials | Not split into 400-byte chunks. Keep user + password well below ~290 characters. |
| `auth_password` empty | ibot sends `AUTHENTICATE *` (abort), logs `SASL: No password configured`, and continues unauthenticated |
| Server doesn't offer `sasl` | Logs `SASL is configured but the server does not offer the 'sasl' capability; continuing WITHOUT SASL` |
| Failure numerics | `902`, `904`, `905`, `906` log `SASL authentication failed (<code>): …` (redacted); `907` logs `SASL: already authenticated`. In every case negotiation ends with `CAP END` and the bot continues. |
| Decided | Once, at **startup**. Switching `auth_method` to or from `sasl` needs a restart. |

## NickServ IDENTIFY

```ini
[core]
auth_method = nickserv
auth_password = YOUR_PASSWORD_HERE
auth_target = NickServ          ; default
```

After the server's welcome (`001`), ibot sends:

```text
PRIVMSG NickServ :IDENTIFY YOUR_PASSWORD_HERE
```

It then waits **5 seconds** before it sends its `JOIN`s, so that registered-only channels accept the bot.

| Detail | Value |
|---|---|
| Account name | Not sent. `auth_user` is ignored for this method. |
| Response checking | None. ibot doesn't read NickServ's reply. Check it yourself (see below). |
| Nick ghosting / recovery | Automatic. If the bot had to register on a fallback nick (`MyBot_`), it identifies as that nick first, then sends `PRIVMSG <auth_target> :GHOST MyBot <password>`, waits 3 s, sends `NICK MyBot`, waits 3 s and, once it's on `MyBot`, sends `IDENTIFY` again. |
| `auth_target` | For example `NickServ@services.example.net` on networks that require it |

> **Note:** Passwords in `IDENTIFY`, `GHOST` and similar service commands are replaced with `[redacted]` in debug (`-v`) logs and the raw log. This covers `NickServ`, `NS`, and (for this method) the nick part of a custom `auth_target`. See [Security](../security.md#logging-and-privacy).

> **Note:** The 5-second wait runs inside the connection's read loop, so the bot doesn't process incoming lines (or answer `PING`) during it. Five seconds is well within any server's ping timeout.

## Capability negotiation details

ibot opens registration with `CAP LS 302` and waits for the full (possibly multi-line) list of capabilities the server offers. It then sends one `CAP REQ` for those of the following that the server **actually offers**:

| Capability | Why |
|---|---|
| `account-tag` | Gives every message the sender's account, which is used for `owner_account` / `admin_accounts` / `extra_owners` |
| `extended-join` | Gives the account on `JOIN` |
| `multi-prefix` | Lets `NAMES` show all of a user's channel modes |
| `server-time` | Message timestamps (`trigger.time`) |
| `sasl` | Only when `auth_method = sasl` |

The offered list is logged as `Server capabilities: …` and the accepted ones as `CAP ACK: …`. `CAP END` is sent once every request has been answered and SASL (if used) has finished.

If the server still rejects the request (`CAP NAK`), ibot retries each capability in a separate `CAP REQ`, once per connection, so one unsupported capability doesn't cost the others. If `sasl` itself is refused, it logs `Server refused (NAK) the SASL capability; continuing WITHOUT SASL`. `CAP DEL` and `CAP NEW` are logged; a deleted capability is no longer used.

`account-notify` isn't requested, so account changes after a user joins are only seen through `account-tag`.

## Verifying that you are logged in

- With SASL, look for `SASL authentication successful` in the log.
- With either method, run `.raw WHOIS MyBot` as the owner and check for the server's `is logged in as` line in a verbose log. You can also `/whois MyBot` from your own client.
- On Rizon and Anope-based networks, `/msg NickServ INFO MyBot` shows the last-seen and online status.

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `SASL authentication failed: … 904 …` | Wrong account or password | Fix `auth_user` / `auth_password`. ibot continues unauthenticated. |
| `SASL is configured but the server does not offer the 'sasl' capability` | The network has no SASL (or not on this port) | Use `nickserv` |
| `Server refused (NAK) the SASL capability` | The server refused SASL | Use `nickserv` |
| No `SASL` lines and no `CAP` lines at all | The server doesn't support `CAP` | Use `nickserv` |
| Password rejected after upgrading | The password was escaped as `%%` for an older build | Write `%` once (see [Interpolation](overview.md#interpolation-and-the--character)) |
| Joined `+R` channel fails with `477` | Identification hadn't completed yet | ibot retries the join every 10 s. Prefer SASL. |
| Bot stays on `MyBot_` | Nick in use (a second instance, or no password configured for the automatic `GHOST`) | Check the log for `asking … to GHOST it`. Otherwise `/msg NickServ GHOST MyBot` / `RECOVER`, then `.bnick MyBot` |

## IRC operator (OPER) credentials

ibot's core has **no** oper support. There is no `[core]` key for `OPER`, and the bot never sends it by itself.

- The owner can oper up manually: `.raw OPER name YOUR_OPER_PASSWORD`.

  > **Warning:** The command and the password then appear in the channel or query where you typed them, and your incoming message is written verbatim to the bot's debug and raw logs. Only the outgoing `OPER` line is redacted. Only do this in a private message to the bot, and preferably not at all.

- Plugins that need oper privileges keep their own credentials in their own section. For example, a plugin might read `[myplugin] oper_name` / `oper_password` and call `bot.write(('OPER', name, password))` in an event handler for `001`. That's plugin behaviour, not ibot's. Check the plugin's documentation (for example the [sopel-scripts](https://github.com/lord3nd3r/sopel-scripts) docs).

## Account-based permissions

When the network sends account information (`account-tag` / `extended-join`), you can tie permissions to accounts instead of nicks:

```ini
[core]
owner = YourNick
owner_account = YourAccount
admin_accounts = FriendAccount
```

See [Permissions](../administration/permissions.md) for the exact rules and fallbacks.

## See also

- [Core reference: authentication keys](core-reference.md#authentication)
- [Connection lifecycle](../architecture/connection-lifecycle.md)
- [Security](../security.md)
- [Troubleshooting](../troubleshooting.md)

---
[← Back to docs home](../index.md)
