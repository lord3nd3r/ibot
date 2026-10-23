"""Offline tests for the connection/dispatch hardening (no network)."""
import asyncio
import os
import re
import tempfile
import threading
import time

import pytest

from ibot.loader import install_sopel_shim

install_sopel_shim()

from ibot.bot import IRCBot, MAX_LINE_BYTES, MAX_NICK_ATTEMPTS  # noqa: E402
from ibot.config import load_config  # noqa: E402
from ibot.dispatch import HandlerPool  # noqa: E402


class FakeWriter:
    def __init__(self):
        self.data = b''
        self.closed = False

    def write(self, data):
        self.data += data

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    def lines(self):
        return [ln for ln in self.data.decode('utf-8').split('\r\n') if ln]


def _cfg(extra=''):
    fd, path = tempfile.mkstemp(suffix='.cfg')
    with os.fdopen(fd, 'w') as f:
        f.write("[core]\nnick = testbot\nhost = irc.example.com\n"
                "owner = testowner\nchannels = #test\nprefix = \\.\n"
                "db_filename = :memory:\n" + extra)
    return path


@pytest.fixture
def bot():
    path = _cfg()
    try:
        b = IRCBot(load_config(path))
        b._writer = FakeWriter()
        yield b
    finally:
        os.unlink(path)


def _run(coro):
    return asyncio.run(coro)


# --- sanitizer / redaction -------------------------------------------------

def test_clean_line_strips_crlf_nul():
    clean, wire = IRCBot._clean_line('PRIVMSG #a :hi\r\nQUIT :pwned\0x')
    assert '\r' not in clean and '\n' not in clean and '\0' not in clean
    assert wire.endswith(b'\r\n') and wire.count(b'\r\n') == 1


def test_clean_line_truncates_on_char_boundary():
    clean, wire = IRCBot._clean_line('PRIVMSG #a :' + '\u00e9' * 600)
    assert len(wire) - 2 <= MAX_LINE_BYTES
    wire[:-2].decode('utf-8')  # must not raise


def test_send_raw_writes_single_line(bot):
    _run(bot._send_raw('PRIVMSG #a :one\nPRIVMSG #b :two'))
    assert len(bot._writer.lines()) == 1


@pytest.mark.parametrize('line,secret', [
    ('PASS hunter2', 'hunter2'),
    ('AUTHENTICATE dGVzdAB0ZXN0AHNlY3JldA==', 'dGVzdAB0ZXN0AHNlY3JldA=='),
    ('PRIVMSG NickServ :IDENTIFY s3cret', 's3cret'),
    ('PRIVMSG nickserv :GHOST testbot s3cret', 's3cret'),
    ('OPER admin operpw', 'operpw'),
    ('NS IDENTIFY s3cret', 's3cret'),
])
def test_redaction(bot, line, secret):
    assert secret not in bot._sanitize_for_log(line)


def test_redaction_keeps_normal_lines(bot):
    line = 'PRIVMSG #chan :hello IDENTIFY world'
    assert bot._sanitize_for_log(line) == line
    assert bot._sanitize_for_log('AUTHENTICATE PLAIN') == 'AUTHENTICATE PLAIN'


def test_send_privmsg_splits_lines(bot):
    sent = []
    bot.send_raw = sent.append
    bot.send_privmsg('#a', 'one\r\ntwo\nthree')
    assert sent == ['PRIVMSG #a :one', 'PRIVMSG #a :two', 'PRIVMSG #a :three']
    sent.clear()
    bot.send_privmsg('#a', 'plain')
    assert sent == ['PRIVMSG #a :plain']


# --- handler pool ------------------------------------------------------------

def test_pool_runs_jobs_and_is_bounded():
    pool = HandlerPool(max_workers=3, max_queue=100)
    done = []
    lock = threading.Lock()
    gate = threading.Event()

    def job(i):
        def _f():
            gate.wait(2)
            with lock:
                done.append(i)
        return _f

    for i in range(20):
        assert pool.submit(job(i))
    assert pool.stats['workers'] <= 3
    gate.set()
    deadline = time.time() + 5
    while len(done) < 20 and time.time() < deadline:
        time.sleep(0.01)
    assert sorted(done) == list(range(20))
    pool.shutdown()


def test_pool_drops_when_full_and_survives_exceptions():
    pool = HandlerPool(max_workers=1, max_queue=1)
    gate = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        gate.wait(2)

    assert pool.submit(blocker)
    started.wait(2)
    assert pool.submit(lambda: 1 / 0)        # queued (raises later)
    assert pool.submit(lambda: None) is False  # queue full -> dropped
    assert pool.stats['dropped'] == 1
    gate.set()
    ran = threading.Event()
    deadline = time.time() + 5
    while not pool.submit(ran.set) and time.time() < deadline:
        time.sleep(0.01)
    assert ran.wait(5)  # worker survived the ZeroDivisionError
    pool.shutdown()
    assert pool.submit(lambda: None) is False


