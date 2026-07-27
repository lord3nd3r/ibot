"""Sopel-compatible database module.

Uses SQLAlchemy with the EXACT same schema as Sopel so existing databases
work without migration:
  - nick_ids (nick_id INTEGER PRIMARY KEY)
  - nicknames (nick_id FK, slug TEXT, canonical TEXT)
  - nick_values (nick_id FK, key TEXT, value TEXT)
  - channel_values (channel TEXT, key TEXT, value TEXT)
  - plugin_values (plugin TEXT, key TEXT, value TEXT)
"""

import json
import logging
import os
import typing

from sqlalchemy import Column, create_engine, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker
from sqlalchemy.sql import select, delete, update, func

from ibot.sopel_shim.tools import Identifier

LOGGER = logging.getLogger(__name__)

BASE = declarative_base()
MYSQL_TABLE_ARGS = {
    'mysql_engine': 'InnoDB',
    'mysql_charset': 'utf8mb4',
    'mysql_collate': 'utf8mb4_unicode_ci',
}


class NickIDs(BASE):
    """Nick IDs table — matches Sopel's schema exactly."""
    __tablename__ = 'nick_ids'
    nick_id = Column(Integer, primary_key=True)


class Nicknames(BASE):
    """Nicknames table — maps nicks to nick_ids."""
    __tablename__ = 'nicknames'
    __table_args__ = MYSQL_TABLE_ARGS
    nick_id = Column(Integer, ForeignKey('nick_ids.nick_id'), primary_key=True)
    slug = Column(String(255), primary_key=True)
    canonical = Column(String(255))


