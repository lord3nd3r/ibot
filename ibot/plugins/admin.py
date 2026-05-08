"""ibot admin control plugin.

Provides IRCd-style admin commands for managing the bot at runtime:
  - rehash:  Reload config and all plugins (like /rehash on an IRCd)
  - reload:  Reload a specific plugin
  - load:    Load a new plugin
  - unload:  Unload a plugin
  - plugins: List loaded plugins
  - join:    Join a channel
  - part:    Part a channel
  - raw:     Send a raw IRC command
  - quit:    Shut down the bot
  - nick:    Change the bot's nick
  - say/msg: Send a message to a target
  - mode:    Set a channel mode

All commands require owner status.
"""

from sopel import plugin
import logging
import os

LOGGER = logging.getLogger(__name__)


# ---- Rehash / Hot-Reload ----

@plugin.require_owner('Only the bot owner can rehash.')
@plugin.command('rehash')
def rehash(bot, trigger):
    """Reload config and all plugins, like /rehash on an IRCd."""
    bot.say('Rehashing...')

    try:
        from ibot.config import load_config
        from ibot.loader import load_plugins
        from ibot.sopel_shim.bot import SopelWrapper

        core_bot = bot._bot
        errors = []

        # Reload config from disk
        try:
            settings = load_config(core_bot.config_path)
            core_bot.settings = settings
            core_bot.dispatcher.settings = settings
        except Exception as e:
            bot.say(f'Config reload failed: {e}')
            LOGGER.exception("Config reload failed")
            return

        # Run shutdown hooks on current plugins
        for p in core_bot.dispatcher.plugins:
            if p.shutdown_func:
                try:
                    p.shutdown_func(bot)
                except Exception as e:
                    errors.append(f'{p.name} shutdown: {e}')
                    LOGGER.exception("Shutdown error in %s", p.name)

        # Clear all handlers
        core_bot.dispatcher.clear()

        # Reload all plugins from disk
        plugins = load_plugins(
            core_bot.plugin_dirs,
            settings=settings,
            exclude=settings.core.exclude,
            enable=settings.core.enable,
        )

        # Re-register
        core_bot.dispatcher.register_plugins(plugins)

        # Run setup hooks
        for p in plugins:
            if p.setup_func:
                try:
                    wrapper = SopelWrapper.__new__(SopelWrapper)
                    wrapper._bot = core_bot
                    wrapper._trigger = None
                    wrapper._default_destination = None
                    wrapper._output_prefix = ''
                    p.setup_func(wrapper)
                except TypeError:
                    try:
                        p.setup_func(settings)
                    except Exception as e:
                        errors.append(f'{p.name} setup: {e}')
                        LOGGER.exception("Setup failed: %s", p.name)
                except Exception as e:
                    errors.append(f'{p.name} setup: {e}')
                    LOGGER.exception("Setup failed: %s", p.name)

        cmd_count = len(core_bot.dispatcher._command_handlers)
        rule_count = len(core_bot.dispatcher._rule_handlers)

        # Reload disabled commands cache
        core_bot.dispatcher.load_disabled_commands()

        bot.say(
            f'Rehash complete: {len(plugins)} plugins loaded '
            f'({cmd_count} commands, {rule_count} rules)')

        if errors:
            bot.say(f'⚠ {len(errors)} error(s):')
            for err in errors:
                bot.say(f'  • {err}')

    except Exception as e:
        LOGGER.exception("Rehash failed")
        bot.say(f'Rehash failed: {e}')


