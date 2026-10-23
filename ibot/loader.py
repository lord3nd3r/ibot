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
import threading
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
                 enable: Optional[List[str]] = None,
                 errors: Optional[list] = None) -> List['PluginInfo']:
    """Discover and load all plugins from the given directories.

    :param plugin_dirs: list of directories to scan for .py files
    :param settings: bot config (passed to setup functions)
    :param exclude: list of plugin names to skip
    :param enable: if non-empty, only load these plugins
    :param errors: optional list; ``(name, message)`` is appended for every
        plugin that failed to import
    :returns: list of PluginInfo objects
    """
    exclude = exclude or []
    enable = enable or []
    plugins = []
    loaded_names = set()

    for plugin_dir in plugin_dirs:
        if not os.path.isdir(plugin_dir):
            LOGGER.warning("Plugin directory not found: %s", plugin_dir)
            continue

        real_dir = os.path.realpath(plugin_dir)

        for filename in sorted(os.listdir(real_dir)):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue

            name = filename[:-3]  # strip .py

            if name in loaded_names:
                LOGGER.debug("Skipping already loaded plugin: %s", name)
                continue

            if name in exclude:
                LOGGER.info("Skipping excluded plugin: %s", name)
                continue

            if enable and name not in enable:
                LOGGER.info("Skipping non-enabled plugin: %s", name)
                continue

            filepath = os.path.join(real_dir, filename)
            try:
                plugin = _load_plugin_file(name, filepath)
                if plugin:
                    plugins.append(plugin)
                    loaded_names.add(name)
                    LOGGER.info("Loaded plugin: %s (%d commands, %d rules, %d events)",
                                name,
                                len(plugin.commands),
                                len(plugin.rules),
                                len(plugin.events))
            except Exception as e:
                LOGGER.exception("Failed to load plugin '%s' from %s: %s", name, filepath, e)
                if errors is not None:
                    errors.append((name, f'{type(e).__name__}: {e}'))

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
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module

    try:
        spec.loader.exec_module(module)
    except BaseException as e:
        # Put back the previously loaded version (if any) so a failed
        # reload leaves the running plugin's module in place.
        if previous is not None:
            sys.modules[spec.name] = previous
        else:
            sys.modules.pop(spec.name, None)
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
    # _load_plugin_file replaces the sys.modules entry (so the file is
    # re-read from disk) and restores the old one if the import fails.
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



# ---------------------------------------------------------------------------
# Plugin lifecycle helpers (setup / shutdown / live reload / rehash)
# ---------------------------------------------------------------------------

_LIFECYCLE_LOCK = threading.RLock()


class PluginSetupError(Exception):
    """A plugin imported fine but its setup() raised."""


def make_plugin_bot(core_bot):
    """Build the ``bot`` object passed to setup()/shutdown()."""
    from ibot.sopel_shim.bot import SopelWrapper
    wrapper = SopelWrapper.__new__(SopelWrapper)
    wrapper._bot = core_bot
    wrapper._trigger = None
    wrapper._default_destination = None
    wrapper._output_prefix = ''
    return wrapper


def _call_with_bot(func, bot):
    """Call ``func(bot)`` -- or ``func()`` if it takes no arguments.

    The signature is inspected *before* the call, so the function runs
    exactly once (a TypeError raised inside it is a real error, not a cue
    to retry with other arguments).
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return func(bot)
    try:
        sig.bind(bot)
        return func(bot)
    except TypeError:
        pass
    try:
        sig.bind()
    except TypeError:
        return func(bot)
    return func()


def run_plugin_setup(plugin, core_bot):
    """Run a plugin's setup() once. Raises PluginSetupError on failure."""
    if not plugin.setup_func:
        return
    try:
        _call_with_bot(plugin.setup_func, make_plugin_bot(core_bot))
    except Exception as e:
        LOGGER.exception("Setup failed for plugin %s", plugin.name)
        raise PluginSetupError(f'{plugin.name} setup: {type(e).__name__}: {e}') from e


def run_plugin_shutdown(plugin, core_bot):
    """Run a plugin's shutdown(); returns an error string or None."""
    if not plugin.shutdown_func:
        return None
    try:
        _call_with_bot(plugin.shutdown_func, make_plugin_bot(core_bot))
    except Exception as e:
        LOGGER.exception("Shutdown error in plugin %s", plugin.name)
        return f'{plugin.name} shutdown: {type(e).__name__}: {e}'
    return None


def setup_registered_plugins(core_bot, plugins):
    """Run setup() for freshly registered plugins.

    A plugin whose setup fails is unregistered (its handlers would otherwise
    run against half-initialised state). Returns a list of error strings.
    """
    errors = []
    for plugin in list(plugins):
        try:
            run_plugin_setup(plugin, core_bot)
        except PluginSetupError as e:
            errors.append(str(e))
            core_bot.dispatcher.unregister_plugin(plugin.name)
            LOGGER.error("Plugin %s disabled because its setup failed", plugin.name)
    return errors


def _import_fresh(name, filepath):
    plugin = _load_plugin_file(name, filepath)
    if plugin is None:
        raise ImportError(f'Cannot load plugin {name} from {filepath}')
    return plugin


