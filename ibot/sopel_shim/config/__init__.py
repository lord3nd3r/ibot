"""Sopel-compatible configuration module."""

from ibot.sopel_shim.config.core_section import CoreSection
import configparser
import os


class Config:
    """Sopel-compatible configuration wrapper.

    Reads an INI-style config file and provides attribute-style access.
    Supports define_section() for plugin custom config sections.
    """

    def __init__(self, filename=None):
        self.parser = configparser.ConfigParser(allow_no_value=True)
        self.filename = filename
        self._sections = {}
        self._section_instances = {}

        if filename and os.path.exists(filename):
            self.parser.read(filename)
            self.homedir = os.path.dirname(os.path.abspath(filename))
            self.basename = os.path.splitext(os.path.basename(filename))[0]
        else:
            self.homedir = os.path.expanduser('~/.sopel')
            self.basename = 'default'

        # Always create core section
        self.core = CoreSection(self.parser, self)

    def __contains__(self, item):
        return self.parser.has_section(item)

    def __getitem__(self, item):
        if self.parser.has_section(item):
            return _SectionProxy(self.parser, item)
        raise KeyError(item)

    def __getattr__(self, name):
        if name.startswith('_') or name in (
            'parser', 'filename', 'core', 'homedir', 'basename',
            '_sections', '_section_instances',
        ):
            raise AttributeError(name)
        # Check for defined sections (plugin config sections)
        if name in self._section_instances:
            return self._section_instances[name]
        if self.parser.has_section(name):
            return _SectionProxy(self.parser, name)
        raise AttributeError(f"No config section: {name}")

    def define_section(self, name, cls, validate=False):
        """Register and instantiate a custom config section.

        This is the key method plugins use to define their config sections:
            bot.config.define_section('grok', GrokSection)
        """
        self._sections[name] = cls
        try:
            instance = cls(self, name, validate=validate)
            self._section_instances[name] = instance
        except Exception:
            # If instantiation fails, provide a basic proxy
            self._section_instances[name] = _SectionProxy(self.parser, name)

    def get_defined_sections(self):
        """Return defined config sections."""
        return [(name, cls) for name, cls in self._sections.items()]

    def option(self, section, key, default=None):
        """Get a config option with a default."""
        try:
            return self.parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def has_option(self, section, key):
        """Check if a config option exists."""
        return self.parser.has_option(section, key)

    def save(self):
        """Write the config to disk."""
        if self.filename:
            with open(self.filename, 'w') as f:
                self.parser.write(f)


class _SectionProxy:
    """Provides attribute-style access to a config section."""

    def __init__(self, parser, section):
        self._parser = parser
        self._section = section

    def __getattr__(self, key):
        if key.startswith('_'):
            raise AttributeError(key)
        try:
            return self._parser.get(self._section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return None

    def __contains__(self, key):
        return self._parser.has_option(self._section, key)

    def __getitem__(self, key):
        return self.__getattr__(key)
