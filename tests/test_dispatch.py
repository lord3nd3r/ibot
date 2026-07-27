"""Tests for ibot.dispatch: lazy-loader wiring and NOLIMIT handling."""

import re

import pytest

from ibot.loader import install_sopel_shim

# The shim must be installed before importing anything that does
# `from sopel import ...` and before building plugins/dispatcher.
install_sopel_shim()

from ibot.config import load_config
from ibot.dispatch import Dispatcher
from ibot.loader import PluginInfo, load_plugins
from ibot.sopel_shim.plugin import NOLIMIT, command, rate_user, rule_lazy, thread


class FakeBot:
    """Minimal bot core good enough to drive the dispatcher."""

    def __init__(self, nick='testbot'):
        self.nick = nick
        self.memory = {'disabled_plugins': {}}
        self.sent = []

    def send_privmsg(self, target, text):
        self.sent.append((target, text))

    def send_notice(self, text, target):
        self.sent.append((target, text))

    def send_raw(self, line):
        pass

    def get_privilege(self, channel, nick):
        return 0


def _make_dispatcher(temp_config_file):
    settings = load_config(temp_config_file)
    return Dispatcher(FakeBot(), settings), settings


def test_rule_lazy_loader_is_registered(temp_config_file):
    """A function decorated only with @rule_lazy should produce a rule handler."""
    def loader(settings):
        return [re.compile(r'lazyhi')]

    @rule_lazy(loader)
    def handler(bot, trigger):
        pass

    plugin = PluginInfo('lazyplugin', None)
    plugin.rules.append(handler)

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])

    assert len(disp._rule_handlers) == 1
    compiled = disp._rule_handlers[0][0]
    assert compiled.search('well lazyhi there')


def test_rule_lazy_loader_end_to_end(temp_config_file, temp_plugin_dir):
    """@rule_lazy loaded from disk gets collected and dispatched."""
    (temp_plugin_dir / 'lz.py').write_text(
        "import re\n"
        "from sopel import plugin\n"
        "def _load(settings):\n"
        "    return [re.compile(r'ping-lazy')]\n"
        "@plugin.thread(False)\n"
        "@plugin.rule_lazy(_load)\n"
        "def handler(bot, trigger):\n"
        "    bot.say('pong-lazy')\n"
    )

    plugins = load_plugins([str(temp_plugin_dir)])
    assert len(plugins) == 1
    assert len(plugins[0].rules) == 1  # collected despite no static _rules

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins(plugins)
    assert len(disp._rule_handlers) == 1

    disp.dispatch(':bob!u@h PRIVMSG #chan :ping-lazy please')
    assert disp.bot.sent == [('#chan', 'pong-lazy')]


def test_nolimit_return_skips_rate_accounting(temp_config_file):
    """Returning NOLIMIT means the call is not recorded against the rate limit."""
    calls = []

    @thread(False)  # run inline so the test is deterministic
    @rate_user(9999)
    @command('nolim')
    def handler(bot, trigger):
        calls.append(1)
        return NOLIMIT

    plugin = PluginInfo('nolimplugin', None)
    plugin.commands.append(handler)

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])

    line = ':bob!u@h PRIVMSG #chan :.nolim'
    disp.dispatch(line)
    disp.dispatch(line)

    # Both invocations ran because NOLIMIT prevented rate-limit recording.
    assert len(calls) == 2


def test_rate_limit_blocks_without_nolimit(temp_config_file):
    """Without NOLIMIT, a heavy per-user rate limit blocks the second call."""
    calls = []

    @thread(False)
    @rate_user(9999)
    @command('limited')
    def handler(bot, trigger):
        calls.append(1)
        # returns None -> counts against the rate limit

    plugin = PluginInfo('limplugin', None)
    plugin.commands.append(handler)

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])

    line = ':bob!u@h PRIVMSG #chan :.limited'
    disp.dispatch(line)
    disp.dispatch(line)

    assert len(calls) == 1