@plugin.require_owner('Only the bot owner can reload plugins.')
@plugin.command('reload')
def reload_plugin(bot, trigger):
    """Reload a specific plugin from disk. Usage: .reload <name>"""
    name = trigger.group(2)
    if not name:
        bot.reply('Usage: .reload <plugin_name>')
        return
    name = name.strip()

    try:
        from ibot.loader import reload_plugin_file, find_plugin_file
        from ibot.sopel_shim.bot import SopelWrapper

        core_bot = bot._bot

        # Find the plugin file
        filepath = find_plugin_file(name, core_bot.plugin_dirs)
        if not filepath:
            bot.reply(f'Plugin not found: {name}')
            return

        # Run shutdown on old plugin
        for p in core_bot.dispatcher.plugins:
            if p.name == name and p.shutdown_func:
                try:
                    p.shutdown_func(bot)
                except Exception:
                    pass

        # Unregister old handlers
        core_bot.dispatcher.unregister_plugin(name)

        # Reload from disk
        new_plugin = reload_plugin_file(name, filepath)
        if not new_plugin:
            bot.reply(f'Failed to load plugin: {name}')
            return

        # Register new handlers
        core_bot.dispatcher.register_plugins([new_plugin])

        # Run setup
        if new_plugin.setup_func:
            try:
                wrapper = SopelWrapper.__new__(SopelWrapper)
                wrapper._bot = core_bot
                wrapper._trigger = None
                wrapper._default_destination = None
                wrapper._output_prefix = ''
                new_plugin.setup_func(wrapper)
            except TypeError:
                try:
                    new_plugin.setup_func(core_bot.settings)
                except Exception:
                    pass

        cmds = sum(len(f._commands) for f in new_plugin.commands)
        rules = len(new_plugin.rules)
        bot.say(f'Reloaded {name} ({cmds} commands, {rules} rules)')

    except Exception as e:
        LOGGER.exception("Reload failed for %s", name)
        bot.say(f'Reload failed: {e}')


@plugin.require_owner('Only the bot owner can load plugins.')
@plugin.command('load')
def load_plugin(bot, trigger):
    """Load a new plugin. Usage: .load <name>"""
    name = trigger.group(2)
    if not name:
        bot.reply('Usage: .load <plugin_name>')
        return
    name = name.strip()

    try:
        from ibot.loader import find_plugin_file, _load_plugin_file
        from ibot.sopel_shim.bot import SopelWrapper

        core_bot = bot._bot

        # Check if already loaded
        for p in core_bot.dispatcher.plugins:
            if p.name == name:
                bot.reply(f'{name} is already loaded. Use .reload instead.')
                return

        filepath = find_plugin_file(name, core_bot.plugin_dirs)
        if not filepath:
            bot.reply(f'Plugin not found: {name}')
            return

        new_plugin = _load_plugin_file(name, filepath)
        if not new_plugin:
            bot.reply(f'Failed to load plugin: {name}')
            return

        core_bot.dispatcher.register_plugins([new_plugin])

        if new_plugin.setup_func:
            try:
                wrapper = SopelWrapper.__new__(SopelWrapper)
                wrapper._bot = core_bot
                wrapper._trigger = None
                wrapper._default_destination = None
                wrapper._output_prefix = ''
                new_plugin.setup_func(wrapper)
            except TypeError:
                try:
                    new_plugin.setup_func(core_bot.settings)
                except Exception:
                    pass

        cmds = sum(len(f._commands) for f in new_plugin.commands)
        bot.say(f'Loaded {name} ({cmds} commands)')

    except Exception as e:
        LOGGER.exception("Load failed for %s", name)
        bot.say(f'Load failed: {e}')


@plugin.require_owner('Only the bot owner can unload plugins.')
@plugin.command('unload')
def unload_plugin(bot, trigger):
    """Unload a plugin. Usage: .unload <name>"""
    name = trigger.group(2)
    if not name:
        bot.reply('Usage: .unload <plugin_name>')
        return
    name = name.strip()

    core_bot = bot._bot

    # Prevent unloading the admin plugin
    if name == 'admin':
        bot.reply("Can't unload the admin plugin.")
        return

    # Check it's loaded
    found = False
    for p in core_bot.dispatcher.plugins:
        if p.name == name:
            found = True
            if p.shutdown_func:
                try:
                    p.shutdown_func(bot)
                except Exception:
                    pass
            break

    if not found:
        bot.reply(f'Plugin not loaded: {name}')
        return

    core_bot.dispatcher.unregister_plugin(name)
    bot.say(f'Unloaded {name}')


# ---- Plugin Info ----