def _restore_module(plugin):
    if plugin is not None and plugin.module is not None:
        sys.modules[f'ibot_plugins.{plugin.name}'] = plugin.module


def _swap_plugin(core_bot, old, new):
    """Replace ``old`` (may be None) with ``new``; roll back if setup fails.

    Order matters: the old plugin is fully shut down before the new one's
    setup runs (plugins that monkey-patch the core rely on this).
    """
    disp = core_bot.dispatcher
    name = new.name
    warnings = []
    if old is not None:
        err = run_plugin_shutdown(old, core_bot)
        if err:
            warnings.append(err)
        disp.unregister_plugin(name)
    disp.register_plugins([new])
    try:
        run_plugin_setup(new, core_bot)
    except PluginSetupError:
        disp.unregister_plugin(name)
        if old is not None:
            LOGGER.warning("Restoring previous version of plugin %s", name)
            _restore_module(old)
            disp.register_plugins([old])
            try:
                run_plugin_setup(old, core_bot)
            except PluginSetupError as e2:
                LOGGER.error("Previous version of %s also failed setup: %s", name, e2)
                disp.unregister_plugin(name)
        raise
    return warnings


def reload_plugin_live(core_bot, name):
    """Reload (or load) one plugin by name on a running bot.

    The new code is imported *before* the running version is touched; if the
    import fails the old version keeps running. Raises on failure.
    Returns the new PluginInfo.
    """
    name = str(name).strip()
    if name.endswith('.py'):
        name = name[:-3]
    with _LIFECYCLE_LOCK:
        disp = core_bot.dispatcher
        filepath = find_plugin_file(name, getattr(core_bot, 'plugin_dirs', []) or [])
        if not filepath:
            raise FileNotFoundError(f'Plugin not found: {name}')
        old = next((p for p in disp.plugins if p.name == name), None)
        new = _import_fresh(name, filepath)
        try:
            warnings = _swap_plugin(core_bot, old, new)
        except Exception:
            raise
        for w in warnings:
            LOGGER.warning("Reload %s: %s", name, w)
        new.reload_warnings = warnings
        return new


def unload_plugin_live(core_bot, name):
    """Shut down and unregister a plugin. Returns an error string or None."""
    with _LIFECYCLE_LOCK:
        disp = core_bot.dispatcher
        old = next((p for p in disp.plugins if p.name == name), None)
        if old is None:
            raise KeyError(name)
        err = run_plugin_shutdown(old, core_bot)
        disp.unregister_plugin(name)
        return err


def rehash_live(core_bot, settings):
    """Reload all plugins with new settings, keeping what fails to import.

    1. Import every plugin first. Plugins that fail to import keep running
       their current version untouched.
    2. For the rest: old shutdown -> unregister -> register new -> setup.
       If a new setup fails, the previous version is restored.
    3. Plugins that disappeared (deleted / newly excluded) are unloaded.

    Returns ``(active_plugin_names, errors)``.
    """
    with _LIFECYCLE_LOCK:
        disp = core_bot.dispatcher
        old_settings = core_bot.settings
        import_errors = []
        new_plugins = load_plugins(
            core_bot.plugin_dirs,
            settings=settings,
            exclude=settings.core.exclude,
            enable=settings.core.enable,
            errors=import_errors,
        )
        errors = [f'{n} import: {msg}' for n, msg in import_errors]
        failed = {n for n, _ in import_errors}
        new_by_name = {p.name: p for p in new_plugins}

        core_bot.settings = settings
        disp.settings = settings

        for old in list(disp.plugins):
            if old.name in new_by_name:
                continue
            if old.name in failed:
                LOGGER.warning("Keeping running version of %s (new version "
                               "failed to import)", old.name)
                continue
            LOGGER.info("Unloading plugin %s (removed or excluded)", old.name)
            err = run_plugin_shutdown(old, core_bot)
            if err:
                errors.append(err)
            disp.unregister_plugin(old.name)

        for new in new_plugins:
            old = next((p for p in disp.plugins if p.name == new.name), None)
            try:
                for w in _swap_plugin(core_bot, old, new):
                    errors.append(w)
            except PluginSetupError as e:
                errors.append(str(e) + (' (kept previous version)' if old else ''))
            except Exception as e:
                LOGGER.exception("Rehash failed for plugin %s", new.name)
                errors.append(f'{new.name}: {type(e).__name__}: {e}')

        # Plugins kept from before may have defined config sections on the
        # old Config object; carry those definitions over.
        try:
            defined = dict(getattr(settings, '_sections', {}) or {})
            for sec_name, cls in list(getattr(old_settings, '_sections', {}).items()):
                if sec_name not in defined:
                    settings.define_section(sec_name, cls)
        except Exception:
            LOGGER.exception("Failed to carry config sections over on rehash")

        try:
            disp._rebuild_ignore_lists()
        except Exception as e:
            LOGGER.exception("Failed to rebuild ignore lists")
            errors.append(f'ignore lists: {e}')
        return [p.name for p in disp.plugins], errors