# --- nick handling -------------------------------------------------------------

def test_433_tries_suffixes_within_nicklen(bot):
    bot._handle_isupport(['testbot', 'NICKLEN=9', 'are supported'])
    tried = []
    for _ in range(5):
        _run(bot._handle_nick_error('433', ['*', bot.nick, 'Nickname is already in use']))
        tried.append(bot.nick)
    assert len(set(tried)) >= 3
    assert all(len(n) <= 9 for n in tried)
    assert all(n.startswith('testb') for n in tried)
    assert bot._writer.lines()[-1] == f'NICK {bot.nick}'


def test_432_sanitizes_nick():
    path = _cfg()
    try:
        b = IRCBot(load_config(path))
        b._writer = FakeWriter()
        b._desired_nick = '9bad.nick!'
        b.nick = b._desired_nick
        _run(b._handle_nick_error('432', ['*', b.nick, 'Erroneous nickname']))
        assert re.fullmatch(r'[A-Za-z\[\]\\`_\^\{\|\}][A-Za-z0-9\[\]\\`_\^\{\|\}\-]*', b.nick)
    finally:
        os.unlink(path)


def test_nick_error_after_registration_keeps_nick(bot):
    bot._registered = True
    _run(bot._handle_nick_error('433', ['testbot', 'other', 'in use']))
    assert bot.nick == 'testbot'
    assert bot._writer.lines() == []


def test_nick_attempts_are_capped(bot):
    closed = []

    async def fake_close():
        closed.append(True)

    bot._close_connection = fake_close
    for _ in range(MAX_NICK_ATTEMPTS + 1):
        _run(bot._handle_nick_error('433', ['*', bot.nick, 'in use']))
    assert closed == [True]


# --- CAP negotiation -------------------------------------------------------------

def _cap(bot, *params):
    _run(bot._handle_cap(list(params)))


def test_cap_ls_multiline_and_intersection(bot):
    _run(bot.register())
    assert bot._writer.lines()[0] == 'CAP LS 302'
    _cap(bot, '*', 'LS', '*', 'multi-prefix sasl=PLAIN,EXTERNAL')
    assert not any(l.startswith('CAP REQ') for l in bot._writer.lines())
    _cap(bot, '*', 'LS', 'account-tag away-notify')
    reqs = [l for l in bot._writer.lines() if l.startswith('CAP REQ')]
    assert len(reqs) == 1
    requested = set(reqs[0].split(':', 1)[1].split())
    assert requested == {'multi-prefix', 'account-tag'}  # sasl not configured
    _cap(bot, '*', 'ACK', 'multi-prefix account-tag')
    assert bot._writer.lines()[-1] == 'CAP END'
    assert bot._enabled_caps == {'multi-prefix', 'account-tag'}


def test_cap_no_common_caps_ends(bot):
    _run(bot.register())
    _cap(bot, '*', 'LS', 'foo bar')
    assert bot._writer.lines()[-1] == 'CAP END'


def test_cap_nak_retries_individually(bot):
    _run(bot.register())
    _cap(bot, '*', 'LS', 'multi-prefix account-tag')
    _cap(bot, '*', 'NAK', 'account-tag multi-prefix')
    reqs = [l for l in bot._writer.lines() if l.startswith('CAP REQ')]
    assert len(reqs) == 3
    _cap(bot, '*', 'ACK', 'multi-prefix')
    assert bot._writer.lines()[-1] != 'CAP END'
    _cap(bot, '*', 'NAK', 'account-tag')
    assert bot._writer.lines()[-1] == 'CAP END'
    assert bot._enabled_caps == {'multi-prefix'}


def test_cap_sasl_waits_for_authentication():
    path = _cfg('auth_method = sasl\nauth_password = pw\n')
    try:
        b = IRCBot(load_config(path))
        b._writer = FakeWriter()
        _run(b.register())
        _cap(b, '*', 'LS', 'sasl multi-prefix')
        _cap(b, '*', 'ACK', 'multi-prefix sasl')
        assert b._writer.lines()[-1] == 'AUTHENTICATE PLAIN'
        assert 'CAP END' not in b._writer.lines()
        _run(b._handle_authenticate(['+']))
        assert b._writer.lines()[-1].startswith('AUTHENTICATE ')
    finally:
        os.unlink(path)


