"""Sopel-compatible [core] config section."""

import os


class CoreSection:
    """Represents the [core] section of Sopel's config.

    Provides attribute-style access to core bot settings with sensible defaults.
    """

    def __init__(self, parser, config=None):
        self._parser = parser
        self._config = config

    def _get(self, key, default=None):
        try:
            return self._parser.get('core', key)
        except Exception:
            return default

    def _getbool(self, key, default=False):
        try:
            return self._parser.getboolean('core', key)
        except Exception:
            return default

    def _getint(self, key, default=0):
        try:
            return self._parser.getint('core', key)
        except Exception:
            return default

    def _getlist(self, key, default=None):
        raw = self._get(key)
        if raw is None:
            return default or []
        # Support both multi-line and comma-separated
        if '\n' in raw:
            items = [item.strip() for item in raw.splitlines() if item.strip()]
        else:
            items = [item.strip() for item in raw.split(',') if item.strip()]
        # Strip surrounding quotes (Sopel uses "value" to protect # chars)
        cleaned = []
        for item in items:
            if (item.startswith('"') and item.endswith('"')) or \
               (item.startswith("'") and item.endswith("'")):
                item = item[1:-1]
            cleaned.append(item)
        return cleaned

    @property
    def nick(self):
        return self._get('nick', 'ibot')

    @property
    def host(self):
        return self._get('host', 'irc.libera.chat')

    @property
    def port(self):
        return self._getint('port', 6697)

    @property
    def use_ssl(self):
        return self._getbool('use_ssl', True)

    @property
    def verify_ssl(self):
        return self._getbool('verify_ssl', True)

    @property
    def owner(self):
        return self._get('owner', '')

    @property
    def owner_account(self):
        return self._get('owner_account', '')

    @property
    def channels(self):
        return self._getlist('channels', [])

    @property
    def prefix(self):
        return self._get('prefix', '\\.')

    @property
    def help_prefix(self):
        return self._get('help_prefix', '.')

    @property
    def auth_method(self):
        return self._get('auth_method', '')

    @property
    def auth_user(self):
        return self._get('auth_user', '')

    @property
    def auth_password(self):
        return self._get('auth_password', '')

    @property
    def auth_target(self):
        return self._get('auth_target', 'NickServ')

    @property
    def admins(self):
        return self._getlist('admins', [])

    @property
    def admin_accounts(self):
        return self._getlist('admin_accounts', [])

    @property
    def db_filename(self):
        return self._get('db_filename', '')

    @property
    def db_type(self):
        return self._get('db_type', 'sqlite')

    @property
    def db_url(self):
        return self._get('db_url', None)

    @property
    def db_user(self):
        return self._get('db_user', None)

    @property
    def db_pass(self):
        return self._get('db_pass', None)

    @property
    def db_host(self):
        return self._get('db_host', None)

    @property
    def db_port(self):
        return self._get('db_port', None)

    @property
    def db_name(self):
        return self._get('db_name', None)

    @property
    def db_driver(self):
        return self._get('db_driver', None)

    @property
    def homedir(self):
        """The directory where the config file lives."""
        if self._config and hasattr(self._config, 'homedir'):
            return self._config.homedir
        return os.path.expanduser('~/.sopel')

    @property
    def db_dir(self):
        """Directory for the database file."""
        return self._get('db_dir', None) or self.homedir

    @property
    def extra(self):
        """Extra plugin directories."""
        return self._getlist('extra', [])

    @property
    def exclude(self):
        """Plugins to exclude from loading."""
        return self._getlist('exclude', [])

    @property
    def enable(self):
        """Plugins to exclusively enable (empty = all)."""
        return self._getlist('enable', [])

    @property
    def logging_level(self):
        return self._get('logging_level', 'INFO')

    @property
    def logging_format(self):
        return self._get('logging_format', None)

    @property
    def logging_datefmt(self):
        return self._get('logging_datefmt', None)

    @property
    def logging_channel(self):
        return self._get('logging_channel', None)

    @property
    def logging_channel_level(self):
        return self._get('logging_channel_level', None)

    @property
    def logging_channel_format(self):
        return self._get('logging_channel_format', None)

    @property
    def logging_channel_datefmt(self):
        return self._get('logging_channel_datefmt', None)

    @property
    def flood_burst(self):
        return self._getint('flood_burst', 4)

    @property
    def flood_refill(self):
        return self._getint('flood_refill', 1)

    @property
    def flood_empty_wait(self):
        return self._getint('flood_empty_wait', 0)

    @property
    def reconnect_on_disconnect(self):
        return self._getbool('reconnect_on_disconnect', True)
