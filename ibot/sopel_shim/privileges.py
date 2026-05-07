"""Sopel-compatible privilege/access level constants."""


class AccessLevel:
    """Channel privilege levels, matching Sopel's constants."""
    VOICE = 1
    HALFOP = 2
    OP = 4
    ADMIN = 8
    OWNER = 16
    OPER = 32


# Shortcuts
VOICE = AccessLevel.VOICE
HALFOP = AccessLevel.HALFOP
OP = AccessLevel.OP
ADMIN = AccessLevel.ADMIN
OWNER = AccessLevel.OWNER
OPER = AccessLevel.OPER
