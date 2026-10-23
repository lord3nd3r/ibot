[Docs home](../index.md) › Configuration › Plugin configuration

# Plugin configuration

Plugins keep their settings in their own INI sections. This page covers the built-in `[admin]` section, how plugins declare and read settings through Sopel's `StaticSection` API, the attribute types ibot supports, environment-variable overrides, and where to find settings for the sopel-scripts collection.

## In this article

- [Prerequisites](#prerequisites)
- [The \[admin\] section](#the-admin-section)
- [How plugins read configuration](#how-plugins-read-configuration)
- [Declaring a section with StaticSection](#declaring-a-section-with-staticsection)
- [Attribute types](#attribute-types)
- [Environment-variable overrides](#environment-variable-overrides)
- [Differences from Sopel](#differences-from-sopel)
- [Settings for the sopel-scripts collection](#settings-for-the-sopel-scripts-collection)
- [See also](#see-also)

## Prerequisites

- [Configuration overview](overview.md)
- If you're writing a plugin: [Writing plugins](../developer-guide/writing-plugins.md)

## The [admin] section

These options are read by the built-in `admin` plugin **each time the event fires**, so they take effect after `.rehash` without a restart.

| Key | Type | Default | Description |
|---|---|---|---|
| `hold_ground` | bool | `false` | When the bot is kicked, wait 5 seconds and rejoin the channel |
| `auto_accept_invite` | bool | `false` | Join a channel when the bot is `INVITE`d to it by an admin or owner |

Booleans in this section accept `true`, `yes`, `1` and `on` (case-insensitive). Anything else counts as false.

```ini
[admin]
hold_ground = true
auto_accept_invite = false
```

> **Note:** With `auto_accept_invite = true`, the bot follows invites only from users who pass the [admin check](../administration/permissions.md). Other invites are ignored and logged as `Ignoring invite to <channel> from non-admin <nick>`. Channels joined this way aren't saved to the persistent list; use `.bjoin` for that.

> **Note:** The rejoin after a kick sleeps for 5 seconds inside the handler thread. It only works if the channel lets the bot back in (no ban and no `+i`).

## How plugins read configuration

At runtime, `bot.config` and `bot.settings` both return the same `Config` object.

| Access pattern | Returns | Notes |
|---|---|---|
| `bot.config.weather.api_key` | raw `str` or `None` | Works for any section in the file. A missing key gives `None`. A missing **section** raises `AttributeError`. |
| `bot.config['weather'].api_key` | raw `str` or `None` | A missing section raises `KeyError`. Use this form for names like `#chan`. |
| `'weather' in bot.config` | `bool` | Is the section present? |
| `bot.config.option('weather', 'api_key', 'default')` | `str` | ibot convenience method with a default |
| `bot.config.has_option('weather', 'api_key')` | `bool` | |
| `bot.config.define_section('weather', WeatherSection)` | n/a | Typed access (see below) |
| `bot.config.save()` | n/a | Rewrites the config file (comments are lost) |

## Declaring a section with StaticSection

```python
from sopel import plugin
from sopel.config import types


class WeatherSection(types.StaticSection):
    api_key = types.SecretAttribute('api_key')
    units = types.ChoiceAttribute('units', ['metric', 'imperial'], default='metric')
    timeout = types.ValidatedAttribute('timeout', parse=int, default=10)
    enabled = types.BooleanAttribute('enabled', default=True)
    channels = types.ListAttribute('channels')


def setup(bot):
    bot.config.define_section('weather', WeatherSection)


@plugin.command('w')
def weather(bot, trigger):
    cfg = bot.config.weather
    if not cfg.api_key:
        bot.reply('Weather is not configured.')
        return
    bot.say(f'Units: {cfg.units}, timeout {cfg.timeout}s')
```

```ini
[weather]
api_key = YOUR_KEY_HERE
units = imperial
timeout = 15
channels =
    "#main"
    "#weather"
```

| `define_section` behaviour | Detail |
|---|---|
| Missing section | Created empty in memory, so attributes return their defaults |
| `validate` | Accepted but **ignored**. ibot never validates at load time. |
| Instantiation error | Logged with a traceback (`Config section [<name>] (<class>) failed to initialise; falling back to raw string values`), then falls back to an untyped proxy (raw strings) |
| Values parsed | **On every attribute read**, so config changes are seen after `.rehash` |

## Attribute types

| Type | Parse behaviour | Default if missing |
|---|---|---|
| `ValidatedAttribute(name, parse=None, serialize=None, default=None, is_secret=False)` | Calls `parse(value)` if given. `parse=bool` uses the boolean parser below. | `default` |
| `SecretAttribute(name, parse=None, serialize=None, default=None)` | Same as `ValidatedAttribute` with `is_secret=True` | `default` |
| `BooleanAttribute(name, default=False)` | `1`, `enable`, `enabled`, `on`, `true`, `y`, `yes` → `True`. Anything else → `False`. | `default` |
| `ValidatedAttribute(..., parse=bool)` | `1`, `yes`, `y`, `true`, `on` → `True`. Anything else → `False`. | `default` |
| `ChoiceAttribute(name, choices, default=None)` | The value must be in `choices`, otherwise **`ValueError` on read** | `default` |
| `FilenameAttribute(name, relative=True, directory=False, default=None)` | `~` expanded. `relative` and `directory` are **ignored**, with no path anchoring or existence check. | `default` |
| `ListAttribute(name, strip=True, default=None)` | See below | `[]` |
| `NO_DEFAULT` | Sentinel: when used as a default, a missing key returns `None` | n/a |

### ListAttribute

- If the value contains a newline, it's split into lines, and a trailing or leading `,` on each line is stripped.
- Otherwise it's split on `,`.
- Blank items are dropped.
- An item written as `"#something"` (double quotes, starting with `#`) has its quotes removed. Other quotes are kept.

> **Note:** This differs slightly from `[core]` lists, which strip any matching `"…"` or `'…'` quotes. See [Lists](overview.md#lists).

### Writing values

Assigning to an attribute (`bot.config.weather.units = 'metric'`) updates the in-memory config, and assigning `None` removes the key. Call `bot.config.save()` to write the change to disk. Lists are written in multi-line form.

## Environment-variable overrides

For attributes declared on a `StaticSection`, an environment variable takes precedence over the file:

```text
SOPEL_<SECTION>_<ATTRIBUTE>      (both upper-cased)
```

| Section / key | Variable |
|---|---|
| `[weather] api_key` | `SOPEL_WEATHER_API_KEY` |
| `[ai_multi] api_key` | `SOPEL_AI_MULTI_API_KEY` |

```bash
export SOPEL_WEATHER_API_KEY='YOUR_KEY_HERE'
python -m ibot mybot.cfg
```

With systemd, use `Environment=` or, better, an `EnvironmentFile=` that has mode `0600`. See [Running as a service](../getting-started/running-as-a-service.md).

> **Note:** Overrides only apply to `StaticSection` attributes. They don't apply to plain `bot.config.section.key` access, `bot.config.option()`, or `[core]` keys.

## Differences from Sopel

| Sopel | ibot |
|---|---|
| `sopel configure` / `configure(config)` wizard | Not supported. `configure()` functions in plugins are never called and `configure_setting()` does nothing. Edit the file by hand. |
| `define_section(..., validate=True)` raises on bad values at startup | Never validates. Errors surface when the attribute is read. |
| `FilenameAttribute` resolves relative to the config directory | Only expands `~` |
| `[#channel]` sections with `disable_plugins` / `disable_commands` | `disable_plugins` is honoured; `disable_commands` is ignored (see [Per-channel settings](per-channel.md#sopel-style-channel-sections)) |

## Settings for the sopel-scripts collection

Kristopher's plugin collection, [lord3nd3r/sopel-scripts](https://github.com/lord3nd3r/sopel-scripts), documents each plugin's section and keys in its own `docs/` and `commands.md`. On the glitchy deployment, the config has sections for `help`, `wikipedia`, `tell`, `imdb`, `weather`, `chat`, `ai_multi`, `moo`, `safety`, `channelstats`, `harambe` and others, all read by those plugins and not by ibot itself. Refer to that repository for the key names and meanings.

> **Warning:** Several of those sections hold API keys and passwords. Keep the config file at mode `0600`, and never paste it into IRC, an issue, or a pastebin.

## See also

- [Configuration overview](overview.md)
- [Writing plugins](../developer-guide/writing-plugins.md)
- [Plugin API reference](../developer-guide/plugin-api-reference.md)
- [Sopel compatibility](../developer-guide/sopel-compatibility.md)

---
[← Back to docs home](../index.md)
