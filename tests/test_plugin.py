"""Tests for ibot.sopel_shim.plugin decorators."""

import pytest
from ibot.sopel_shim.plugin import (
    command, rule, event, interval, require_admin, require_owner,
    require_chanmsg, require_privmsg, rate_user, rate_channel,
    thread, priority, unblockable, output_prefix
)


def test_command_decorator():
    """Test command decorator."""
    @command('test')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_commands')
    assert 'test' in func._commands


def test_multiple_commands():
    """Test multiple command decorator."""
    @command('cmd1', 'cmd2', 'cmd3')
    def func(bot, trigger):
        pass
    
    assert len(func._commands) == 3
    assert 'cmd1' in func._commands
    assert 'cmd2' in func._commands
    assert 'cmd3' in func._commands


def test_rule_decorator():
    """Test rule decorator."""
    @rule(r'hello.*')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_rules')
    assert r'hello.*' in func._rules


def test_event_decorator():
    """Test event decorator."""
    @event('JOIN', 'PART')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_events')
    assert 'JOIN' in func._events
    assert 'PART' in func._events


def test_interval_decorator():
    """Test interval decorator."""
    @interval(60)
    def func(bot):
        pass
    
    assert hasattr(func, '_intervals')
    assert 60 in func._intervals


def test_require_admin_decorator():
    """Test require_admin decorator."""
    @require_admin
    @command('admin')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_predicates')
    assert len(func._predicates) > 0


def test_require_owner_decorator():
    """Test require_owner decorator."""
    @require_owner('Only owner')
    @command('owner')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_predicates')
    assert len(func._predicates) > 0


def test_require_chanmsg_decorator():
    """Test require_chanmsg decorator."""
    @require_chanmsg
    @command('chanonly')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_predicates')


def test_require_privmsg_decorator():
    """Test require_privmsg decorator."""
    @require_privmsg
    @command('pmonly')
    def func(bot, trigger):
        pass
    
    assert hasattr(func, '_predicates')


def test_rate_decorators():
    """Test rate limiting decorators."""
    @rate_user(10)
    @rate_channel(30)
    @command('limited')
    def func(bot, trigger):
        pass
    
    assert func._rate_user == 10
    assert func._rate_channel == 30


def test_thread_decorator():
    """Test thread decorator."""
    @thread(False)
    @command('unthreaded')
    def func(bot, trigger):
        pass
    
    assert func._threaded is False


def test_priority_decorator():
    """Test priority decorator."""
    @priority('high')
    @command('urgent')
    def func(bot, trigger):
        pass
    
    assert func._priority == 'high'


def test_unblockable_decorator():
    """Test unblockable decorator."""
    @unblockable
    @command('always')
    def func(bot, trigger):
        pass
    
    assert func._unblockable is True


def test_output_prefix_decorator():
    """Test output_prefix decorator."""
    @output_prefix('[BOT] ')
    @command('prefixed')
    def func(bot, trigger):
        pass
    
    assert func._output_prefix == '[BOT] '


def test_stacked_decorators():
    """Test multiple decorators on one function."""
    @require_admin
    @rate_user(5)
    @output_prefix('[ADMIN] ')
    @command('complex')
    def func(bot, trigger):
        pass
    
    assert 'complex' in func._commands
    assert func._rate_user == 5
    assert func._output_prefix == '[ADMIN] '
    assert len(func._predicates) > 0
