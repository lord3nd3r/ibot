[Docs home](../index.md) › Getting started › Running as a service

# Run ibot as a service

ibot runs in the foreground and logs to standard error. This page shows how to keep it running permanently with systemd (as a system unit or a user unit) or inside tmux/screen, how to handle logs, how to lock down file permissions, and how to run bots on several networks.

## In this article

- [Prerequisites](#prerequisites)
- [How ibot behaves as a long-running process](#how-ibot-behaves-as-a-long-running-process)
- [Option A: systemd system unit](#option-a-systemd-system-unit)
- [Option B: systemd user unit](#option-b-systemd-user-unit)
- [Option C: tmux or screen](#option-c-tmux-or-screen)
- [Logging](#logging)
- [File permissions](#file-permissions)
- [Running several bots or networks](#running-several-bots-or-networks)
- [Upgrades and restarts](#upgrades-and-restarts)
- [See also](#see-also)

## Prerequisites

- A working config that connects in the foreground. See [Quickstart](quickstart.md).
- A dedicated Unix user is recommended (the examples use `ender` and `/home/ender/ibot`).
- `sudo` access for system units, or `loginctl enable-linger` for user units.

## How ibot behaves as a long-running process

| Behaviour | Detail |
|---|---|
| Foreground only | There is no daemon/fork mode and no PID file |
| Logs | Go to **stderr** through `logging.basicConfig`. There is no option for a normal log file; the optional [raw traffic log](#logging) (`log_raw`) is the only file ibot writes itself. |
| Working directory | `python3 -m ibot` imports `ibot` from the current directory when it isn't installed into the environment, so set the working directory to the repository root |
| Relative paths | `db_filename` and the `plugins/` directory are resolved relative to the **config file's directory**, not the working directory |
| Reconnects | Built in. On disconnect the bot waits 5 s, 10 s, 20 s … up to 300 s, back to 5 s after each successful registration (`reconnect_on_disconnect = true`). A silent server is detected with a keepalive `PING` after 240 s. |
| `SIGINT` / `SIGTERM` | Sends `QUIT :Shutdown signal`, closes the socket, runs plugin `shutdown()` hooks, exits with status 0 |
| `.bquit` / `.die` | Sends `QUIT` straight away (bypassing the flood queue), waits up to 3 s for the server to close the link, closes it, runs plugin `shutdown()` hooks and exits with status 0. It doesn't reconnect. |
| Restart from a plugin | `bot.restart()` (plugin API; there's no built-in restart command) quits the same way, then replaces the process with a fresh `python -m ibot <same arguments>` in the original working directory. The PID stays the same, so systemd sees no exit. |
| Config errors | A missing config file exits with status 1 |

> **Note:** Both a signal and `.bquit` end with **exit status 0**. With `Restart=on-failure`, systemd will therefore *not* restart the bot after an intentional quit. That is usually what you want. Use `Restart=always` if `.die` should only bounce the bot.

## Option A: systemd system unit

Create `/etc/systemd/system/ibot-mybot.service`:

```ini
[Unit]
Description=ibot IRC bot (mybot)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ender
Group=ender
WorkingDirectory=/home/ender/ibot
ExecStart=/usr/bin/python3 -m ibot /home/ender/ibot/mybot.cfg
# With a virtual environment instead:
# ExecStart=/home/ender/ibot/.venv/bin/python -m ibot /home/ender/ibot/mybot.cfg
Restart=on-failure
RestartSec=30
KillSignal=SIGTERM
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1
UMask=0077

# Hardening (optional; relax if plugins need more)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ibot-mybot.service
systemctl status ibot-mybot.service
journalctl -u ibot-mybot.service -f
```

> **Warning:** Don't add `-v` in production unless you need it. Debug logging records **every line the bot sends and receives**, including private messages, into the journal. Credentials in `AUTHENTICATE` and `PRIVMSG NickServ :IDENTIFY` lines are redacted, but other content is not. See [Security](../security.md#logging-and-privacy).

> **Note:** `ProtectSystem=full` makes `/usr`, `/boot` and `/etc` read-only. Plugins that write outside the home directory (for example into `/var/lib`) need `ReadWritePaths=`. If a plugin misbehaves under hardening, remove options one at a time.

### Templated unit for several bots

`/etc/systemd/system/ibot@.service`:

```ini
[Unit]
Description=ibot IRC bot (%i)
Wants=network-online.target
After=network-online.target

[Service]
User=ender
WorkingDirectory=/home/ender/ibot
ExecStart=/usr/bin/python3 -m ibot /home/ender/ibot/%i.cfg
Restart=on-failure
RestartSec=30
UMask=0077

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ibot@glitchy ibot@technet
```

## Option B: systemd user unit

This needs no root access once lingering is enabled.

```bash
sudo loginctl enable-linger ender      # one time; lets user units run without a login
mkdir -p ~/.config/systemd/user
```

`~/.config/systemd/user/ibot-mybot.service`:

```ini
[Unit]
Description=ibot IRC bot (mybot)
After=network-online.target

[Service]
WorkingDirectory=%h/ibot
ExecStart=/usr/bin/python3 -m ibot %h/ibot/mybot.cfg
Restart=on-failure
RestartSec=30
Environment=PYTHONUNBUFFERED=1
UMask=0077

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ibot-mybot.service
journalctl --user -u ibot-mybot.service -f
```

## Option C: tmux or screen

This suits interactive debugging. Note that tmux and screen do **not** restart the bot after a crash or reboot.

```bash
# tmux
tmux new-session -d -s mybot -c ~/ibot 'python3 -m ibot mybot.cfg 2>&1 | tee -a logs/mybot.log'
tmux attach -t mybot           # detach again with Ctrl+b d

# screen
cd ~/ibot && screen -dmS mybot sh -c 'python3 -m ibot mybot.cfg 2>&1 | tee -a logs/mybot.log'
screen -r mybot                # detach with Ctrl+a d
```

Create `logs/` first (`mkdir -p ~/ibot/logs && chmod 700 ~/ibot/logs`).

> **Warning:** Pressing Ctrl+C in the attached session stops the bot. To leave it running, detach instead.

To start it automatically after a reboot without systemd, use a cron `@reboot` entry:

```cron
@reboot cd /home/ender/ibot && /usr/bin/tmux new-session -d -s mybot 'python3 -m ibot mybot.cfg'
```

## Logging

| Setting | Effect |
|---|---|
| Default | `INFO` level, format `%(asctime)s [%(levelname)s] %(name)s: %(message)s`, date format `%Y-%m-%d %H:%M:%S` |
| `-v` / `--verbose` | `DEBUG` level, including raw IRC traffic (`>>>` sent, `<<<` received) |
| `[core] log_raw = true` | Also writes the raw traffic (redacted) to `<logdir>/<config-name>.raw.log`, rotated at 10 MiB with 3 backups, mode `0600`. See [Core reference](../configuration/core-reference.md#log_raw). |
| `[core] logging_level` | **Has no effect.** The root logger is configured once at `INFO`/`DEBUG` before the config is read, and the second `logging.basicConfig()` call that would apply `logging_level` does nothing. Use `-v` to get debug output. |

Logger names you will see: `ibot`, `ibot.bot`, `ibot.dispatch`, `ibot.loader`, `ibot.plugins.admin`, plus whatever names your plugins use.

Rotating a tee'd log file with logrotate:

```text
/home/ender/ibot/logs/*.log {
    weekly
    rotate 8
    compress
    missingok
    copytruncate
}
```

## File permissions

Config files hold IRC passwords and plugin API keys. Databases hold user data (seen times, tells, quotes and so on).

```bash
cd ~/ibot
chmod 600 *.cfg            # owner read/write only
chmod 600 *.db             # SQLite databases
chmod 700 .                # optional: keep the whole checkout private
```

> **Note:** The repository's `.gitignore` covers `*.cfg` (except `default.cfg`), `*.cfg.*` (so `mybot.cfg.orig` and `mybot.cfg.bak`), `*.orig`, `*~`, `*.db` with its `-wal`/`-shm`/`-journal` side files, `*.log` and `logs/`. Other names, such as `mybot.backup.cfg.txt` or a copy outside those patterns, are **not** covered, so check `git status` before every commit.

> **Warning:** Generating a config gives it mode `0600`, but existing files keep the mode they already have. Run the `chmod` commands above once on an existing installation.

## Running several bots or networks

One ibot process connects to **one** server with **one** nick. To run on several networks, start one process per config file:

```bash
python3 -m ibot glitchy.cfg
python3 -m ibot technet.cfg
```

Each process has its own database. By default that is the `db_filename` you set, or `<config-name>.db` next to the config. Two processes **can** point `extra` at the same plugin directory. Avoid sharing one SQLite file between them: ibot enables WAL mode and a 10-second `busy_timeout`, which makes occasional concurrent writes safe, but each process caches its per-channel disabled-plugin list and won't see the other's `.disable`/`.enable` changes until a `.rehash`. Persistent channels (`.bjoin`) would also be shared, so both bots would join the same channels.

## Upgrades and restarts

1. `git pull` in the repository.
2. Core changes need a restart, for example `sudo systemctl restart ibot-mybot`.
3. Plugin-only changes can use `.reload <plugin>` or `.rehash` from IRC (see [Plugin management](../administration/plugin-management.md#hot-reloading)).

## See also

- [Quickstart](quickstart.md)
- [Security](../security.md)
- [Troubleshooting](../troubleshooting.md)
- [Connection lifecycle](../architecture/connection-lifecycle.md)

---
[← Back to docs home](../index.md)
