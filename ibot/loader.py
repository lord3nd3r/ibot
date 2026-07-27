"""Plugin loader for ibot.

Discovers, imports, and registers Sopel-compatible plugins from .py files.
Injects the sopel shim into sys.modules so `from sopel import plugin` works.
"""

import importlib
import importlib.util
import inspect
import logging
import os
import sys
from typing import List, Optional

LOGGER = logging.getLogger(__name__)


def install_sopel_shim() -> None:
    """Install the sopel compatibility shim into sys.modules.

    This makes `import sopel`, `from sopel import plugin`, etc. resolve
    to our shim package instead of the real sopel (if installed).
    """
    from ibot import sopel_shim
    from ibot.sopel_shim import (
        plugin, module, trigger, bot, db,
        config, tools, formatting, privileges,
    )
    from ibot.sopel_shim.tools import web as tools_web
    from ibot.sopel_shim.tools import time as tools_time
    from ibot.sopel_shim.config import core_section
    from ibot.sopel_shim.config import types as config_types
    from types import ModuleType

    sys.modules['sopel'] = sopel_shim
    sys.modules['sopel.plugin'] = plugin
    sys.modules['sopel.module'] = module
    sys.modules['sopel.trigger'] = trigger
    sys.modules['sopel.bot'] = bot
    sys.modules['sopel.db'] = db
    sys.modules['sopel.config'] = config
    sys.modules['sopel.config.core_section'] = core_section
    sys.modules['sopel.config.types'] = config_types
    sys.modules['sopel.tools'] = tools
    sys.modules['sopel.tools.web'] = tools_web
    sys.modules['sopel.tools.time'] = tools_time
    sys.modules['sopel.formatting'] = formatting
    sys.modules['sopel.privileges'] = privileges

    # Keep attribute access and import paths on the same objects.
    tools.web = tools_web
    tools.time = tools_time

    # Expose sopel.tools.target (live User/Channel state objects).
    # Imported here (not at package import time) to avoid a circular import
    # with ibot.bot.
    from ibot.sopel_shim import target as target_mod
    sys.modules['sopel.tools.target'] = target_mod
    tools.target = target_mod

    # Create a tools.identifiers alias pointing to tools (Identifier lives there)
    identifiers_mod = ModuleType('sopel.tools.identifiers')
    identifiers_mod.Identifier = tools.Identifier
    identifiers_mod.IdentifierFactory = tools.Identifier  # type alias
    sys.modules['sopel.tools.identifiers'] = identifiers_mod

    # Create sopel.tools.events alias
    events_mod = ModuleType('sopel.tools.events')
    for attr in dir(tools.events):
        if not attr.startswith('_'):
            setattr(events_mod, attr, getattr(tools.events, attr))
    sys.modules['sopel.tools.events'] = events_mod

    # Stub modules for less common imports
    for stub_name in ('sopel.irc', 'sopel.irc.utils', 'sopel.lifecycle',
                       'sopel.plugins', 'sopel.plugins.exceptions'):
        if stub_name not in sys.modules:
            stub = ModuleType(stub_name)
            # Add a no-op deprecated decorator for sopel.lifecycle
            if stub_name == 'sopel.lifecycle':
                stub.deprecated = lambda *a, **kw: (lambda f: f)
            sys.modules[stub_name] = stub

    LOGGER.info("Sopel compatibility shim installed")


class PluginInfo:
    """Holds metadata about a loaded plugin."""

    def __init__(self, name, module):
        self.name = name
        self.module = module
        self.commands = []        # Functions with @command
        self.rules = []           # Functions with @rule
        self.events = []          # Functions with @event
        self.nick_commands = []   # Functions with @nickname_command
        self.action_commands = [] # Functions with @action_command
        self.intervals = []       # Functions with @interval
        self.url_callbacks = []   # Functions with @url
        self.find_rules = []      # Functions with @find
        self.search_rules = []    # Functions with @search
        self.ctcp_handlers = []   # Functions with @ctcp
        self.setup_func = None
        self.shutdown_func = None


