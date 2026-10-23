"""Sopel-compatible bot wrapper.

The SopelWrapper is the `bot` object that plugin callables receive.
It wraps the core IRC client and provides convenient methods like
say(), reply(), notice(), etc.
"""

import logging
import re

LOGGER = logging.getLogger(__name__)

# Conservative per-PRIVMSG body limit (bytes), matching the core bot.
_MAX_MESSAGE_BYTES = 400

_LINE_BREAK_RE = re.compile(r'\r\n|\r|\n')


def _lines(text):
    """Split text on CR/LF; drop empty lines (single-line text is kept)."""
    text = str(text)
    if '\r' not in text and '\n' not in text:
        return [text]
    return [ln for ln in _LINE_BREAK_RE.split(text) if ln.strip()]


def _one_line(text):
    """Collapse CR/LF/NUL into spaces (for single-line fields)."""
    return re.sub(r'[\r\n\0]+', ' ', str(text))


class SopelWrapper:
    """The bot object passed to plugin callables.

    Wraps the core bot instance and provides a default destination
    (from the trigger's sender) for all messaging methods.
    """

    def __init__(self, bot, trigger):
        self._bot = bot
        self._trigger = trigger
        self._default_destination = (
            str(trigger.sender) if trigger and trigger.sender else None
        )
        self._output_prefix = ''

    def _prefix(self, text):
        if self._output_prefix:
            return self._output_prefix + text
        return text

    @staticmethod
    def _split_chunks(text, max_bytes=_MAX_MESSAGE_BYTES):
        """Split text into byte-safe chunks, also honouring embedded newlines.

        Yields non-empty chunks in order. Newlines force a chunk boundary;
        long lines are further split on character boundaries so UTF-8 is never
        cut mid-codepoint.
        """
        # Prefer the core bot's byte-aware splitter when available.
        splitter = None
        # Imported lazily to avoid circular imports at module load.
        try:
            from ibot.bot import IRCBot
            splitter = IRCBot._split_message
        except Exception:
            splitter = None

        for line in _LINE_BREAK_RE.split(str(text)):
            if not line:
                continue
            if splitter is not None:
                for chunk in splitter(line, max_bytes):
                    if chunk:
                        yield chunk
            else:
                # Fallback byte-aware split
                encoded = line.encode('utf-8')
                if len(encoded) <= max_bytes:
                    yield line
                    continue
                chunk = []
                chunk_bytes = 0
                for ch in line:
                    ch_bytes = len(ch.encode('utf-8'))
                    if chunk_bytes + ch_bytes > max_bytes and chunk:
                        yield ''.join(chunk)
                        chunk = []
                        chunk_bytes = 0
                    chunk.append(ch)
                    chunk_bytes += ch_bytes
                if chunk:
                    yield ''.join(chunk)

    def say(self, text, destination=None, max_messages=None,
            truncation=None, trailing=None):
        """Send a PRIVMSG to the destination (defaults to trigger's sender).

        ``max_messages`` caps the number of PRIVMSG lines actually sent
        (counting both newline splits *and* byte-length splits). Extra content
        is dropped; when truncation occurs the last sent message may be
        modified by ``truncation`` / ``trailing`` (Sopel semantics).
        """
        dest = destination or self._default_destination
        if not dest:
            LOGGER.warning("No destination for say()")
            return

        text = self._prefix(text)
        # Sopel default is 1; keep that for plugin compatibility.
        if max_messages is None:
            max_messages = 1
        if max_messages < 1:
            return

        chunks = list(self._split_chunks(text))
        if not chunks:
            return

        truncated = len(chunks) > max_messages
        to_send = chunks[:max_messages]

        if truncated:
            last = to_send[-1]
            # Append optional truncation marker / trailing text.
            suffix = ''
            if truncation:
                suffix += str(truncation)
            if trailing:
                suffix += str(trailing)
            if suffix:
                # Fit suffix within the byte budget of the last message.
                max_body = _MAX_MESSAGE_BYTES - len(suffix.encode('utf-8'))
                if max_body < 0:
                    max_body = 0
                encoded = last.encode('utf-8')
                if len(encoded) > max_body:
                    # Trim on character boundaries.
                    trimmed = []
                    nbytes = 0
                    for ch in last:
                        cb = len(ch.encode('utf-8'))
                        if nbytes + cb > max_body:
                            break
                        trimmed.append(ch)
                        nbytes += cb
                    last = ''.join(trimmed)
                to_send[-1] = last + suffix

        for chunk in to_send:
            # Use send_raw-style single-chunk send to avoid double-splitting.
            if hasattr(self._bot, 'send_privmsg_chunk'):
                self._bot.send_privmsg_chunk(dest, chunk)
            else:
                self._bot.send_privmsg(dest, chunk)

    def reply(self, text, destination=None, reply_to=None, notice=False):
        """Reply to the user who triggered the command."""
        dest = destination or self._default_destination
        nick = reply_to or (
            str(self._trigger.nick) if self._trigger is not None else ''
        )
        text = self._prefix(text)
        msg = f"{nick}: {text}" if nick else text
        if notice:
            if dest:
                for line in _lines(msg):
                    self._bot.send_notice(line, dest)
        elif dest:
            self.say(msg, destination=dest)

    def notice(self, text, destination=None):
        """Send a NOTICE."""
        dest = destination or self._default_destination
        if dest:
            text = self._prefix(text)
            for line in _lines(text):
                self._bot.send_notice(line, dest)

    def action(self, text, destination=None):
        """Send a CTCP ACTION (/me)."""
        dest = destination or self._default_destination
        if dest:
            text = self._prefix(text)
            for line in _lines(text):
                if hasattr(self._bot, 'send_privmsg_chunk'):
                    self._bot.send_privmsg_chunk(dest, f'\x01ACTION {line}\x01')
                else:
                    self._bot.send_privmsg(dest, f'\x01ACTION {line}\x01')

    def kick(self, nick, channel=None, text=None):
        """Kick a user from a channel."""
        chan = channel or self._default_destination
        if chan:
            chan, nick = _one_line(chan), _one_line(nick)
            if text:
                self._bot.send_raw(f'KICK {chan} {nick} :{_one_line(text)}')
            else:
                self._bot.send_raw(f'KICK {chan} {nick}')

    def join(self, channel, password=None):
        """Join a channel."""
        channel = _one_line(channel)
        if password:
            self._bot.send_raw(f'JOIN {channel} {_one_line(password)}')
        else:
            self._bot.send_raw(f'JOIN {channel}')

    def part(self, channel, msg=None):
        """Part/leave a channel."""
        channel = _one_line(channel)
        if msg:
            self._bot.send_raw(f'PART {channel} :{_one_line(msg)}')
        else:
            self._bot.send_raw(f'PART {channel}')

    def quit(self, message=None):
        """Quit the IRC server and shut the bot down (no reconnect)."""
        message = _one_line(message) if message else None
        if hasattr(self._bot, 'quit'):
            self._bot.quit(message)
        elif message:
            self._bot.send_raw(f'QUIT :{message}')
        else:
            self._bot.send_raw('QUIT')

    def restart(self, message=None):
        """Quit and re-launch the bot process with the same config."""
        message = _one_line(message) if message else 'Restarting'
        if hasattr(self._bot, 'restart'):
            self._bot.restart(message)
        else:
            self.quit(message)

    def reload_plugin(self, name):
        """Reload one plugin by name. Raises an exception on failure."""
        from ibot.loader import reload_plugin_live
        reload_plugin_live(self._bot, name)

    def write(self, args, text=None):
        """Send a raw IRC command."""
        if isinstance(args, (list, tuple)):
            cmd = ' '.join(str(a) for a in args)
        else:
            cmd = str(args)
        cmd = _one_line(cmd)
        if text:
            self._bot.send_raw(f'{cmd} :{_one_line(text)}')
        else:
            self._bot.send_raw(cmd)

    def msg(self, recipient, text):
        """Send a PRIVMSG (lower-level alias)."""
        self._bot.send_privmsg(str(recipient), str(text))

    # --- Properties proxied from the core bot ---

    def __getattr__(self, name):
        """Fall back to the core bot for public attributes (Sopel behaviour).

        Private/dunder names are not forwarded, so feature probes like
        ``getattr(bot, '_plugins', ...)`` keep behaving as before.
        """
        if name.startswith('_'):
            raise AttributeError(name)
        core = self.__dict__.get('_bot')
        if core is None:
            raise AttributeError(name)
        return getattr(core, name)

    @property
    def nick(self):
        return self._bot.nick

    @property
    def settings(self):
        return self._bot.settings

    @property
    def config(self):
        return self._bot.settings

    @property
    def db(self):
        return self._bot.db

    @property
    def memory(self):
        return self._bot.memory

    @property
    def channels(self):
        return self._bot.channels

    @property
    def users(self):
        return self._bot.users

    def _get_privilege(self, channel, nick):
        """Get a user's privilege level in a channel."""
        return self._bot.get_privilege(channel, nick)

    def has_channel_privilege(self, channel, privilege):
        """Check if the bot has a specific privilege in a channel."""
        return self._bot.get_privilege(channel, self._bot.nick) >= privilege
