"""Sopel compatibility shim for ibot.

This package provides a drop-in replacement for the `sopel` package,
allowing Sopel plugins to be loaded and executed by ibot without
modification.
"""

from ibot.sopel_shim import plugin
from ibot.sopel_shim import module
from ibot.sopel_shim import tools
from ibot.sopel_shim import formatting
from ibot.sopel_shim import trigger as trigger_mod
from ibot.sopel_shim import db as db_mod
from ibot.sopel_shim import bot as bot_mod
from ibot.sopel_shim import config as config_mod
from ibot.sopel_shim import privileges as privileges_mod
