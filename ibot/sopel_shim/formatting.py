"""Sopel-compatible IRC formatting utilities."""

import re

# IRC formatting codes
BOLD = '\x02'
ITALIC = '\x1d'
UNDERLINE = '\x1f'
STRIKETHROUGH = '\x1e'
MONOSPACE = '\x11'
RESET = '\x0f'
COLOR = '\x03'
REVERSE = '\x16'

# Regex to strip all IRC formatting
_FORMAT_STRIP = re.compile(
    r'[\x02\x1d\x1f\x1e\x11\x0f\x16]|'
    r'\x03(\d{1,2}(,\d{1,2})?)?'
)


def plain(text):
    """Strip all IRC formatting codes from text."""
    return _FORMAT_STRIP.sub('', text)


def bold(text):
    """Wrap text in IRC bold formatting."""
    return BOLD + text + BOLD


def italic(text):
    """Wrap text in IRC italic formatting."""
    return ITALIC + text + ITALIC


def underline(text):
    """Wrap text in IRC underline formatting."""
    return UNDERLINE + text + UNDERLINE


def strikethrough(text):
    """Wrap text in IRC strikethrough formatting."""
    return STRIKETHROUGH + text + STRIKETHROUGH


def monospace(text):
    """Wrap text in IRC monospace formatting."""
    return MONOSPACE + text + MONOSPACE


def color(text, fg=None, bg=None):
    """Wrap text in IRC color codes."""
    if fg is None:
        return text
    code = COLOR + str(fg).zfill(2)
    if bg is not None:
        code += ',' + str(bg).zfill(2)
    return code + text + COLOR


# Color name constants
class colors:
    WHITE = 0
    BLACK = 1
    BLUE = 2
    GREEN = 3
    RED = 4
    BROWN = 5
    MAROON = 5      # alias for BROWN
    PURPLE = 6
    ORANGE = 7
    YELLOW = 8
    LIGHT_GREEN = 9
    LIME = 9        # alias
    TEAL = 10
    CYAN = 10       # alias for TEAL
    LIGHT_CYAN = 11
    LIGHT_BLUE = 12
    ROYAL_BLUE = 12 # alias
    PINK = 13
    LIGHT_PURPLE = 13  # alias for PINK
    FUCHSIA = 13       # alias
    GREY = 14
    GRAY = 14       # alias
    LIGHT_GREY = 15
    LIGHT_GRAY = 15 # alias
    DEFAULT = 99    # reset to default color
