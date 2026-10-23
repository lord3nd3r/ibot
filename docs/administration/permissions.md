[Docs home](../index.md) › Administration › Permissions

# Permissions

ibot has three permission levels: **owner**, **admin**, and everyone else. This page explains how ibot decides which level a user has, how plugins use the levels, and how to configure them safely.

## In this article

- [Prerequisites](#prerequisites)
- [Permission levels](#permission-levels)
- [How the owner is identified](#how-the-owner-is-identified)
- [How admins are identified](#how-admins-are-identified)
- [Where account names come from](#where-account-names-come-from)
- [Channel privileges](#channel-privileges)
- [Permission-related exemptions](#permission-related-exemptions)
- [Recommended configurations](#recommended-configurations)
- [Checking your own status](#checking-your-own-status)
- [See also](#see-also)

## Prerequisites

- Access to the bot's config file (see [Core reference](../configuration/core-reference.md)).
- To use account-based identity, a network with services accounts and IRCv3 `account-tag` or `extended-join`.

## Permission levels

| Level | Who | Typical use | Decorator |
|---|---|---|---|
| Owner | `owner` / `owner_account`, plus anyone listed in `extra_owners` | Plugin lifecycle, `.raw`, `.bnick`, `.bquit` | `@plugin.require_owner` |
| Admin | The owner, plus `admins` / `admin_accounts` | Channel management, messaging, per-channel plugin control | `@plugin.require_admin` |
| User | Everyone else | Normal plugin commands | (none) |

The owner is **always** an admin, too. Admin commands are listed with their levels in [Admin commands](admin-commands.md#command-summary).

## How the owner is identified

The check runs for every message the bot considers dispatching (`Trigger.owner`):

```text
if owner_account is set AND the sender's account is known:
    owner  ⇔  account == owner_account          (exact, case-sensitive)
elif owner is set:
    owner  ⇔  nick.lower() == owner.lower()
else:
    nobody is owner

if not owner yet and extra_owners is set:
    owner  ⇔  account.lower() in extra_owners      (when the account is known)
           OR nick.lower() in extra_owners         (always checked)
```

| `owner` | `owner_account` | Sender's account | Result |
|---|---|---|---|
| `Alice` | (empty) | any | Owner if the nick is `alice` in any case |
| `Alice` | `alice_acct` | `alice_acct` | Owner |
| `Alice` | `alice_acct` | `someone_else` | **Not** owner, even when the nick is `Alice` |
| `Alice` | `alice_acct` | unknown (not logged in, or the network sends no account info) | Falls back to nick: owner if the nick is `Alice` |
| (empty) | `alice_acct` | unknown | Not owner |

`extra_owners` entries are lowercased and compared with both the account and the nick, so an entry works whether it names an account or a nick.

> **Warning:** If the sender's account is unknown, ibot **falls back to the nick**, even when `owner_account` is set. So `owner_account` only protects you when the network gives ibot account information. To prevent the fallback entirely, leave `owner` empty and set only `owner_account`, though the bot then can't recognise you while you're logged out.

> **Warning:** `extra_owners` matches the **nick** even when the sender's account is known and different. An entry that names an account is therefore also accepted as a nick: anyone who can use a nick spelled like that account gets owner rights. Only list names that are registered *and* protected as nicks too. See [Security](../security.md#owner-and-admin-identity).

> **Note:** Nicks are compared with Python's `str.lower()`, not IRC casemapping. `[`/`{` and `\`/`|` count as different characters here, unlike in IRC.

## How admins are identified

```text
admin  ⇔  owner
       OR (account is known AND account in admin_accounts)   (exact, case-sensitive)
       OR nick.lower() in [a.lower() for a in admins]
```

Unlike the owner check, the nick list is **always** consulted, even when the sender's account is known and isn't in `admin_accounts`.

> **Warning:** Every nick in `admins` is trusted by nick alone. On a network where anyone can take an unregistered or temporarily free nick, they get admin rights. Prefer `admin_accounts`, and keep `admins` empty, or limited to nicks that are registered and protected by services (for example NickServ `ENFORCE`/`KILL`).

## Where account names come from

For each message, ibot finds the sender's account in this order:

1. The `account` message tag (IRCv3 `account-tag`).
2. ibot's tracked user state, filled in from:
   - `extended-join`: the account field in `JOIN` lines for users who join a channel the bot is in.
   - `ACCOUNT` messages, if the server sends them.

ibot sends `CAP LS 302` and then requests only those of `account-tag`, `extended-join`, `multi-prefix` and `server-time` (plus `sasl` when configured) that the server offers. If the server rejects a multi-capability request with `CAP NAK`, ibot retries each capability on its own, once per connection. See [Authentication](../configuration/authentication.md#capability-negotiation-details).

> **Note:** ibot doesn't request `account-notify` and doesn't send `WHO`/`WHOX`. A user who was already in a channel when the bot joined has no tracked account. A user who logs out after joining keeps their old tracked account until they leave. When the `account-tag` capability is active, the tag on each message takes priority, so this only matters as a fallback.

> **Note:** On networks that offer neither `account-tag` nor `extended-join`, such as many older IRCds, every permission check is **nick-only**. The startup log line `Server capabilities: …` and the following `CAP ACK` line show which capabilities you got.

## Channel privileges

`@plugin.require_privilege(level)` checks the user's channel mode (voice, halfop, op, …) in the channel where the command was used:

| Situation | Result |
|---|---|
| In a channel, the user's privilege ≥ `level` | Allowed |
| In a channel, the user is a bot admin or the owner | Allowed (admins bypass this check) |
| In a private message | **Denied**, because there's no channel to check |

The bot's own channel privilege is checked by `@plugin.require_bot_privilege(level)`. In a private message the check is skipped and the command runs.

## Permission-related exemptions

| Mechanism | Who is exempt |
|---|---|
| Per-channel `.disable` and `[#channel] disable_plugins` | **Nobody**. A disabled plugin doesn't respond to the owner either. Only the `admin` plugin can never be disabled. |
| Rate limits (`@plugin.rate*`) | Admins and the owner, unless the plugin passes `include_admins=True` |
| `nick_blocks` / `host_blocks` | **Nobody** is exempt by permission. A blocked owner is ignored too, except by `@plugin.unblockable` handlers. |

## Recommended configurations

**Network with services and IRCv3 (e.g. Libera.Chat):**

```ini
[core]
owner = YourNick
owner_account = YourAccount
admins =
admin_accounts = TrustedAccount1, TrustedAccount2
```

**Network without IRCv3 account support:**

```ini
[core]
owner = YourRegisteredNick
admins = RegisteredNick1
```

Register every one of these nicks with NickServ and turn on nick protection, so that nobody else can use them while you're offline.

> **Note:** After editing these keys, run `.rehash`. Permissions are read from the current config for each message.

## Checking your own status

- `.bstatus` replies only to admins, and `.plugins` only to the owner. Both are silent for anyone else, so they're quick tests.
- If the bot ignores you, see [The bot ignores my admin commands](../troubleshooting.md#the-bot-ignores-my-admin-commands).

## See also

- [Admin commands](admin-commands.md)
- [Authentication](../configuration/authentication.md)
- [Security: owner and admin identity](../security.md#owner-and-admin-identity)
- [Core reference: owner](../configuration/core-reference.md#owner)

---
[← Back to docs home](../index.md)