@plugin.require_owner
@plugin.command('plugins')
def list_plugins(bot, trigger):
    """List all loaded plugins."""
    core_bot = bot._bot
    names = [p.name for p in core_bot.dispatcher.plugins]
    if names:
        bot.say(f'Loaded plugins ({len(names)}): {", ".join(sorted(names))}')
    else:
        bot.say('No plugins loaded.')


# ---- Channel Management ----

@plugin.require_admin('Only admins can make the bot join channels.')
@plugin.command('bjoin')
def bot_join(bot, trigger):
    """Join a channel. Usage: .bjoin #channel [key]"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: .bjoin #channel [key]')
        return
    parts = args.strip().split(None, 1)
    channel = parts[0]
    key = parts[1] if len(parts) > 1 else None
    bot.join(channel, key)
    bot.say(f'Joining {channel}')


@plugin.require_admin('Only admins can make the bot part channels.')
@plugin.command('bpart')
def bot_part(bot, trigger):
    """Part a channel. Usage: .bpart #channel [message]"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: .bpart #channel [message]')
        return
    parts = args.strip().split(None, 1)
    channel = parts[0]
    msg = parts[1] if len(parts) > 1 else None
    bot.part(channel, msg)


# ---- Raw IRC / Messaging ----

@plugin.require_owner('Only the bot owner can send raw commands.')
@plugin.command('raw')
def raw_cmd(bot, trigger):
    """Send a raw IRC command. Usage: .raw <command>"""
    raw = trigger.group(2)
    if not raw:
        bot.reply('Usage: .raw <IRC command>')
        return
    bot.write(raw)
    bot.reply('Sent.')


@plugin.require_admin
@plugin.command('say', 'msg')
def say_cmd(bot, trigger):
    """Send a message. Usage: .say <target> <message>"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: .say <target> <message>')
        return
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        bot.reply('Usage: .say <target> <message>')
        return
    target, message = parts
    bot.msg(target, message)


@plugin.require_admin
@plugin.command('act')
def act_cmd(bot, trigger):
    """Send an action. Usage: .act <target> <action>"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: .act <target> <action>')
        return
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        bot.reply('Usage: .act <target> <action>')
        return
    target, action = parts
    bot.action(action, destination=target)


# ---- Bot Control ----

@plugin.require_owner('Only the bot owner can change the nick.')
@plugin.command('bnick')
def bot_nick(bot, trigger):
    """Change the bot's nick. Usage: .bnick <newnick>"""
    new_nick = trigger.group(2)
    if not new_nick:
        bot.reply(f'Current nick: {bot.nick}')
        return
    new_nick = new_nick.strip()
    bot.write(f'NICK {new_nick}')
    bot.say(f'Changing nick to {new_nick}')


