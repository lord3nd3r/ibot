"""Sopel-compatible config types.

Provides StaticSection and its attribute descriptors so plugins can define
custom config sections that read from the INI file.
"""

import logging
import os
import re

LOGGER = logging.getLogger(__name__)


class NO_DEFAULT:
    """Sentinel indicating no default value is available."""


class StaticSection:
    """A configuration section with parsed and validated settings.

    Plugins subclass this and add attribute descriptors (ValidatedAttribute,
    BooleanAttribute, etc.) to define their config options.
    """

    def __init__(self, config, section_name, validate=True):
        if not config.parser.has_section(section_name):
            config.parser.add_section(section_name)
        self._parent = config
        self._parser = config.parser
        self._section_name = section_name

    def configure_setting(self, name, prompt, default=NO_DEFAULT):
        """Interactive configuration (stub for compatibility)."""
        pass


class BaseValidated:
    """Base class for config attribute descriptors."""

    def __init__(self, name, default=None, is_secret=False):
        self.name = name
        self.default = default
        self.is_secret = bool(is_secret)

    def serialize(self, value):
        return str(value)

    def parse(self, value):
        return value

    def __get__(self, instance, owner=None):
        if instance is None:
            return self

        value = None
        env_name = 'SOPEL_%s_%s' % (
            instance._section_name.upper(), self.name.upper())
        if env_name in os.environ:
            value = os.environ.get(env_name)
        elif instance._parser.has_option(instance._section_name, self.name):
            value = instance._parser.get(instance._section_name, self.name)

        if value is not None:
            return self.parse(value)
        if self.default is not NO_DEFAULT:
            return self.default
        return None

    def __set__(self, instance, value):
        if value is None:
            instance._parser.remove_option(instance._section_name, self.name)
            return
        instance._parser.set(
            instance._section_name, self.name, self.serialize(value))

    def __delete__(self, instance):
        instance._parser.remove_option(instance._section_name, self.name)


class ValidatedAttribute(BaseValidated):
    """A descriptor for settings in a StaticSection.

    Supports optional parse/serialize callables for type conversion.
    """

    def __init__(self, name, parse=None, serialize=None,
                 default=None, is_secret=False):
        super().__init__(name, default=default, is_secret=is_secret)
        if parse == bool:
            self._parse_func = _parse_boolean
            self._serialize_func = _serialize_boolean
        else:
            self._parse_func = parse
            self._serialize_func = serialize

    def parse(self, value):
        if self._parse_func:
            return self._parse_func(value)
        return value

    def serialize(self, value):
        if self._serialize_func:
            return self._serialize_func(value)
        return str(value)


class BooleanAttribute(BaseValidated):
    """A descriptor for Boolean settings."""

    def __init__(self, name, default=False):
        super().__init__(name, default=default, is_secret=False)

    def parse(self, value):
        if value is True or value == 1:
            return True
        if isinstance(value, str):
            return value.lower() in [
                '1', 'enable', 'enabled', 'on', 'true', 'y', 'yes',
            ]
        return bool(value)

    def serialize(self, value):
        return 'true' if self.parse(value) else 'false'


class SecretAttribute(ValidatedAttribute):
    """A config attribute for secret/password values."""

    def __init__(self, name, parse=None, serialize=None, default=None):
        super().__init__(
            name, parse=parse, serialize=serialize,
            default=default, is_secret=True,
        )


class ListAttribute(BaseValidated):
    """A config attribute containing a list of string values.

    Supports both multi-line and comma-separated formats.
    """
    DELIMITER = ','
    QUOTE_REGEX = re.compile(r'^"(?P<value>#.*)"$')

    def __init__(self, name, strip=True, default=None):
        default = default or []
        super().__init__(name, default=default)
        self.strip = strip

    def parse(self, value):
        if not value:
            return []
        if "\n" in value:
            items = (
                item.strip(self.DELIMITER).strip()
                for item in value.splitlines()
            )
        else:
            items = value.split(self.DELIMITER)

        parsed = []
        for item in items:
            item = item.strip() if self.strip else item
            if not item:
                continue
            # Unquote items starting with #
            result = self.QUOTE_REGEX.match(item)
            if result:
                item = result.group('value')
            parsed.append(item)
        return parsed

    def serialize(self, value):
        if not isinstance(value, (list, set, tuple)):
            raise ValueError('ListAttribute value must be a list.')
        if not value:
            return ''
        return '\n' + '\n'.join(str(item) for item in value)


class ChoiceAttribute(BaseValidated):
    """A config attribute which must be one of a set of choices."""

    def __init__(self, name, choices, default=None):
        super().__init__(name, default=default)
        self.choices = choices

    def parse(self, value):
        if value in self.choices:
            return value
        raise ValueError(
            f'{value!r} is not one of: {", ".join(self.choices)}')

    def serialize(self, value):
        if value in self.choices:
            return value
        raise ValueError(
            f'{value!r} is not one of: {", ".join(self.choices)}')


class FilenameAttribute(BaseValidated):
    """A config attribute representing a filesystem path."""

    def __init__(self, name, relative=True, directory=False, default=None):
        super().__init__(name, default=default)
        self.relative = relative
        self.directory = directory

    def parse(self, value):
        if not value:
            return None
        return os.path.expanduser(value)

    def serialize(self, value):
        return str(value) if value else ''


# Helper functions for boolean parsing
def _parse_boolean(value):
    if value is True or value == 1:
        return value
    if isinstance(value, str):
        return value.lower() in ['1', 'yes', 'y', 'true', 'on']
    return bool(value)


def _serialize_boolean(value):
    return 'true' if _parse_boolean(value) else 'false'
