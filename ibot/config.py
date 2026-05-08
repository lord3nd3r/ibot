"""Configuration loader for ibot.

Wraps the sopel_shim config and provides the main config loading interface.
"""

import os
from typing import Optional
from ibot.sopel_shim.config import Config


def load_config(filename: str) -> Config:
    """Load an ibot configuration file.

    :param filename: path to the INI config file
    :returns: Config object
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Config file not found: {filename}")
    return Config(filename)


def create_default_config(filename: str) -> None:
    """Create a default config file if one doesn't exist."""
    if os.path.exists(filename):
        return

    default = """\
[core]
nick = ibot
host = irc.libera.chat
port = 6697
use_ssl = true
verify_ssl = true
owner = yournick
channels = #yourchannel
prefix = \\.
db_filename = ibot.db

# Authentication (optional)
# auth_method = sasl
# auth_user = ibot
# auth_password = yourpassword

# Admin list
# admins = admin1, admin2
# admin_accounts = account1, account2

# Plugin directories (comma-separated)
# extra = /path/to/plugins

# Plugins to exclude
# exclude = plugin1, plugin2

# Flood protection
# flood_burst = 4
# flood_refill = 1

# Logging
# logging_level = INFO
"""
    with open(filename, 'w') as f:
        f.write(default)
