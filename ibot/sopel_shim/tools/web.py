"""Sopel-compatible web utilities."""

import re
import urllib.parse


_URL_REGEX = re.compile(
    r'(?:https?|ftp)://[^\s<>\'")\]]+',
    re.IGNORECASE,
)


def search_urls(text, schemes=None):
    """Find URLs in text."""
    return _URL_REGEX.findall(text)


def quote(s, safe=''):
    """URL-encode a string."""
    return urllib.parse.quote(s, safe=safe)


def unquote(s):
    """URL-decode a string."""
    return urllib.parse.unquote(s)