class NickValues(BASE):
    """Nick values key-value store."""
    __tablename__ = 'nick_values'
    __table_args__ = MYSQL_TABLE_ARGS
    nick_id = Column(Integer, ForeignKey('nick_ids.nick_id'), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(String(255))


class ChannelValues(BASE):
    """Channel values key-value store."""
    __tablename__ = 'channel_values'
    __table_args__ = MYSQL_TABLE_ARGS
    channel = Column(String(255), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(String(255))


class PluginValues(BASE):
    """Plugin values key-value store."""
    __tablename__ = 'plugin_values'
    __table_args__ = MYSQL_TABLE_ARGS
    plugin = Column(String(255), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(String(255))


def _deserialize(value):
    """Deserialize a JSON value from the database."""
    if value is None:
        return None
    value = str(value)
    try:
        value = json.loads(value)
    except (ValueError, json.JSONDecodeError):
        pass
    return value


class SopelDB:
    """Sopel-compatible database interface.

    Uses SQLAlchemy with the same schema as Sopel, so existing databases
    (SQLite, MySQL, PostgreSQL) work without any migration.
    """

    def __init__(self, config=None, db_filename=None,
                 identifier_factory=Identifier):
        self.make_identifier = identifier_factory

        if db_filename:
            db_path = os.path.expanduser(db_filename)
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            self.url = f'sqlite:///{db_path}'
            self.type = 'sqlite'
        elif config:
            # Check for db_url first (Sopel 8+ style)
            db_url = getattr(config.core, 'db_url', None)
            if db_url:
                self.url = db_url
                self.type = db_url.split('://')[0].split('+')[0]
            else:
                db_type = getattr(config.core, 'db_type', 'sqlite') or 'sqlite'
                self.type = db_type

                if db_type == 'sqlite':
                    path = config.core.db_filename
                    if not path:
                        homedir = getattr(config, 'homedir', '.')
                        basename = getattr(config, 'basename', 'ibot')
                        path = os.path.join(homedir, basename + '.db')
                    path = os.path.expanduser(path)
                    if not os.path.isabs(path):
                        homedir = getattr(config, 'homedir', '.')
                        path = os.path.normpath(os.path.join(homedir, path))
                    self.url = f'sqlite:///{path}'
                else:
                    # Build URL for non-SQLite databases
                    db_user = getattr(config.core, 'db_user', '') or ''
                    db_pass = getattr(config.core, 'db_pass', '') or ''
                    db_host = getattr(config.core, 'db_host', '') or 'localhost'
                    db_port = getattr(config.core, 'db_port', '') or ''
                    db_name = getattr(config.core, 'db_name', '') or ''

                    driver_map = {
                        'mysql': 'mysql',
                        'postgres': 'postgresql',
                        'postgresql': 'postgresql',
                        'oracle': 'oracle',
                        'mssql': 'mssql+pymssql',
                    }
                    driver = getattr(config.core, 'db_driver', '') or driver_map.get(db_type, db_type)

                    if db_port:
                        host_part = f'{db_host}:{db_port}'
                    else:
                        host_part = db_host

                    if db_user and db_pass:
                        auth_part = f'{db_user}:{db_pass}@'
                    elif db_user:
                        auth_part = f'{db_user}@'
                    else:
                        auth_part = ''

                    self.url = f'{driver}://{auth_part}{host_part}/{db_name}'
        else:
            self.url = 'sqlite:///ibot.db'
            self.type = 'sqlite'

        self.engine = create_engine(self.url, pool_recycle=3600)

        # Create tables if they don't exist
        BASE.metadata.create_all(self.engine)

        self.ssession = scoped_session(
            sessionmaker(bind=self.engine))

    def connect(self):
        """Get a raw database connection (legacy compatibility)."""
        return self.engine.raw_connection()

    def session(self):
        """Get a SQLAlchemy session."""
        return self.ssession()

    def get_uri(self):
        """Return the database connection URL."""
        return self.url

    # --- Nick ID Management ---

    def get_nick_id(self, nick, create=False):
        """Return the internal ID for a given nick.

        Uses Sopel's nick_ids + nicknames indirection tables.
        """
        slug = self.make_identifier(nick).lower()
        with self.session() as session:
            nickname = session.execute(
                select(Nicknames).where(Nicknames.slug == slug)
            ).scalar_one_or_none()

            if nickname is None:
                if not create:
                    raise ValueError(f'No ID exists for nick: {nick}')
                # Create a new nick_id
                nick_id = NickIDs()
                session.add(nick_id)
                session.commit()

                # Create nickname entry
                nickname = Nicknames(
                    nick_id=nick_id.nick_id,
                    slug=slug,
                    canonical=str(nick),
                )
                session.add(nickname)
                session.commit()
            return nickname.nick_id

    def alias_nick(self, nick, alias):
        """Create an alias for a nick."""
        slug = self.make_identifier(alias).lower()
        nick_id = self.get_nick_id(nick, create=True)
        with self.session() as session:
            existing = session.execute(
                select(Nicknames).where(Nicknames.slug == slug)
            ).scalar_one_or_none()
            if existing:
                raise ValueError('Alias already exists.')
            nickname = Nicknames(
                nick_id=nick_id, slug=slug, canonical=str(alias))
            session.add(nickname)
            session.commit()

    def unalias_nick(self, alias):
        """Remove an alias."""
        slug = self.make_identifier(alias).lower()
        nick_id = self.get_nick_id(alias)
        with self.session() as session:
            count = session.scalar(
                select(func.count()).select_from(Nicknames)
                .where(Nicknames.nick_id == nick_id)
            )
            if count <= 1:
                raise ValueError('Given alias is the only entry in its group.')
            session.execute(
                delete(Nicknames).where(Nicknames.slug == slug)
            )
            session.commit()

    def merge_nick_groups(self, first_nick, second_nick):
        """Merge two nick groups."""
        first_id = self.get_nick_id(first_nick, create=True)
        second_id = self.get_nick_id(second_nick, create=True)
        with self.session() as session:
            results = session.execute(
                select(NickValues).where(NickValues.nick_id == second_id)
            ).scalars()
            for row in results:
                first_res = session.execute(
                    select(NickValues)
                    .where(NickValues.nick_id == first_id)
                    .where(NickValues.key == row.key)
                ).scalar_one_or_none()
                if not first_res:
                    self.set_nick_value(
                        first_nick, row.key, _deserialize(row.value))
            session.execute(
                delete(NickValues).where(NickValues.nick_id == second_id))
            session.execute(
                update(Nicknames)
                .where(Nicknames.nick_id == second_id)
                .values(nick_id=first_id))
            session.commit()

    def forget_nick_group(self, nick):
        """Remove a nick, all aliases, and all stored values."""
        nick_id = self.get_nick_id(nick)
        with self.session() as session:
            session.execute(
                delete(Nicknames).where(Nicknames.nick_id == nick_id))
            session.execute(
                delete(NickValues).where(NickValues.nick_id == nick_id))
            session.commit()

    # --- Nick Values ---

    def set_nick_value(self, nick, key, value):
        """Set a value for a nick."""
        value = json.dumps(value, ensure_ascii=False)
        nick_id = self.get_nick_id(nick, create=True)
        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(NickValues.nick_id == nick_id)
                .where(NickValues.key == key)
            ).scalar_one_or_none()
            if result:
                result.value = value
                session.commit()
            else:
                session.add(NickValues(
                    nick_id=nick_id, key=key, value=value))
                session.commit()

    def get_nick_value(self, nick, key, default=None):
        """Get a value for a nick."""
        slug = self.make_identifier(nick).lower()
        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(Nicknames.nick_id == NickValues.nick_id)
                .where(Nicknames.slug == slug)
                .where(NickValues.key == key)
            ).scalar_one_or_none()
            if result is not None:
                return _deserialize(result.value)
            return default

    def delete_nick_value(self, nick, key):
        """Delete a value for a nick."""
        try:
            nick_id = self.get_nick_id(nick)
        except ValueError:
            return
        with self.session() as session:
            result = session.execute(
                select(NickValues)
                .where(NickValues.nick_id == nick_id)
                .where(NickValues.key == key)
            ).scalar_one_or_none()
            if result:
                session.delete(result)
                session.commit()

    # --- Channel Values ---

    def get_channel_slug(self, channel):
        """Get the normalized channel name."""
        return self.make_identifier(channel).lower()

    def set_channel_value(self, channel, key, value):
        """Set a value for a channel."""
        channel = self.get_channel_slug(channel)
        value = json.dumps(value, ensure_ascii=False)
        with self.session() as session:
            result = session.execute(
                select(ChannelValues)
                .where(ChannelValues.channel == channel)
                .where(ChannelValues.key == key)
            ).scalar_one_or_none()
            if result:
                result.value = value
                session.commit()
            else:
                session.add(ChannelValues(
                    channel=channel, key=key, value=value))
                session.commit()

    def get_channel_value(self, channel, key, default=None):
        """Get a value for a channel."""
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            result = session.execute(
                select(ChannelValues)
                .where(ChannelValues.channel == channel)
                .where(ChannelValues.key == key)
            ).scalar_one_or_none()
            if result is not None:
                return _deserialize(result.value)
            return default

    def delete_channel_value(self, channel, key):
        """Delete a value for a channel."""
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            session.execute(
                delete(ChannelValues)
                .where(ChannelValues.channel == channel)
                .where(ChannelValues.key == key))
            session.commit()

    def forget_channel(self, channel):
        """Remove all stored values for a channel."""
        channel = self.get_channel_slug(channel)
        with self.session() as session:
            session.execute(
                delete(ChannelValues)
                .where(ChannelValues.channel == channel))
            session.commit()

    # --- Plugin Values ---

    def set_plugin_value(self, plugin, key, value):
        """Set a value for a plugin."""
        plugin = plugin.lower()
        value = json.dumps(value, ensure_ascii=False)
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()
            if result:
                result.value = value
                session.commit()
            else:
                session.add(PluginValues(
                    plugin=plugin, key=key, value=value))
                session.commit()

    def get_plugin_value(self, plugin, key, default=None):
        """Get a value for a plugin."""
        plugin = plugin.lower()
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()
            if result is not None:
                return _deserialize(result.value)
            return default

    def delete_plugin_value(self, plugin, key):
        """Delete a value for a plugin."""
        plugin = plugin.lower()
        with self.session() as session:
            result = session.execute(
                select(PluginValues)
                .where(PluginValues.plugin == plugin)
                .where(PluginValues.key == key)
            ).scalar_one_or_none()
            if result:
                session.delete(result)
                session.commit()

    def forget_plugin(self, plugin):
        """Remove all stored values for a plugin."""
        plugin = plugin.lower()
        with self.session() as session:
            session.execute(
                delete(PluginValues)
                .where(PluginValues.plugin == plugin))
            session.commit()

    # --- Combined Lookups ---

    def get_nick_or_channel_value(self, name, key, default=None):
        """Get a value for a nick or channel, depending on the identifier type."""
        identifier = self.make_identifier(name)
        if identifier.is_nick():
            return self.get_nick_value(identifier, key, default)
        return self.get_channel_value(identifier, key, default)

    def get_preferred_value(self, names, key):
        """Get a value from the first name which has it set."""
        for name in names:
            value = self.get_nick_or_channel_value(name, key)
            if value is not None:
                return value
        return None

    def close(self):
        """Close the database connection."""
        self.ssession.remove()
        self.engine.dispose()