def load_plugins(plugin_dirs: List[str], settings=None, 
                 exclude: Optional[List[str]] = None, 
                 enable: Optional[List[str]] = None) -> List['PluginInfo']:
    """Discover and load all plugins from the given directories.

    :param plugin_dirs: list of directories to scan for .py files
    :param settings: bot config (passed to setup functions)
    :param exclude: list of plugin names to skip
    :param enable: if non-empty, only load these plugins
    :returns: list of PluginInfo objects
    """
    exclude = exclude or []
    enable = enable or []
    plugins = []

    for plugin_dir in plugin_dirs:
        if not os.path.isdir(plugin_dir):
            LOGGER.warning("Plugin directory not found: %s", plugin_dir)
            continue

        for filename in sorted(os.listdir(plugin_dir)):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue

            name = filename[:-3]  # strip .py

            if name in exclude:
                LOGGER.info("Skipping excluded plugin: %s", name)
                continue

            if enable and name not in enable:
                LOGGER.info("Skipping non-enabled plugin: %s", name)
                continue

            filepath = os.path.join(plugin_dir, filename)
            try:
                plugin = _load_plugin_file(name, filepath)
                if plugin:
                    plugins.append(plugin)
                    LOGGER.info("Loaded plugin: %s (%d commands, %d rules, %d events)",
                                name,
                                len(plugin.commands),
                                len(plugin.rules),
                                len(plugin.events))
            except Exception as e:
                LOGGER.exception("Failed to load plugin '%s' from %s: %s", name, filepath, e)

    return plugins


def _load_plugin_file(name: str, filepath: str) -> Optional['PluginInfo']:
    """Load a single .py plugin file and extract its handlers."""
    spec = importlib.util.spec_from_file_location(
        f'ibot_plugins.{name}', filepath
    )
    if spec is None or spec.loader is None:
        LOGGER.error("Cannot create module spec for plugin '%s' at %s", name, filepath)
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        del sys.modules[spec.name]
        LOGGER.error("Failed to execute plugin module '%s': %s", name, e)
        raise

    plugin = PluginInfo(name, module)

    # Check for setup/shutdown functions
    if hasattr(module, 'setup'):
        plugin.setup_func = module.setup
    if hasattr(module, 'shutdown'):
        plugin.shutdown_func = module.shutdown

    # Scan all module-level functions for plugin decorators
    for obj_name, obj in inspect.getmembers(module, inspect.isfunction):
        if not hasattr(obj, '_ibot_plugin'):
            continue

        if getattr(obj, '_commands', []):
            plugin.commands.append(obj)
        if getattr(obj, '_rules', []) or getattr(obj, '_rules_lazy_loaders', []):
            plugin.rules.append(obj)
        if getattr(obj, '_events', []):
            plugin.events.append(obj)
        if getattr(obj, '_nickname_commands', []):
            plugin.nick_commands.append(obj)
        if getattr(obj, '_action_commands', []):
            plugin.action_commands.append(obj)
        if getattr(obj, '_intervals', []):
            plugin.intervals.append(obj)
        if getattr(obj, '_url_regex', []) or getattr(obj, '_url_lazy_loaders', []):
            plugin.url_callbacks.append(obj)
        if getattr(obj, '_find_rules', []) or getattr(obj, '_find_rules_lazy_loaders', []):
            plugin.find_rules.append(obj)
        if getattr(obj, '_search_rules', []) or getattr(obj, '_search_rules_lazy_loaders', []):
            plugin.search_rules.append(obj)
        if getattr(obj, '_ctcp', []):
            plugin.ctcp_handlers.append(obj)

    return plugin


def reload_plugin_file(name: str, filepath: str) -> Optional['PluginInfo']:
    """Reload a single plugin by re-importing its module.

    Removes the old module from sys.modules first so the file is
    actually re-read from disk.
    """
    mod_name = f'ibot_plugins.{name}'
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return _load_plugin_file(name, filepath)


def find_plugin_file(name: str, plugin_dirs: List[str]) -> Optional[str]:
    """Find a plugin file by name across all plugin directories.

    Returns the full path or None.
    """
    for plugin_dir in plugin_dirs:
        filepath = os.path.join(plugin_dir, f'{name}.py')
        if os.path.isfile(filepath):
            return filepath
    return None

