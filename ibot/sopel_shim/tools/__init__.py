"""Sopel-compatible tools module.

Provides Identifier, SopelMemory, and other utility classes.
"""

import re
import threading
from collections import OrderedDict
from typing import Any, Optional, Pattern


class Identifier(str):
    """A string subclass representing an IRC identifier (nick/channel).

    Comparisons are case-insensitive per IRC rules (RFC 1459).
    """

    def __new__(cls, identifier):
        s = str.__new__(cls, identifier)
        return s

    @staticmethod
    def _lower(text):
        """IRC case-fold: uppercase {, }, | map to [, ], \\."""
        return (text.lower()
                .replace('{', '[')
                .replace('}', ']')
                .replace('|', '\\')
                .replace('~', '^'))

    def lower(self):
        return Identifier._lower(str(self))

    def __eq__(self, other):
        if isinstance(other, str):
            return Identifier._lower(str(self)) == Identifier._lower(other)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash(Identifier._lower(str(self)))

    def is_nick(self) -> bool:
        """Check if this identifier is a nickname (not a channel)."""
        return not str(self).startswith(('#', '&', '+', '!'))


class SopelMemory(dict):
    """A thread-safe dictionary for sharing data between plugins."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            return super().__getitem__(key)

    def __setitem__(self, key, value):
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key):
        with self._lock:
            super().__delitem__(key)

    def __contains__(self, key):
        with self._lock:
            return super().__contains__(key)

    def get(self, key, default=None):
        with self._lock:
            return super().get(key, default)

    def setdefault(self, key, default=None):
        with self._lock:
            return super().setdefault(key, default)

    def pop(self, key, *args):
        with self._lock:
            return super().pop(key, *args)

    def __iter__(self):
        with self._lock:
            return iter(list(super().keys()))

    def keys(self):
        with self._lock:
            return list(super().keys())

    def values(self):
        with self._lock:
            return list(super().values())

    def items(self):
        with self._lock:
            return list(super().items())

    def __len__(self):
        with self._lock:
            return super().__len__()


class SopelMemoryWithDefault(SopelMemory):
    """SopelMemory subclass that supports a default factory."""

    def __init__(self, default_factory=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = self.default_factory()
        return self[key]


class SopelIdentifierMemory(SopelMemory):
    """A SopelMemory that uses Identifier keys for case-insensitive lookups."""

    def __getitem__(self, key):
        return super().__getitem__(Identifier(key))

    def __setitem__(self, key, value):
        super().__setitem__(Identifier(key), value)

    def __delitem__(self, key):
        super().__delitem__(Identifier(key))

    def __contains__(self, key):
        return super().__contains__(Identifier(key))

    def get(self, key, default=None):
        return super().get(Identifier(key), default)


def get_hostmask_regex(mask: str) -> Pattern:
    """Convert a hostmask pattern (nick!user@host) to a compiled regex."""
    # Escape everything except *
    mask = re.escape(mask)
    mask = mask.replace(r'\*', '.*')
    return re.compile(mask + '$', re.IGNORECASE)


def chain_loaders(*loaders):
    """Chain multiple lazy loader functions together."""
    def combined_loader(settings):
        results = []
        for loader in loaders:
            results.extend(loader(settings))
        return results
    return combined_loader


class web:
    """Web-related utility methods."""

    _url_regex = re.compile(
        r'(?:https?|ftp)://[^\s<>\'")\]]+',
        re.IGNORECASE,
    )

    @staticmethod
    def search_urls(text, schemes=None):
        """Find URLs in text."""
        return web._url_regex.findall(text)


class events:
    """Numeric IRC events mapped to human-readable names."""
    RPL_WELCOME = '001'
    RPL_YOURHOST = '002'
    RPL_CREATED = '003'
    RPL_MYINFO = '004'
    RPL_ISUPPORT = '005'
    RPL_LUSERCLIENT = '251'
    RPL_LUSEROP = '252'
    RPL_LUSERUNKNOWN = '253'
    RPL_LUSERCHANNELS = '254'
    RPL_LUSERME = '255'
    RPL_AWAY = '301'
    RPL_WHOISUSER = '311'
    RPL_WHOISSERVER = '312'
    RPL_WHOISOPERATOR = '313'
    RPL_ENDOFWHO = '315'
    RPL_WHOISIDLE = '317'
    RPL_ENDOFWHOIS = '318'
    RPL_WHOISCHANNELS = '319'
    RPL_WHOISACCOUNT = '330'
    RPL_TOPIC = '332'
    RPL_TOPICWHOTIME = '333'
    RPL_WHOREPLY = '352'
    RPL_NAMREPLY = '353'
    RPL_ENDOFNAMES = '366'
    RPL_MOTD = '372'
    RPL_MOTDSTART = '375'
    RPL_ENDOFMOTD = '376'
    ERR_NOSUCHNICK = '401'
    ERR_NOSUCHCHANNEL = '403'
    ERR_CANNOTSENDTOCHAN = '404'
    ERR_UNKNOWNCOMMAND = '421'
    ERR_NOMOTD = '422'
    ERR_NICKNAMEINUSE = '433'
    ERR_NOTREGISTERED = '451'
    ERR_NEEDMOREPARAMS = '461'
    ERR_ALREADYREGISTRED = '462'
    ERR_CHANOPRIVSNEEDED = '482'
    RPL_SASLSUCCESS = '903'
    ERR_SASLFAIL = '904'
    ERR_SASLTOOLONG = '905'
    ERR_SASLABORTED = '906'
    RPL_LOGGEDIN = '900'
    RPL_LOGGEDOUT = '901'
