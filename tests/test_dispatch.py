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
from ibot.sopel_shim.plugin import (
    NOLIMIT, allow_bots, command, echo, priority, rate_user, rule_lazy,
    thread, unblockable,
)
from ibot.sopel_shim.tools import SopelIdentifierMemory
from ibot.bot import User


class FakeBot:
    """Minimal bot core good enough to drive the dispatcher."""

    def __init__(self, nick='testbot'):
        self.nick = nick
        self.memory = {'disabled_plugins': {}}
        self.sent = []
        self.users = SopelIdentifierMemory()

    def send_privmsg(self, target, text):
        self.sent.append((target, text))

    def send_privmsg_chunk(self, target, text):
        self.sent.append((target, text))

    def send_notice(self, text, target):
        self.sent.append((target, text))

    def send_raw(self, line):
        pass

    def get_privilege(self, channel, nick):
        return 0

    def get_user_account(self, nick):
        user = self.users.get(nick)
        return user.account if user else None

    def _track_account(self, nick, account):
        if nick not in self.users:
            self.users[nick] = User(nick)
        self.users[nick].account = account


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


def test_priority_orders_handlers(temp_config_file):
    """High-priority handlers are registered (and run) before low."""
    order = []

    @thread(False)
    @priority('low')
    @command('p')
    def low_h(bot, trigger):
        order.append('low')

    @thread(False)
    @priority('high')
    @command('p')
    def high_h(bot, trigger):
        order.append('high')

    @thread(False)
    @priority('medium')
    @command('p')
    def med_h(bot, trigger):
        order.append('medium')

    plugin = PluginInfo('priplugin', None)
    # Register low first so sort order, not registration order, wins.
    plugin.commands.extend([low_h, high_h, med_h])

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])
    disp.dispatch(':bob!u@h PRIVMSG #chan :.p')
    assert order == ['high', 'medium', 'low']


def test_nick_blocks_ignore_sender(temp_config_file):
    calls = []

    @thread(False)
    @command('hi')
    def handler(bot, trigger):
        calls.append(1)

    plugin = PluginInfo('ignplugin', None)
    plugin.commands.append(handler)

    disp, settings = _make_dispatcher(temp_config_file)
    # Inject ignore list as if loaded from config
    from ibot.sopel_shim.tools import Identifier
    disp._ignore_nicks = {Identifier('spammer').lower()}
    disp.register_plugins([plugin])

    disp.dispatch(':spammer!u@h PRIVMSG #chan :.hi')
    assert calls == []
    disp.dispatch(':bob!u@h PRIVMSG #chan :.hi')
    assert calls == [1]


def test_unblockable_bypasses_ignore(temp_config_file):
    calls = []

    @thread(False)
    @unblockable
    @command('hi')
    def handler(bot, trigger):
        calls.append(1)

    plugin = PluginInfo('ubplugin', None)
    plugin.commands.append(handler)

    disp, _ = _make_dispatcher(temp_config_file)
    from ibot.sopel_shim.tools import Identifier
    disp._ignore_nicks = {Identifier('spammer').lower()}
    disp.register_plugins([plugin])

    disp.dispatch(':spammer!u@h PRIVMSG #chan :.hi')
    assert calls == [1]


def test_allow_bots_filter(temp_config_file):
    calls = []

    @thread(False)
    @command('hi')
    def normal(bot, trigger):
        calls.append('normal')

    @thread(False)
    @allow_bots
    @command('hi')
    def with_bots(bot, trigger):
        calls.append('bots')

    plugin = PluginInfo('botplugin', None)
    plugin.commands.extend([normal, with_bots])

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])
    # Message tagged as bot
    disp.dispatch('@bot=;account=otherbot :otherbot!u@h PRIVMSG #chan :.hi')
    assert calls == ['bots']


def test_echo_filter_skips_own_nick(temp_config_file):
    calls = []

    @thread(False)
    @command('hi')
    def normal(bot, trigger):
        calls.append('normal')

    @thread(False)
    @echo
    @command('hi')
    def with_echo(bot, trigger):
        calls.append('echo')

    plugin = PluginInfo('echoplugin', None)
    plugin.commands.extend([normal, with_echo])

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])
    # Message from the bot itself
    disp.dispatch(':testbot!u@h PRIVMSG #chan :.hi')
    assert calls == ['echo']


def test_account_tag_sets_trigger_account(temp_config_file):
    seen = []

    @thread(False)
    @command('who')
    def handler(bot, trigger):
        seen.append(trigger.account)

    plugin = PluginInfo('acctplugin', None)
    plugin.commands.append(handler)

    disp, _ = _make_dispatcher(temp_config_file)
    disp.register_plugins([plugin])
    disp.dispatch('@account=alice_acct :bob!u@h PRIVMSG #chan :.who')
    assert seen == ['alice_acct']


def test_tag_value_unescaping():
    from ibot.sopel_shim.trigger import unescape_tag_value, PreTrigger
    assert unescape_tag_value(r'a\sb\sc') == 'a b c'
    assert unescape_tag_value(r'x\:y') == 'x;y'
    pre = PreTrigger('bot', r'@account=foo\sbar :n!u@h PRIVMSG #c :hi')
    assert pre.tags['account'] == 'foo bar'
