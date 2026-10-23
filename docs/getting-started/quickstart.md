[Docs home](../index.md) › Getting started › Quickstart

# Quickstart: your first ibot

This walkthrough takes you from an installed checkout to a bot that is connected, has joined a channel and answers admin commands, then adds a first custom plugin. It takes about ten minutes.

## In this article

- [Prerequisites](#prerequisites)
- [Step 1: Generate a configuration file](#step-1-generate-a-configuration-file)
- [Step 2: Edit the essentials](#step-2-edit-the-essentials)
- [Step 3: Start the bot](#step-3-start-the-bot)
- [Step 4: Talk to your bot](#step-4-talk-to-your-bot)
- [Step 5: Add your first plugin](#step-5-add-your-first-plugin)
- [Step 6: Stop the bot](#step-6-stop-the-bot)
- [Next steps](#next-steps)
- [See also](#see-also)

## Prerequisites

- ibot is installed. See [Installation](installation.md).
- You have a registered IRC nickname for yourself, which makes owner checks reliable. Registering one for the bot is recommended too.
- You know which network, port and channel you want to use.

## Step 1: Generate a configuration file

```bash
cd ~/ibot
python -m ibot --generate-config mybot.cfg
chmod 600 mybot.cfg
```

This writes the following template:

```ini
[core]
nick = ibot
host = irc.libera.chat
port = 6697
use_ssl = true
verify_ssl = true
owner = yournick
channels = #yourchannel
prefix = \.
db_filename = ibot.db

# Authentication (optional)
# auth_method = sasl
# auth_user = ibot
# auth_password = yourpassword

# Admin list
# admins = admin1, admin2
# admin_accounts = account1, account2

# Plugin directories (comma-separated)
# extra = /path/to/plugins

# Plugins to exclude
# exclude = plugin1, plugin2

# Flood protection
# flood_burst = 4
# flood_refill = 1

# Logging
# logging_level = INFO
```

> **Warning:** `--generate-config` never overwrites an existing file, but it still prints `Default config written to: mybot.cfg` when the file already existed and was left alone. Check the file contents if you aren't sure.

> **Note:** A newly generated file is created with mode `0600` (owner read/write only), because it will soon hold passwords. A config file you created some other way, or one created by an older build, keeps its existing mode, so run `chmod 600` on it as shown above.

## Step 2: Edit the essentials

Open the file and set at least the following:

```ini
[core]
nick = MyBot
host = irc.libera.chat
port = 6697
use_ssl = true
verify_ssl = true

owner = YourNick
owner_account = YourAccount

channels = #yourchannel
prefix = \.

db_filename = mybot.db

auth_method = sasl
auth_user = MyBot
auth_password = YOUR_PASSWORD_HERE
```

| Key | Why it matters |
|---|---|
| `nick` | The nickname the bot registers with. If it is taken, ibot tries `MyBot_`, `MyBot__`, then `MyBot_` plus a random number, and later tries to reclaim the real nick with services `GHOST` if a password is configured. |
| `host` / `port` / `use_ssl` | Where the bot connects. TLS on 6697 is the default. |
| `owner` / `owner_account` | Who can run owner-only commands. When the server supplies account information, `owner_account` is preferred. See [Permissions](../administration/permissions.md). |
| `channels` | Channels joined after registration |
| `prefix` | A **regular expression** for the command prefix. `\.` is a literal dot. For `!` use `!`, for `$` use `\$`. |
| `db_filename` | SQLite file, resolved relative to the config file's directory |
| `auth_*` | SASL or NickServ login. See [Authentication](../configuration/authentication.md). |

> **Note:** The config file is read **without** interpolation, so `%` in a value (a password, for example) is just a character. Don't escape it as `%%`. See [Configuration overview](../configuration/overview.md#interpolation-and-the--character).

## Step 3: Start the bot

Run it in the foreground with debug logging:

```bash
python -m ibot mybot.cfg -v
```

A healthy startup looks like this (timestamps trimmed):

```text
[INFO] ibot: ibot starting up...
[INFO] ibot: Plugin directories: ['/home/you/ibot/ibot/plugins']
[INFO] ibot.loader: Sopel compatibility shim installed
[INFO] ibot.loader: Loaded plugin: admin (17 commands, 0 rules, 2 events)
[INFO] ibot: Loaded 1 plugins
[INFO] ibot.dispatch: Loaded disabled plugins for 0 channels
[INFO] ibot.bot: Connecting to irc.libera.chat:6697 (SSL=True)...
[INFO] ibot.bot: Connected to irc.libera.chat:6697
[INFO] ibot.bot: Server capabilities: account-tag extended-join multi-prefix sasl server-time …
[INFO] ibot.bot: CAP ACK: account-tag extended-join multi-prefix sasl server-time
[INFO] ibot.bot: SASL authentication successful
[INFO] ibot.bot: Registered as MyBot
[INFO] ibot.bot: Joining #yourchannel
```

The exact wording of the log lines can vary slightly between versions. With `-v` you also see every raw line, marked `>>>` (sent) or `<<<` (received). Passwords in `AUTHENTICATE`, `PASS`, `OPER` and NickServ `IDENTIFY`/`GHOST`-style lines are replaced with `[redacted]`.

## Step 4: Talk to your bot

In your channel:

```text
<YourNick> .bstatus
<MyBot>    Nick: MyBot | Channels: 1 | Plugins: 1 | Commands: 19 | Rules: 0 | Events: 2
<YourNick> .plugins
<MyBot>    Loaded plugins (1): admin
```

Join another channel and make it persistent:

```text
<YourNick> .bjoin #another
<MyBot>    Joining #another
<MyBot>    #another will rejoin on restart.
```

If nothing happens, check:

1. That the prefix matches. With `prefix = \.` you type `.bstatus`.
2. That you are recognised as owner or admin. See [Troubleshooting](../troubleshooting.md#the-bot-ignores-my-admin-commands).

The full command list is in [Admin commands](../administration/admin-commands.md).

## Step 5: Add your first plugin

Create a `plugins/` directory **next to your config file**. ibot loads it automatically.

```bash
mkdir -p plugins
```

`plugins/hello.py`:

```python
from sopel import plugin


@plugin.command('hello', 'hi')
@plugin.example('.hello')
def hello(bot, trigger):
    """Greets the caller."""
    bot.reply('Hello there!')
```

Load it without restarting (owner only):

```text
<YourNick> .load hello
<MyBot>    Loaded hello (2 commands)
<YourNick> .hi
<MyBot>    YourNick: Hello there!
```

After you edit the file, run `.reload hello`. The [Writing plugins](../developer-guide/writing-plugins.md) tutorial goes much further.

## Step 6: Stop the bot

Do one of the following:

- Press **Ctrl+C**. On `SIGINT`/`SIGTERM` ibot sends `QUIT :Shutdown signal`, runs plugin `shutdown()` hooks and exits.
- Send `.bquit [message]` (or `.die`) from IRC as the owner.

## Next steps

- Keep it running: [Running as a service](running-as-a-service.md)
- Tune every option: [Core reference](../configuration/core-reference.md)
- Load the ibot-plugins collection: [Plugin management](../administration/plugin-management.md#using-the-ibot-plugins-collection)

## See also

- [Configuration overview](../configuration/overview.md)
- [Authentication](../configuration/authentication.md)
- [Admin commands](../administration/admin-commands.md)
- [Troubleshooting](../troubleshooting.md)

---
[← Back to docs home](../index.md)