@plugin.require_admin
@plugin.command('bmode')
def bot_mode(bot, trigger):
    """Set a channel mode. Usage: .bmode #channel +o nick"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: .bmode #channel <mode> [target]')
        return
    bot.write(f'MODE {args.strip()}')


@plugin.require_owner('Only the bot owner can shut down the bot.')
@plugin.command('bquit', 'die')
def bot_quit(bot, trigger):
    """Shut down the bot. Usage: .bquit [message]"""
    msg = trigger.group(2) or 'Shutting down.'
    bot.quit(msg)
    bot._bot._running = False


# ---- Status ----

@plugin.require_admin
@plugin.command('bstatus')
def bot_status(bot, trigger):
    """Show bot status info."""
    core_bot = bot._bot
    n_plugins = len(core_bot.dispatcher.plugins)
    n_cmds = len(core_bot.dispatcher._command_handlers)
    n_rules = len(core_bot.dispatcher._rule_handlers)
    n_events = sum(len(v) for v in core_bot.dispatcher._event_handlers.values())
    n_channels = len(core_bot.channels)

    bot.say(
        f'Nick: {core_bot.nick} | '
        f'Channels: {n_channels} | '
        f'Plugins: {n_plugins} | '
        f'Commands: {n_cmds} | '
        f'Rules: {n_rules} | '
        f'Events: {n_events}'
    )


# ---- Per-Channel Command Disable/Enable ----

# Protected commands that cannot be disabled
_PROTECTED_COMMANDS = {
    'disable', 'enable', 'disabled',
    'rehash', 'reload', 'load', 'unload', 'plugins',
    'bquit', 'die', 'raw',
}


@plugin.require_admin('Only admins can disable commands.')
@plugin.require_privmsg('This command must be used in PM.')
@plugin.command('disable')
def disable_cmd(bot, trigger):
    """Disable a command in a channel. Usage (PM): .disable <command> <#channel>"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: disable <command> <#channel>')
        return

    parts = args.strip().split()
    if len(parts) < 2:
        bot.reply('Usage: disable <command> <#channel>')
        return

    cmd_name = parts[0].lower()
    channel = parts[1]

    if not channel.startswith(('#', '&')):
        bot.reply('Channel must start with # or &')
        return

    if cmd_name in _PROTECTED_COMMANDS:
        bot.reply(f'Cannot disable protected command: {cmd_name}')
        return

    core_bot = bot._bot
    channel_lower = channel.lower()

    # Update memory cache
    disabled = core_bot.memory.setdefault('disabled_commands', {})
    chan_disabled = disabled.setdefault(channel_lower, set())

    if cmd_name in chan_disabled:
        bot.reply(f'"{cmd_name}" is already disabled in {channel}')
        return

    chan_disabled.add(cmd_name)

    # Persist to DB
    core_bot.db.set_channel_value(channel, 'disabled_commands',
                                   sorted(chan_disabled))

    bot.reply(f'Disabled "{cmd_name}" in {channel}')
    LOGGER.info("Command '%s' disabled in %s by %s",
                cmd_name, channel, trigger.nick)


@plugin.require_admin('Only admins can enable commands.')
@plugin.require_privmsg('This command must be used in PM.')
@plugin.command('enable')
def enable_cmd(bot, trigger):
    """Enable a previously disabled command in a channel. Usage (PM): .enable <command> <#channel>"""
    args = trigger.group(2)
    if not args:
        bot.reply('Usage: enable <command> <#channel>')
        return

    parts = args.strip().split()
    if len(parts) < 2:
        bot.reply('Usage: enable <command> <#channel>')
        return

    cmd_name = parts[0].lower()
    channel = parts[1]

    if not channel.startswith(('#', '&')):
        bot.reply('Channel must start with # or &')
        return

    core_bot = bot._bot
    channel_lower = channel.lower()

    disabled = core_bot.memory.get('disabled_commands', {})
    chan_disabled = disabled.get(channel_lower, set())

    if cmd_name not in chan_disabled:
        bot.reply(f'"{cmd_name}" is not disabled in {channel}')
        return

    chan_disabled.discard(cmd_name)

    # Clean up empty sets
    if not chan_disabled:
        disabled.pop(channel_lower, None)
        core_bot.db.delete_channel_value(channel, 'disabled_commands')
    else:
        core_bot.db.set_channel_value(channel, 'disabled_commands',
                                       sorted(chan_disabled))

    bot.reply(f'Enabled "{cmd_name}" in {channel}')
    LOGGER.info("Command '%s' enabled in %s by %s",
                cmd_name, channel, trigger.nick)


@plugin.require_admin
@plugin.require_privmsg('This command must be used in PM.')
@plugin.command('disabled')
def disabled_list(bot, trigger):
    """List disabled commands. Usage (PM): .disabled [#channel]"""
    channel = (trigger.group(2) or '').strip()
    core_bot = bot._bot
    disabled = core_bot.memory.get('disabled_commands', {})

    if channel:
        # Show disabled commands for a specific channel
        chan_disabled = disabled.get(channel.lower(), set())
        if chan_disabled:
            bot.reply(f'Disabled in {channel}: {", ".join(sorted(chan_disabled))}')
        else:
            bot.reply(f'No commands disabled in {channel}')
    else:
        # Show all channels with disabled commands
        if not disabled:
            bot.reply('No commands disabled in any channel.')
            return
        for chan, cmds in sorted(disabled.items()):
            if cmds:
                bot.reply(f'{chan}: {", ".join(sorted(cmds))}')
