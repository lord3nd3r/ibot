"""Legacy sopel.module compatibility."""
from ibot.sopel_shim.plugin import *  # noqa
from ibot.sopel_shim.plugin import (
    command, commands, rule, event, interval,
    nickname_command, nickname_commands,
    action_command, action_commands,
    require_admin, require_owner, require_chanmsg,
    require_privmsg, require_privilege, require_bot_privilege,
    require_account,
    rate, thread, priority, unblockable,
    allow_bots, echo, example, output_prefix,
    url, url_lazy, find, search, ctcp, intent,
    VOICE, HALFOP, OP, ADMIN, OWNER, OPER, NOLIMIT,
)
