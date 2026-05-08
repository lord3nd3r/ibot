"""Tests for ibot.config module."""

import pytest
from ibot.config import load_config, create_default_config
import os
import tempfile


def test_load_config(temp_config_file):
    """Test loading a config file."""
    config = load_config(temp_config_file)
    assert config.core.nick == 'testbot'
    assert config.core.host == 'irc.example.com'
    assert config.core.port == 6667
    assert config.core.owner == 'testowner'
    assert '#testchannel' in config.core.channels


def test_load_nonexistent_config():
    """Test loading a non-existent config file raises error."""
    with pytest.raises(FileNotFoundError):
        load_config('/nonexistent/path/config.cfg')


def test_create_default_config():
    """Test creating a default config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cfg', delete=False) as f:
        config_path = f.name
    
    # Remove the file so we can test creation
    os.unlink(config_path)
    
    try:
        create_default_config(config_path)
        assert os.path.exists(config_path)
        
        # Verify it's valid
        config = load_config(config_path)
        assert config.core.nick is not None
        assert config.core.host is not None
    finally:
        try:
            os.unlink(config_path)
        except FileNotFoundError:
            pass


def test_config_channels_list(temp_config_file):
    """Test that channels config returns a list."""
    config = load_config(temp_config_file)
    assert isinstance(config.core.channels, list)
    assert len(config.core.channels) > 0
