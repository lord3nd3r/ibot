[Docs home](../index.md) › Developer guide › Testing

# Testing

This page explains how to run ibot's test suite, what it covers, how to unit-test your own plugins without an IRC server, and how to do a safe live test.

## In this article

- [Prerequisites](#prerequisites)
- [Running the test suite](#running-the-test-suite)
- [Test layout](#test-layout)
- [Current test status](#current-test-status)
- [Unit-testing a plugin](#unit-testing-a-plugin)
- [Testing against a live server](#testing-against-a-live-server)
- [Static checks](#static-checks)
- [See also](#see-also)

## Prerequisites

- Python 3.8 or later (the bot is run on 3.13)
- A clone of the repository

## Running the test suite

```bash
cd ~/ibot
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'        # sqlalchemy, pytest, pytest-asyncio, mypy
pytest                          # runs tests/ (configured in pyproject.toml)
pytest -q tests/test_dispatch.py -k rate   # a subset
```

`pyproject.toml` sets `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and the file patterns `test_*.py` and `*_test.py`.

> **Note:** `CONTRIBUTING.md` mentions `pytest --cov`. That needs `pytest-cov`, which isn't in the `dev` extras: `pip install pytest-cov`.

## Test layout

| File | Tests | Covers |
|---|---|---|
| `tests/conftest.py` | — | Fixtures: `temp_config_file` (a minimal `[core]` with `db_filename = :memory:`) and `temp_plugin_dir` |
| `tests/test_compat.py` | 14 | The Sopel shim: imports, decorators, trigger, wrapper |
| `tests/test_config.py` | 4 | Config loading and core keys |
| `tests/test_dispatch.py` | 11 | Dispatcher: lazy loaders, NOLIMIT, priority, ignore lists, `allow_bots`, `echo` |
| `tests/test_loader.py` | 10 | Plugin discovery, exclude/enable, reload |
| `tests/test_plugin.py` | 15 | Decorator metadata |
| `tests/test_tools.py` | 17 | `Identifier`, memory classes, web/time helpers |
| `tests/test_hardening.py` | 22 (27 collected) | Line cleaning and log redaction (one parametrized test with 6 cases), the handler pool, nick fallback, CAP negotiation, ISUPPORT parsing, `web.check_url`, threaded database nick IDs and merging, case-insensitive rules and `$nickname`, `[#channel] disable_plugins`, handler exceptions |

> **Note:** In the fixture, `db_filename = :memory:` is treated as a *file name* relative to the config directory, not as SQLite's in-memory database. A file literally named `:memory:` is created in the temporary directory.

## Current test status

On the source snapshot these docs describe (commit `565ddbd`, 22 October 2026), run with Python 3.13 and SQLAlchemy 2.0, pytest collects **98 tests: 95 pass and 3 fail**:

| Failing test | Why |
|---|---|
| `test_priority_orders_handlers` | It expects all three same-named commands to run. The dispatcher stops at the first match. |
| `test_allow_bots_filter` | The first command in sort order is filtered out (bot), and dispatch still stops, so the `allow_bots` handler never runs |
| `test_echo_filter_skips_own_nick` | The same mechanism, for `echo` |

All three come from the "first command wins" behaviour described in [Dispatch: known limitations](../architecture/dispatch.md#known-limitations).

## Unit-testing a plugin

The dispatcher can be driven with a fake core bot and raw IRC lines. This pattern is taken from `tests/test_dispatch.py`:

```python
# tests/test_myplugin.py
from ibot.loader import install_sopel_shim
install_sopel_shim()                    # must come before importing plugins

from ibot.config import load_config
from ibot.dispatch import Dispatcher
from ibot.loader import _load_plugin_file
from ibot.sopel_shim.tools import SopelIdentifierMemory


class FakeBot:
    def __init__(self, nick='testbot'):
        self.nick = nick
        self.memory = {'disabled_plugins': {}}
        self.users = SopelIdentifierMemory()
        self.sent = []
    def send_privmsg(self, target, text): self.sent.append((target, text))
    def send_privmsg_chunk(self, target, text): self.sent.append((target, text))
    def send_notice(self, text, target): self.sent.append((target, text))
    def send_raw(self, line): self.sent.append(('RAW', line))
    def get_privilege(self, channel, nick): return 0
    def get_user_account(self, nick): return None
    def _track_account(self, nick, account): pass


def test_hello(temp_config_file):
    settings = load_config(temp_config_file)
    bot = FakeBot()
    disp = Dispatcher(bot, settings)
    plugin = _load_plugin_file('hello', 'plugins/hello.py')
    disp.register_plugins([plugin])

    disp.dispatch(':alice!a@host PRIVMSG #chan :.hello')

    import time; time.sleep(0.1)         # handlers run in threads by default
    assert ('#chan', 'Hello, alice!') in bot.sent
```

Tips:

| Tip | Detail |
|---|---|
| Avoid sleeps | Decorate test-only handlers with `@plugin.thread(False)`, or poll `bot.sent` with a timeout |
| The prefix comes from the config | The fixture uses `prefix = \.`, so commands start with `.` |
| Tags | Prefix the line: `@account=alice :alice!a@h PRIVMSG #c :.cmd` |
| PMs | Target the bot's nick: `:alice!a@h PRIVMSG testbot :.cmd` |
| Admin/owner | Set `owner`/`admins` in a custom config file |

## Testing against a live server

1. Copy your config to `test.cfg`. Change `nick`, use a **test channel**, and use a separate `db_filename`.
2. Run `python3 -m ibot test.cfg -v` and watch the debug log.
3. Exercise the plugin. Use `.reload <name>` after each edit.

> **Warning:** Don't run a second instance with the production config. It would share the database file and the nick (causing `433` collisions), and could repeat actions in production channels.

## Static checks

```bash
python3 -m py_compile path/to/plugin.py   # syntax
mypy ibot                                 # types (configured in pyproject.toml)
```

## See also

- [Writing plugins](writing-plugins.md)
- [Contributing](../../CONTRIBUTING.md)
- [Troubleshooting](../troubleshooting.md)

---
[← Back to docs home](../index.md)
