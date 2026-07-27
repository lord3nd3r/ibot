"""Sopel-compatible ``sopel.tools.target`` module.

Sopel exposes its live ``User`` and ``Channel`` state objects here. ibot's
core tracks channel/user state with the classes defined in :mod:`ibot.bot`, so
we re-export those same classes. Because the bot populates ``bot.channels`` and
``bot.users`` with these instances, ``isinstance(obj, target.Channel)`` checks
in plugins work against the live objects.
"""

from ibot.bot import User, Channel

__all__ = ['User', 'Channel']
