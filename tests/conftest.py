"""Pytest configuration and fixtures for ibot tests."""

import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cfg', delete=False) as f:
        f.write("""[core]
nick = testbot
host = irc.example.com
port = 6667
use_ssl = false
verify_ssl = false
owner = testowner
channels = #testchannel
prefix = \\.
db_filename = :memory:
""")
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    try:
        os.unlink(config_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def temp_plugin_dir():
    """Create a temporary plugin directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
