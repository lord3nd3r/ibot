[Docs home](index.md) › Glossary

# Glossary

Definitions of the IRC, IRCv3, Sopel and ibot terms used throughout this documentation.

## In this article

- [Prerequisites](#prerequisites)
- [IRC and IRCv3 terms](#irc-and-ircv3-terms)
- [ibot and Sopel terms](#ibot-and-sopel-terms)
- [See also](#see-also)

## Prerequisites

None.

## IRC and IRCv3 terms

| Term | Definition |
|---|---|
| **Account** | The services (NickServ) account a user is logged in to. It can differ from the user's nick. ibot uses it for [owner and admin checks](administration/permissions.md). |
| **`account-tag`** | An IRCv3 capability that attaches `account=<name>` to every message from a logged-in user. Requested by ibot. |
| **CAP** | IRCv3 capability negotiation. ibot sends `CAP LS 302`, then `CAP REQ` for whichever of `account-tag`, `extended-join`, `multi-prefix`, `server-time` (and `sasl`, when SASL is configured) the server offers. |
| **Casemapping** | The rules a network uses to compare nicks and channels case-insensitively. In `rfc1459`, `[]\~` are the upper-case forms of `{}|^`. `Identifier` uses this mapping. |
| **CTCP** | Client-To-Client Protocol: `\x01`-delimited messages inside `PRIVMSG`/`NOTICE`, such as `ACTION` (`/me`) and `VERSION`. |
| **`extended-join`** | An IRCv3 capability that adds the account and realname to `JOIN` messages. |
| **Hostmask** | `nick!user@host`, the full identity of a message sender. Matched by `host_blocks`. |
| **ISUPPORT (`005`)** | A server numeric that advertises network limits and features. |
| **Message tags** | IRCv3 `@key=value;…` metadata before a message. Available as `trigger.tags`. |
| **NickServ** | The services bot that registers nicks and accounts. ibot can identify to it with `auth_method = nickserv`. |
| **Numeric** | A three-digit server reply, such as `001` (welcome), `433` (nick in use), or `477` (registration needed to join). |
| **PM / query** | A private message: a `PRIVMSG` whose target is the bot's nick. |
| **Privilege / prefix mode** | A channel status: voice `+`, halfop `%`, op `@`, admin `&`, owner `~`. Exposed as `bot.channels[#c].privileges`. |
| **SASL** | Authenticating to services during connection registration. ibot supports the `PLAIN` mechanism. |
| **Token bucket** | The flood-control algorithm: each line costs a token, and tokens refill over time. See [Flood control](architecture/flood-control.md). |

An incoming message showing several of these terms:

```text
@account=alice;time=2026-10-22T19:03:11.000Z :alice!~al@host.example.net PRIVMSG #chan :.seen bob
└──────── message tags ────────┘ └──────── hostmask ──────────┘ └command┘ └target┘ └─ text ─┘
```

> **Note:** ibot compares nicks in two different ways. `Identifier` (used for `bot.users` and `nick_blocks`) uses RFC 1459 casemapping. Owner and admin nick checks use plain `str.lower()`. See [Permissions](administration/permissions.md).

## ibot and Sopel terms

| Term | Definition |
|---|---|
| **Admin** | A user in `admins` or `admin_accounts`, or the owner. Can run admin-level commands. |
| **Callable / handler** | A plugin function decorated with `@plugin.command`, `@plugin.rule` and so on, and called by the dispatcher. |
| **Core bot** | ibot's `Bot` object (`ibot.bot`). It owns the connection, state, database and dispatcher. Plugins see it through the wrapper. |
| **Dispatcher** | The component that matches incoming lines against handlers, applies filters, and runs them. See [Dispatch](architecture/dispatch.md). |
| **Handler pool** | The bounded set of worker threads (`[core] handler_threads`, default 64) that runs threaded handlers. See [Dispatch: Threading model](architecture/dispatch.md#threading-model). |
| **Interval job** | A function decorated with `@plugin.interval(seconds)` that runs periodically. |
| **Lazy loader** | A function passed to `@plugin.rule_lazy` and similar, which returns patterns when the plugin is registered. |
| **Owner** | The most-trusted user, set by `owner_account` or `owner`. Additional owners can be listed in `extra_owners`. |
| **Persistent channel** | A channel added with `.bjoin`, stored in the database and rejoined at every connect. |
| **Plugin** | A `.py` file directly in a plugin directory whose name doesn't start with `_`. It's loaded even when it has no decorated callables. See [What counts as a plugin](administration/plugin-management.md#what-counts-as-a-plugin). |
| **Predicate** | A restriction check attached by decorators such as `require_admin` and `require_chanmsg`. |
| **Prefix** | The regular expression that starts a command, `\.` by default. |
| **Rehash** | `.rehash`: re-read the config and reload all plugins without reconnecting. A plugin that fails to import keeps its previous version. |
| **Shim** | ibot's `sopel` compatibility package, inserted into `sys.modules`. |
| **sopel-scripts** | The official ibot plugin collection ([lord3nd3r/sopel-scripts](https://github.com/lord3nd3r/sopel-scripts)), loaded through `[core] extra`. |
| **`SopelWrapper` (`bot`)** | The object passed to handlers as `bot`. It knows the current trigger, so `say()` defaults to the right destination. |
| **Trigger** | The object passed to handlers that describes the incoming message: nick, sender, match groups, tags, account, and admin/owner flags. See [Plugin API reference](developer-guide/plugin-api-reference.md#trigger). |

## See also

- [FAQ](faq.md)
- [Plugin API reference](developer-guide/plugin-api-reference.md)

---
[← Back to docs home](index.md)
