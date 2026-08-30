"""ibot entry point.

Usage:
    python -m ibot [config_file]
    python -m ibot --generate-config [filename]
"""

import argparse
import asyncio
import logging
import os
import sys

from ibot.bot import IRCBot
from ibot.config import load_config, create_default_config
from ibot.dispatch import Dispatcher
from ibot.loader import install_sopel_shim, load_plugins


def setup_logging(level='INFO'):
    """Configure logging for the bot."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def main():
    parser = argparse.ArgumentParser(
        prog='ibot',
        description='ibot - A Sopel-compatible IRC bot',
    )
    parser.add_argument(
        'config',
        nargs='?',
        default='ibot.cfg',
        help='Path to config file (default: ibot.cfg)',
    )
    parser.add_argument(
        '--generate-config',
        metavar='FILE',
        nargs='?',
        const='ibot.cfg',
        help='Generate a default config file and exit',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug logging',
    )

    args = parser.parse_args()

    # Generate config and exit
    if args.generate_config:
        create_default_config(args.generate_config)
        print(f"Default config written to: {args.generate_config}")
        return

    # Setup logging
    setup_logging('DEBUG' if args.verbose else 'INFO')
    logger = logging.getLogger('ibot')

    # Load config
    config_path = args.config
    if not os.path.exists(config_path):
        logger.error("Config file not found: %s", config_path)
        logger.info("Run 'python -m ibot --generate-config' to create one")
        sys.exit(1)

    settings = load_config(config_path)
    log_level = settings.core.logging_level or 'INFO'
    if args.verbose:
        log_level = 'DEBUG'
    setup_logging(log_level)

    logger.info("ibot starting up...")

    # Install sopel shim BEFORE loading plugins
    install_sopel_shim()

    # Determine plugin directories
    plugin_dirs = []
    # Built-in plugins directory
    builtin_dir = os.path.join(os.path.dirname(__file__), 'plugins')
    if os.path.isdir(builtin_dir):
        plugin_dirs.append(builtin_dir)

    # Extra plugin directories from config
    for extra_dir in settings.core.extra:
        extra_dir = os.path.realpath(os.path.expanduser(extra_dir.strip()))
        if os.path.isdir(extra_dir) and extra_dir not in [os.path.realpath(d) for d in plugin_dirs]:
            plugin_dirs.append(extra_dir)
        elif not os.path.isdir(extra_dir):
            logger.warning("Plugin directory not found: %s", extra_dir)

    # Default plugins dir relative to config
    config_dir = os.path.dirname(os.path.abspath(config_path))
    default_plugin_dir = os.path.join(config_dir, 'plugins')
    if os.path.isdir(default_plugin_dir) and default_plugin_dir not in plugin_dirs:
        plugin_dirs.append(default_plugin_dir)

    logger.info("Plugin directories: %s", plugin_dirs)

    # Load plugins
    plugins = load_plugins(
        plugin_dirs,
        settings=settings,
        exclude=settings.core.exclude,
        enable=settings.core.enable,
    )

    logger.info("Loaded %d plugins", len(plugins))

    # Create bot and dispatcher
    bot = IRCBot(settings)
    bot.plugin_dirs = plugin_dirs
    bot.config_path = config_path
    dispatcher = Dispatcher(bot, settings)
    dispatcher.register_plugins(plugins)
    bot.dispatcher = dispatcher

    # Load per-channel disabled commands from DB
    dispatcher.load_disabled_commands()

    # Run setup functions
    from ibot.sopel_shim.bot import SopelWrapper
    for plugin in plugins:
        if plugin.setup_func:
            try:
                # Setup receives the bot (some expect settings, some expect bot)
                wrapper = SopelWrapper.__new__(SopelWrapper)
                wrapper._bot = bot
                wrapper._trigger = None
                wrapper._default_destination = None
                wrapper._output_prefix = ''
                plugin.setup_func(wrapper)
                logger.info("Setup complete for plugin: %s", plugin.name)
            except TypeError:
                # Some setup functions expect just settings/config
                try:
                    plugin.setup_func(settings)
                except Exception:
                    logger.exception("Setup failed for plugin: %s",
                                     plugin.name)
            except Exception:
                logger.exception("Setup failed for plugin: %s", plugin.name)

    # Run the bot
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
    finally:
        # Run shutdown functions
        for plugin in plugins:
            if plugin.shutdown_func:
                try:
                    plugin.shutdown_func(bot)
                except Exception:
                    logger.exception("Shutdown error in %s", plugin.name)


if __name__ == '__main__':
    main()