# --- ISUPPORT ---------------------------------------------------------------------

def test_isupport_prefix_and_chanmodes(bot):
    bot._handle_isupport(['testbot', 'PREFIX=(Yqaohv)!~&@%+',
                          'CHANMODES=beI,kfL,lj,psmntirRcOAQKVCuzNSMTGZ',
                          'NICKLEN=16', 'are supported by this server'])
    assert bot._prefix_modes['Y'] == '!'
    assert bot._chanmodes[1] == 'kfL'
    assert bot._nicklen == 16


# --- web.get safety ---------------------------------------------------------------

def test_web_check_url():
    from ibot.sopel_shim.tools import web
    for bad in ('file:///etc/passwd', 'ftp://example.com/', 'http://127.0.0.1/',
                'http://10.1.2.3/', 'http://[::1]/', 'http://169.254.169.254/',
                'http://localhost/'):
        with pytest.raises(web.UnsafeURLError):
            web.check_url(bad)
    web.check_url('https://93.184.215.14/')  # public literal, no DNS needed
    web.check_url('http://127.0.0.1/', allow_private=True)


# --- DB -----------------------------------------------------------------------------

def test_db_nick_ids_threaded_and_merge():
    from ibot.sopel_shim.db import SopelDB
    with tempfile.TemporaryDirectory() as d:
        db = SopelDB(db_filename=os.path.join(d, 't.db'))
        ids = []
        lock = threading.Lock()

        def worker():
            v = db.get_nick_id('SameNick', create=True)
            with lock:
                ids.append(v)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(ids)) == 1

        db.set_nick_value('alice', 'a', 1)
        db.set_nick_value('bob', 'a', 2)
        db.set_nick_value('bob', 'b', 3)
        db.merge_nick_groups('alice', 'bob')
        assert db.get_nick_value('alice', 'a') == 1
        assert db.get_nick_value('alice', 'b') == 3
        assert db.get_nick_id('alice') == db.get_nick_id('bob')
        # merging a group with itself must not wipe it
        db.merge_nick_groups('alice', 'bob')
        assert db.get_nick_value('alice', 'b') == 3

        with db.engine.connect() as conn:
            from sqlalchemy import text
            assert conn.execute(text('PRAGMA journal_mode')).scalar().lower() == 'wal'
        db.close()


# --- dispatcher compat --------------------------------------------------------------

def _disp(extra=''):
    from ibot.dispatch import Dispatcher
    from tests.test_dispatch import FakeBot
    path = _cfg(extra)
    settings = load_config(path)
    os.unlink(path)
    return Dispatcher(FakeBot(), settings)


def _plugin(name, *funcs, kind='rules'):
    from ibot.loader import PluginInfo
    p = PluginInfo(name, None)
    getattr(p, kind).extend(funcs)
    return p


def test_rules_ignore_case_and_nickname_substitution():
    from ibot.sopel_shim.plugin import rule, thread
    hits = []

    @thread(False)
    @rule(r'$nickname[:,]? hello')
    def h(bot, trigger):
        hits.append(trigger.group(0))

    d = _disp()
    d.register_plugins([_plugin('p', h)])
    d.dispatch(':bob!u@h PRIVMSG #chan :TESTBOT: HELLO')
    assert len(hits) == 1
    # nick change: patterns follow the new nick
    d.bot.nick = 'newbot'
    d.refresh_nick_patterns()
    d.dispatch(':bob!u@h PRIVMSG #chan :newbot: hello')
    assert len(hits) == 2


def test_channel_disable_plugins():
    from ibot.sopel_shim.plugin import command, thread
    hits = []

    @thread(False)
    @command('ping')
    def h(bot, trigger):
        hits.append(trigger.sender)

    d = _disp('\n[#quiet]\ndisable_plugins = p\n')
    d.register_plugins([_plugin('p', h, kind='commands')])
    d.dispatch(':bob!u@h PRIVMSG #quiet :.ping')
    d.dispatch(':bob!u@h PRIVMSG #loud :.ping')
    assert hits == ['#loud']


def test_handler_exception_does_not_break_dispatch():
    from ibot.sopel_shim.plugin import command, thread
    hits = []

    @thread(False)
    @command('boom')
    def bad(bot, trigger):
        raise RuntimeError('x')

    @thread(False)
    @command('ok')
    def good(bot, trigger):
        hits.append(1)

    d = _disp()
    d.register_plugins([_plugin('p', bad, good, kind='commands')])
    d.dispatch(':bob!u@h PRIVMSG #c :.boom')
    d.dispatch(':bob!u@h PRIVMSG #c :.ok')
    assert hits == [1]
