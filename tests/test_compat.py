"""Tests for the remaining Sopel-compatibility features:

- sopel.tools.target (User / Channel)
- unbounded TEXT value columns in the DB
- @plugin.require_bot_privilege
"""

import pytest

from ibot.loader import install_sopel_shim

install_sopel_shim()

from sqlalchemy import Text

from ibot.config import load_config
from ibot.dispatch import Dispatcher
from ibot.loader import PluginInfo
from ibot.sopel_shim.db import ChannelValues, NickValues, PluginValues, SopelDB
from ibot.sopel_shim.plugin import command, require_bot_privilege, thread
from ibot.sopel_shim.privileges import OP, VOICE


# --- sopel.tools.target ---

def test_tools_target_exports_live_classes():
    """sopel.tools.target.User/Channel are the same classes the bot tracks."""
    from sopel.tools.target import User, Channel
    from sopel.tools import target
    from ibot.bot import User as CoreUser, Channel as CoreChannel

    assert User is CoreUser
    assert Channel is CoreChannel
    assert target.User is CoreUser


def test_channel_privilege_helpers():
    """Channel exposes Sopel-style is_op/is_voiced/... bitmask checks."""
    from sopel.tools.target import Channel

    chan = Channel('#room')
    chan.add_user('opper', privilege=OP)

    assert chan.is_op('opper') is True
    assert chan.is_voiced('opper') is False   # only the OP bit is set
    assert chan.has_privilege('opper', VOICE)  # >= semantics: OP outranks voice
    assert chan.is_op('nobody') is False


# --- DB value columns are unbounded TEXT ---

@pytest.mark.parametrize('model', [NickValues, ChannelValues, PluginValues])
def test_value_columns_are_text(model):
    assert isinstance(model.__table__.c.value.type, Text)


def test_large_value_roundtrip(tmp_path):
    """A value well past 255 chars roundtrips intact."""
    db = SopelDB(db_filename=str(tmp_path / 't.db'))
    try:
        channels = ['#channel-%03d' % i for i in range(200)]
        db.set_plugin_value('admin', 'persistent_channels', channels)
        assert db.get_plugin_value('admin', 'persistent_channels') == channels
    finally:
        db.close()


# --- require_bot_privilege ---

class _FakeBot:
    def __init__(self, bot_priv=0, nick='testbot'):
        self.nick = nick
        self.memory = {'disabled_plugins': {}}
        self.sent = []
        self._bot_priv = bot_priv

    def send_privmsg(self, target, text):
        self.sent.append((target, text))

    def send_notice(self, text, target):
        self.sent.append((target, text))

    def send_raw(self, line):
        pass

    def get_privilege(self, channel, nick):
        # Only the bot's own nick has the configured privilege.
        return self._bot_priv if str(nick).lower() == self.nick.lower() else 0


def _dispatch_cmd(temp_config_file, bot_priv, line):
    calls = []

    @thread(False)
    @require_bot_privilege(OP, 'I need op for that.')
    @command('opcmd')
    def handler(bot, trigger):
        calls.append(1)

    plugin = PluginInfo('opplugin', None)
    plugin.commands.append(handler)

    settings = load_config(temp_config_file)
    disp = Dispatcher(_FakeBot(bot_priv=bot_priv), settings)
    disp.register_plugins([plugin])
    disp.dispatch(line)
    return calls, disp.bot.sent


def test_require_bot_privilege_blocks_without_privilege(temp_config_file):
    calls, sent = _dispatch_cmd(
        temp_config_file, bot_priv=0,
        line=':bob!u@h PRIVMSG #chan :.opcmd')
    assert calls == []
    assert sent == [('#chan', 'I need op for that.')]


def test_require_bot_privilege_allows_with_privilege(temp_config_file):
    calls, sent = _dispatch_cmd(
        temp_config_file, bot_priv=OP,
        line=':bob!u@h PRIVMSG #chan :.opcmd')
    assert calls == [1]
    assert sent == []


def test_require_bot_privilege_skipped_in_pm(temp_config_file):
    # In a PM the check does not apply, so the command runs even with no privs.
    calls, sent = _dispatch_cmd(
        temp_config_file, bot_priv=0,
        line=':bob!u@h PRIVMSG testbot :.opcmd')
    assert calls == [1]
