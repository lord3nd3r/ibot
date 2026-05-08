"""Tests for ibot.loader module."""

import pytest
from pathlib import Path
from ibot.loader import load_plugins, _load_plugin_file, find_plugin_file, install_sopel_shim


# Install shim once at module level
install_sopel_shim()


def test_load_plugins_empty_dir(temp_plugin_dir):
    """Test loading plugins from empty directory."""
    plugins = load_plugins([str(temp_plugin_dir)])
    assert plugins == []


def test_load_plugins_with_example(temp_plugin_dir):
    """Test loading a simple plugin."""
    # Create a minimal plugin
    plugin_file = temp_plugin_dir / 'testplugin.py'
    plugin_file.write_text("""
from sopel import plugin

@plugin.command('test')
def test_command(bot, trigger):
    bot.say('Test!')
""")
    
    plugins = load_plugins([str(temp_plugin_dir)])
    assert len(plugins) == 1
    assert plugins[0].name == 'testplugin'
    assert len(plugins[0].commands) == 1


def test_load_plugins_skip_underscore(temp_plugin_dir):
    """Test that files starting with _ are skipped."""
    (temp_plugin_dir / '_private.py').write_text('# private module')
    (temp_plugin_dir / '__init__.py').write_text('# init file')
    
    plugins = load_plugins([str(temp_plugin_dir)])
    assert len(plugins) == 0


def test_load_plugins_with_exclude(temp_plugin_dir):
    """Test excluding plugins."""
    (temp_plugin_dir / 'plugin1.py').write_text('# plugin 1')
    (temp_plugin_dir / 'plugin2.py').write_text('# plugin 2')
    
    plugins = load_plugins(
        [str(temp_plugin_dir)],
        exclude=['plugin1']
    )
    # plugin2 loads but has no functions with decorators, so still valid PluginInfo
    assert len(plugins) == 1
    assert plugins[0].name == 'plugin2'


def test_load_plugins_with_enable(temp_plugin_dir):
    """Test enable filter."""
    (temp_plugin_dir / 'plugin1.py').write_text("""
from sopel import plugin

@plugin.command('cmd1')
def cmd(bot, trigger):
    pass
""")
    (temp_plugin_dir / 'plugin2.py').write_text("""
from sopel import plugin

@plugin.command('cmd2')
def cmd(bot, trigger):
    pass
""")
    
    plugins = load_plugins(
        [str(temp_plugin_dir)],
        enable=['plugin1']
    )
    assert len(plugins) == 1
    assert plugins[0].name == 'plugin1'


def test_load_plugin_with_setup_shutdown(temp_plugin_dir):
    """Test loading plugin with setup/shutdown hooks."""
    plugin_file = temp_plugin_dir / 'hooks.py'
    plugin_file.write_text("""
from sopel import plugin

def setup(bot):
    pass

def shutdown(bot):
    pass

@plugin.command('test')
def test_cmd(bot, trigger):
    pass
""")
    
    plugins = load_plugins([str(temp_plugin_dir)])
    assert len(plugins) == 1
    assert plugins[0].setup_func is not None
    assert plugins[0].shutdown_func is not None


def test_find_plugin_file(temp_plugin_dir):
    """Test finding plugin files."""
    (temp_plugin_dir / 'myplugin.py').write_text('# test')
    
    found = find_plugin_file('myplugin', [str(temp_plugin_dir)])
    assert found is not None
    assert 'myplugin.py' in found
    
    not_found = find_plugin_file('nonexistent', [str(temp_plugin_dir)])
    assert not_found is None


def test_load_plugin_with_multiple_decorators(temp_plugin_dir):
    """Test loading plugin with various decorator types."""
    plugin_file = temp_plugin_dir / 'multi.py'
    plugin_file.write_text("""
from sopel import plugin

@plugin.command('cmd')
def command_func(bot, trigger):
    pass

@plugin.rule(r'hello')
def rule_func(bot, trigger):
    pass

@plugin.event('JOIN')
def event_func(bot, trigger):
    pass

@plugin.interval(60)
def interval_func(bot):
    pass
""")
    
    plugins = load_plugins([str(temp_plugin_dir)])
    assert len(plugins) == 1
    p = plugins[0]
    assert len(p.commands) == 1
    assert len(p.rules) == 1
    assert len(p.events) == 1
    assert len(p.intervals) == 1
