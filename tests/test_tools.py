"""Tests for ibot.sopel_shim.tools module."""

import pytest
from ibot.sopel_shim.tools import (
    Identifier, SopelMemory, SopelIdentifierMemory,
    get_hostmask_regex
)


class TestIdentifier:
    """Tests for Identifier class."""
    
    def test_case_insensitive_equality(self):
        """Test that identifiers are case-insensitive."""
        assert Identifier('Nick') == Identifier('nick')
        assert Identifier('NICK') == Identifier('nick')
        assert Identifier('NiCk') == 'nick'
    
    def test_irc_case_folding(self):
        """Test IRC-specific case folding rules."""
        # IRC rules: [ = {, ] = }, \ = |, ^ = ~
        assert Identifier('[test]') == Identifier('{test}')
        assert Identifier('\\pipe\\') == Identifier('|pipe|')
        assert Identifier('^caret^') == Identifier('~caret~')
    
    def test_hash_consistency(self):
        """Test that equal identifiers have equal hashes."""
        id1 = Identifier('TestNick')
        id2 = Identifier('testnick')
        assert hash(id1) == hash(id2)
    
    def test_is_nick(self):
        """Test nick vs channel detection."""
        assert Identifier('alice').is_nick()
        assert not Identifier('#channel').is_nick()
        assert not Identifier('&channel').is_nick()
        assert not Identifier('+modeless').is_nick()


class TestSopelMemory:
    """Tests for SopelMemory class."""
    
    def test_thread_safe_operations(self):
        """Test basic thread-safe dict operations."""
        mem = SopelMemory()
        mem['key'] = 'value'
        assert mem['key'] == 'value'
        assert 'key' in mem
        assert mem.get('nonexistent', 'default') == 'default'
    
    def test_setdefault(self):
        """Test setdefault operation."""
        mem = SopelMemory()
        result = mem.setdefault('key', [])
        assert result == []
        result.append('item')
        assert mem['key'] == ['item']
    
    def test_pop(self):
        """Test pop operation."""
        mem = SopelMemory()
        mem['key'] = 'value'
        assert mem.pop('key') == 'value'
        assert 'key' not in mem
        assert mem.pop('nonexistent', 'default') == 'default'


class TestSopelIdentifierMemory:
    """Tests for SopelIdentifierMemory class."""
    
    def test_case_insensitive_keys(self):
        """Test that keys are case-insensitive."""
        mem = SopelIdentifierMemory()
        mem['Nick'] = 'Alice'
        assert mem['nick'] == 'Alice'
        assert mem['NICK'] == 'Alice'
        assert 'NiCk' in mem
    
    def test_irc_case_folding_keys(self):
        """Test IRC case folding in keys."""
        mem = SopelIdentifierMemory()
        mem['[test]'] = 'value'
        assert mem['{test}'] == 'value'


class TestHostmaskRegex:
    """Tests for hostmask regex generation."""
    
    def test_exact_match(self):
        """Test exact hostmask matching."""
        regex = get_hostmask_regex('alice!user@host.com')
        assert regex.match('alice!user@host.com')
        assert not regex.match('bob!user@host.com')
    
    def test_wildcard_match(self):
        """Test wildcard hostmask matching."""
        regex = get_hostmask_regex('*!*@*.example.com')
        assert regex.match('alice!user@subdomain.example.com')
        assert regex.match('bob!admin@host.example.com')
        assert not regex.match('alice!user@other.com')
    
    def test_partial_wildcard(self):
        """Test partial wildcard matching."""
        regex = get_hostmask_regex('alice!*@*')
        assert regex.match('alice!user@host.com')
        assert regex.match('alice!admin@example.org')
        assert not regex.match('bob!user@host.com')
