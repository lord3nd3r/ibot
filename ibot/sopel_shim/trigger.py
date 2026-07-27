"""Sopel-compatible Trigger and PreTrigger classes.

These represent incoming IRC messages and provide context to plugin callables.
"""

from datetime import datetime, timezone
import re

from ibot.sopel_shim.tools import Identifier
from ibot.sopel_shim.tools import web
from ibot.sopel_shim import formatting


COMMANDS_WITH_CONTEXT = frozenset({
    'INVITE', 'JOIN', 'KICK', 'MODE',
    'NOTICE', 'PART', 'PRIVMSG', 'TOPIC',
})

# IRCv3 tag value escapes (message-tags)
_TAG_UNESCAPE = {
    ':': ';',
    's': ' ',
    '\\': '\\',
    'r': '\r',
    'n': '\n',
}


def unescape_tag_value(value):
    """Decode an IRCv3 tag value (\\: \\s \\\\ \\r \\n)."""
    if value is None:
        return None
    out = []
    i = 0
    while i < len(value):
        if value[i] == '\\' and i + 1 < len(value):
            nxt = value[i + 1]
            out.append(_TAG_UNESCAPE.get(nxt, nxt))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return ''.join(out)


class PreTrigger:
    """A parsed raw IRC message, before rule matching.

    Handles parsing of the IRC protocol line into components:
    nick, user, host, event, args, text, tags, etc.
    """

    component_regex = re.compile(r'([^!]*)!?([^@]*)@?(.*)')
    ctcp_regex = re.compile('\x01(\\S+) ?(.*)\x01')

    def __init__(self, own_nick, line, url_schemes=None):
        self.make_identifier = Identifier
        line = line.strip('\r\n')
        self.line = line
        self.urls = tuple()
        self.plain = ''
        self.ctcp = None
        self.status_prefix = None

        # Parse IRCv3 message tags (with unescaping)
        self.tags = {}
        if line.startswith('@'):
            tagstring, line = line.split(' ', 1)
            for raw_tag in tagstring[1:].split(';'):
                if not raw_tag:
                    continue
                if '=' in raw_tag:
                    key, raw_val = raw_tag.split('=', 1)
                    self.tags[key] = unescape_tag_value(raw_val)
                else:
                    self.tags[raw_tag] = None

        # Timestamp
        self.time = datetime.now(timezone.utc)
        if 'time' in self.tags:
            tag_time = self.tags['time'] or ''
            try:
                self.time = datetime.strptime(
                    tag_time, "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                # Also accept seconds-only form
                try:
                    self.time = datetime.strptime(
                        tag_time, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        # Parse hostmask
        self.hostmask = None
        if line.startswith(':'):
            self.hostmask, line = line[1:].split(' ', 1)

        # Parse args and text
        if ' :' in line:
            argstr, self.text = line.split(' :', 1)
            self.args = argstr.split(' ')
            self.args.append(self.text)
        else:
            self.args = line.split(' ')
            self.text = self.args[-1] if len(self.args) > 1 else ''

        self.event = self.args[0]
        self.args = self.args[1:]

        # Parse nick, user, host from hostmask
        components = PreTrigger.component_regex.match(self.hostmask or '')
        nick, self.user, self.host = components.groups()
        self.nick = Identifier(nick)

        # Determine sender (channel or PM partner)
        target = None
        if self.args and self.event in COMMANDS_WITH_CONTEXT:
            raw_target = self.args[0]
            target = Identifier(raw_target)
            # If the target is our own nick, sender is the person messaging us
            if target.lower() == Identifier(own_nick).lower():
                target = self.nick

        self.sender = target

        # Parse CTCP
        if self.event in ('PRIVMSG', 'NOTICE') and self.args:
            ctcp_match = PreTrigger.ctcp_regex.match(self.args[-1])
            if ctcp_match is not None:
                ctcp_cmd, message = ctcp_match.groups()
                self.ctcp = ctcp_cmd
                self.args[-1] = message or ''

            # Search for URLs
            self.urls = tuple(web.search_urls(self.args[-1]))

        # Handle extended-join account info: JOIN #chan account :realname
        # (args after event strip: [channel, account, realname] or [channel])
        if self.event == 'JOIN' and len(self.args) >= 2:
            # extended-join: channel, account, realname
            account = self.args[1]
            if account and account != '*':
                self.tags.setdefault('account', account)

        # Plain text (stripped of formatting)
        if self.args:
            self.plain = formatting.plain(self.args[-1])


class Trigger(str):
    """A matched IRC message passed to plugin callables.

    Subclasses str so `trigger` itself is the message text.
    Provides all the context attributes plugins expect:
    nick, sender, match, group, admin, owner, etc.
    """

    sender = property(lambda self: self._pretrigger.sender)
    status_prefix = property(lambda self: self._pretrigger.status_prefix)
    time = property(lambda self: self._pretrigger.time)
    raw = property(lambda self: self._pretrigger.line)
    hostmask = property(lambda self: self._pretrigger.hostmask)
    user = property(lambda self: self._pretrigger.user)
    nick = property(lambda self: self._pretrigger.nick)
    host = property(lambda self: self._pretrigger.host)
    event = property(lambda self: self._pretrigger.event)
    ctcp = property(lambda self: self._pretrigger.ctcp)
    match = property(lambda self: self._match)
    group = property(lambda self: self._match.group)
    groups = property(lambda self: self._match.groups)
    groupdict = property(lambda self: self._match.groupdict)
    args = property(lambda self: self._pretrigger.args)
    urls = property(lambda self: self._pretrigger.urls)
    plain = property(lambda self: self._pretrigger.plain)
    tags = property(lambda self: self._pretrigger.tags)
    admin = property(lambda self: self._admin)
    owner = property(lambda self: self._owner)
    account = property(lambda self: self.tags.get('account') or self._account)

    @property
    def is_privmsg(self):
        return self._pretrigger.sender and self._pretrigger.sender.is_nick()

    @property
    def text(self):
        return self._pretrigger.text

    def __new__(cls, settings, message, match, account=None):
        return str.__new__(cls, message.args[-1] if message.args else '')

    def __init__(self, settings, message, match, account=None):
        self._account = account
        self._pretrigger = message
        self._match = match

        # Determine owner/admin status
        owner_nick = settings.core.owner if settings else ''
        owner_account = settings.core.owner_account if settings else ''
        admin_list = settings.core.admins if settings else []
        admin_accounts = settings.core.admin_accounts if settings else []

        if owner_account and self.account:
            self._owner = (owner_account == self.account)
        elif owner_nick:
            self._owner = (
                str(self.nick).lower() == owner_nick.lower()
            )
        else:
            self._owner = False

        self._admin = (
            self._owner
            or (self.account and self.account in admin_accounts)
            or any(
                str(self.nick).lower() == a.lower()
                for a in admin_list
            )
        )
