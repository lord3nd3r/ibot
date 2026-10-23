[Docs home](index.md) › Changelog

# Changelog

This page is the history of ibot, compiled from the Git log of `main`. Entries are grouped by date, newest first, and each entry links its commit's short hash. Dates are commit author dates.

## In this article

- [Prerequisites](#prerequisites)
- [How to read this page](#how-to-read-this-page)
- [Unreleased](#unreleased)
- [1.0.0 (2026-07-26)](#100-2026-07-26)
- [Pre-1.0 (2026-05-07 to 2026-05-13)](#pre-10-2026-05-07-to-2026-05-13)
- [Generating this list yourself](#generating-this-list-yourself)
- [See also](#see-also)

## Prerequisites

None.

## How to read this page

| Label | Meaning |
|---|---|
| **Added** | New feature |
| **Changed** | A change in existing behaviour |
| **Fixed** | Bug fix |
| **Removed** | A file or feature was removed |
| **Docs** | Documentation only |

> **Note:** The repository has no Git tags. Version numbers come from the "Bump version" commit.

## Unreleased

Commits on `main` after the 1.0.0 version bump. The version number is still `1.0.0`.

### 2026-10-23

Commit [`565ddbd`](https://github.com/lord3nd3r/ibot/commit/565ddbd), "Core hardening: safe sends, reconnect, CAP LS, GHOST regain, Sopel compat; tests" (committed 2026-10-22 22:43 CDT). A bot process started before this commit keeps running the older code until it's restarted.

**Connection and protocol**

- **Changed:** Capability negotiation uses `CAP LS 302` and requests only the caps the server offers. A `CAP NAK` for several caps is retried one cap at a time. See [Registration and CAP](architecture/connection-lifecycle.md#registration-and-cap).
- **Added:** Nick fallback (`nick_`, `nick__`, then a random number), sanitising of erroneous nicks (`432`), a cap of 20 attempts, and NickServ `GHOST` regain when a password is configured. See [Nick collisions](architecture/connection-lifecycle.md#nick-collisions).
- **Added:** Keepalive: a `PING` after 240 s of silence, and a reconnect if nothing arrives within 60 s. See [Keepalive](architecture/connection-lifecycle.md#keepalive).
- **Fixed:** The reconnect delay now resets to 5 s after a successful registration.
- **Changed:** `471`/`477` join failures are retried with back-off (10 s up to 300 s, at most 8 times per channel).
- **Added:** New `[core]` keys, `handler_threads`, `handler_queue_size`, `log_raw`, `logdir`, `bind_host`, `user`, `name` and `extra_owners`. See [Core reference](configuration/core-reference.md).

**Safety**

- **Added:** Every outgoing line has CR, LF and NUL replaced and is cut to 510 bytes on a character boundary. See [Flood control: line safety](architecture/flood-control.md#line-safety).
- **Added:** Credentials are redacted from debug and raw logs (`AUTHENTICATE`, `PASS`, `OPER`, NickServ commands). Optional raw traffic log, written with mode `0600`. See [Security: logging and privacy](security.md#logging-and-privacy).
- **Added:** `sopel.tools.web.get()` blocks private and internal addresses, re-checks redirects, and caps bodies at 5 MiB. See [Tools reference](developer-guide/tools-reference.md#sopeltoolsweb).
- **Changed:** `auto_accept_invite` accepts invites only from admins and the owner.
- **Changed:** `--generate-config` creates the file with mode `0600`. Config values are read literally (no `%` interpolation).
- **Changed:** `.gitignore` also covers `*.cfg.*`, `*.orig`, `*~`, `*.log`, `logs/` and SQLite side files.

**Plugins and dispatch**

- **Added:** Threaded handlers run on a bounded pool instead of one thread each. See [Dispatch: Threading model](architecture/dispatch.md#threading-model).
- **Changed:** `.reload` and `.rehash` import the new code first and keep the previous version if the import or `setup()` fails. `setup()` and `shutdown()` are called exactly once. Interval jobs restart on reload. See [Hot reloading](administration/plugin-management.md#hot-reloading).
- **Changed:** `.rehash` now applies ignore lists and `[#channel] disable_plugins`.
- **Added:** Sopel compatibility: case-insensitive rules, `$nickname`/`$nick` substitution, `bot.restart()`, `bot.reload_plugin()`, and forwarding of unknown public attributes to the core bot. See [Sopel compatibility](developer-guide/sopel-compatibility.md).
- **Changed:** SQLite uses WAL mode and a 10 s busy timeout. See [Database](architecture/database.md).
- **Removed:** The bundled `ibot/plugins/example.py` plugin.
- **Added:** `tests/test_hardening.py`. See [Testing](developer-guide/testing.md#current-test-status).

### 2026-08-30

- **Fixed:** Duplicate plugin loading and a command dispatch loop ([`f6d8fa2`](https://github.com/lord3nd3r/ibot/commit/f6d8fa2)).
- **Changed:** Dispatch returns after the first matching command, so a command line no longer falls through to `@rule` handlers ([`b315657`](https://github.com/lord3nd3r/ibot/commit/b315657)).

  > **Warning:** This change makes three existing tests fail (`test_priority_orders_handlers`, `test_allow_bots_filter`, `test_echo_filter_skips_own_nick`). It also means that only the first matching command handler is considered, even when that handler is filtered out. See [Dispatch: known limitations](architecture/dispatch.md#known-limitations) and [Testing](developer-guide/testing.md#current-test-status).

## 1.0.0 (2026-07-26)

- **Fixed:** Database default handling, message splitting, and Sopel compatibility gaps ([`c5d3676`](https://github.com/lord3nd3r/ibot/commit/c5d3676), merged in PR #1).
- **Added:** The remaining Sopel compatibility gaps were addressed ([`3b4dbb1`](https://github.com/lord3nd3r/ibot/commit/3b4dbb1), merged in PR #2) and wired end-to-end ([`07a78c3`](https://github.com/lord3nd3r/ibot/commit/07a78c3)). See [Sopel compatibility](developer-guide/sopel-compatibility.md).
- **Docs:** The README was rewritten with full install, config and compatibility docs ([`37aa725`](https://github.com/lord3nd3r/ibot/commit/37aa725)).
- **Changed:** The version was bumped to 1.0.0 ([`72528bd`](https://github.com/lord3nd3r/ibot/commit/72528bd)).
- **Docs:** 1.0 is documented as "stable-ish / somewhat beta" ([`e9ee0f0`](https://github.com/lord3nd3r/ibot/commit/e9ee0f0)).

## Pre-1.0 (2026-05-07 to 2026-05-13)

### 2026-05-13

- **Fixed:** The bot joined `+R` channels too fast on startup. It now waits for NickServ identification before joining ([`0623f51`](https://github.com/lord3nd3r/ibot/commit/0623f51)).

### 2026-05-10

- **Fixed:** `register_plugins` extends the plugin list instead of replacing it ([`65cbb09`](https://github.com/lord3nd3r/ibot/commit/65cbb09)).

### 2026-05-09

- **Added:** `hold_ground` and `auto_accept_invite` in the admin plugin ([`ed2c027`](https://github.com/lord3nd3r/ibot/commit/ed2c027)). See [Admin commands: automatic behaviour](administration/admin-commands.md#automatic-behaviour).
- **Removed:** `default.cfg` ([`5ef25de`](https://github.com/lord3nd3r/ibot/commit/5ef25de)). Use `--generate-config` instead.
- **Docs:** The Quick Start uses `--generate-config` ([`95e4249`](https://github.com/lord3nd3r/ibot/commit/95e4249)).

### 2026-05-08

- **Changed:** The IRC host changed from libera.chat to rizon.net ([`6465c20`](https://github.com/lord3nd3r/ibot/commit/6465c20)).
- **Removed:** `PLAN.md`, since the implementation was complete ([`25ecb89`](https://github.com/lord3nd3r/ibot/commit/25ecb89)).
- **Docs:** The README used `default.cfg` as its starting point ([`31dcb1a`](https://github.com/lord3nd3r/ibot/commit/31dcb1a)). This was superseded on 2026-05-09.
- **Fixed:** `Channel.users` is a dict, matching Sopel's API ([`5706308`](https://github.com/lord3nd3r/ibot/commit/5706308)).
- **Added:** Per-channel disable/enable, PM-only and persisted in the database ([`f3c0cca`](https://github.com/lord3nd3r/ibot/commit/f3c0cca)).
- **Changed:** Disable/enable work on plugin names instead of commands ([`afaec25`](https://github.com/lord3nd3r/ibot/commit/afaec25)).
- **Fixed:** Shutdown on signals (Ctrl+C) ([`93bcaf0`](https://github.com/lord3nd3r/ibot/commit/93bcaf0)).
- **Fixed:** `RuntimeError: dictionary changed size during iteration` in `SopelMemory` ([`d2fa617`](https://github.com/lord3nd3r/ibot/commit/d2fa617)).
- **Added:** Dynamic channel joins (`.bjoin`) persist in the database ([`9c9905b`](https://github.com/lord3nd3r/ibot/commit/9c9905b)).
- **Changed:** "Major improvements: security, performance, and project structure" ([`d0eea52`](https://github.com/lord3nd3r/ibot/commit/d0eea52)).
- **Changed:** Type hints, tests, and code organisation ([`d437f88`](https://github.com/lord3nd3r/ibot/commit/d437f88)).
- **Fixed:** CTCP handlers respect `@rule` patterns ([`94357b7`](https://github.com/lord3nd3r/ibot/commit/94357b7)).
- **Fixed:** Persistent channel handling and logging ([`c853b36`](https://github.com/lord3nd3r/ibot/commit/c853b36)), with extra debug logging for channel joins ([`ea3db5b`](https://github.com/lord3nd3r/ibot/commit/ea3db5b)).

### 2026-05-07

- **Added:** Initial commit: a Sopel-compatible IRC bot framework ([`71f6dc5`](https://github.com/lord3nd3r/ibot/commit/71f6dc5)).

## Generating this list yourself

```bash
git -C ~/ibot log --date=short --pretty='%h %ad %s'
git -C ~/ibot log --date=short --pretty='%h %ad %s' 565ddbd..   # commits after this page
```

## See also

- [Contributing](../CONTRIBUTING.md)
- [Sopel compatibility](developer-guide/sopel-compatibility.md)

---
[← Back to docs home](index.md)
