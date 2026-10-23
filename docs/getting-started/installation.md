[Docs home](../index.md) › Getting started › Installation

# Install ibot

This page covers installing ibot from source into a Python virtual environment, adding optional database drivers, and checking that the install works.

## In this article

- [Prerequisites](#prerequisites)
- [System requirements](#system-requirements)
- [Step 1: Get the source](#step-1-get-the-source)
- [Step 2: Create a virtual environment](#step-2-create-a-virtual-environment)
- [Step 3: Install ibot](#step-3-install-ibot)
- [Step 4: Verify the installation](#step-4-verify-the-installation)
- [Optional database drivers](#optional-database-drivers)
- [Installing without a virtual environment](#installing-without-a-virtual-environment)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)
- [See also](#see-also)

## Prerequisites

- A Unix-like system (Linux, BSD or macOS). ibot uses `asyncio` signal handlers for `SIGINT`/`SIGTERM`. These are skipped automatically on platforms that lack them, but Linux is the tested platform.
- Python **3.8 or newer**, with `venv` and `pip`.
- `git`.
- Outbound network access to your IRC server (default port 6697/TLS).

## System requirements

| Component | Requirement | Source of truth |
|---|---|---|
| Python | `>=3.8` | `pyproject.toml` → `requires-python` |
| SQLAlchemy | `>=2.0,<3.0` | `pyproject.toml` → `dependencies`, `requirements.txt` |
| Disk | A few MB, plus your SQLite database | |
| Memory | Small. Plugin calls run on a bounded pool of up to 64 worker threads by default (see [Dispatch](../architecture/dispatch.md#threading-model)). | `[core] handler_threads` |

> **Note:** The production deployment (`glitchy`) runs on Debian 13 with Python 3.13 and SQLAlchemy 2.0.x.

## Step 1: Get the source

```bash
git clone https://github.com/lord3nd3r/ibot.git
cd ibot
```

## Step 2: Create a virtual environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

> **Note:** On Debian/Ubuntu you may first need `sudo apt install python3-venv`. Debian 12 and newer mark the system Python as "externally managed" (PEP 668), so `pip install` outside a virtual environment is refused.

## Step 3: Install ibot

Choose one:

```bash
# Runtime only (editable, so `git pull` takes effect immediately)
pip install -e .

# Runtime + development tools (pytest, pytest-asyncio, mypy)
pip install -e ".[dev]"

# Dependencies only, run straight from the checkout without installing the package
pip install -r requirements.txt
```

The package defines these extras (`pyproject.toml` → `[project.optional-dependencies]`):

| Extra | Installs | Use when |
|---|---|---|
| `mysql` | `pymysql>=1.0` | Your database is MySQL or MariaDB |
| `postgres` | `psycopg2-binary>=2.9` | Your database is PostgreSQL |
| `dev` | `pytest>=7.0`, `pytest-asyncio>=0.21`, `mypy>=1.0` | You are developing or testing ibot |

Installing the package also creates an `ibot` console script (`ibot = ibot.__main__:main`).

## Step 4: Verify the installation

```bash
python -m ibot --help
```

Expected output:

```text
usage: ibot [-h] [--generate-config [FILE]] [-v] [config]

ibot - A Sopel-compatible IRC bot

positional arguments:
  config                Path to config file (default: ibot.cfg)

options:
  -h, --help            show this help message and exit
  --generate-config [FILE]
                        Generate a default config file and exit
  -v, --verbose         Enable debug logging
```

Check the version and the SQLAlchemy import:

```bash
python -c "import ibot, sqlalchemy; print(ibot.__version__, sqlalchemy.__version__)"
# 1.0.0 2.0.x
```

## Optional database drivers

SQLite needs no extra packages. For other databases, install a driver and configure `db_type`/`db_url` as described in [Database](../architecture/database.md).

```bash
pip install -e ".[mysql]"      # MySQL / MariaDB via PyMySQL
pip install -e ".[postgres]"   # PostgreSQL via psycopg2
```

> **Warning:** With `db_type = mysql` and no `db_driver`, ibot builds a URL that starts with `mysql://`, and SQLAlchemy resolves that to the `MySQLdb` (mysqlclient) driver, **not** PyMySQL. If you installed the `mysql` extra, set `db_driver = mysql+pymysql` or use an explicit `db_url = mysql+pymysql://...`.

## Installing without a virtual environment

You can run ibot directly from a checkout when SQLAlchemy is available to the interpreter (for example from the distribution package `python3-sqlalchemy`):

```bash
cd ~/ibot
python3 -m ibot mybot.cfg
```

`python3 -m ibot` resolves the `ibot` package from the current directory, so **run it from the repository root**. The `glitchy` deployment runs this way, as `python3 -m ibot glitchy.cfg -v` from `/home/ender/ibot`.

## Upgrading

```bash
cd ibot
git pull
pip install -e .        # only needed if dependencies changed
```

Then restart the process. You can pick up most plugin and config changes without restarting by using `.rehash` (see [Plugin management](../administration/plugin-management.md#hot-reloading)), but changes to the **core** (`ibot/bot.py`, `ibot/dispatch.py`, `ibot/sopel_shim/*`) always need a process restart.

## Uninstalling

```bash
pip uninstall ibot
rm -rf .venv
```

Your configuration files and databases are never removed automatically.

## See also

- [Quickstart](quickstart.md)
- [Running as a service](running-as-a-service.md)
- [Database](../architecture/database.md)
- [Testing](../developer-guide/testing.md)

---
[← Back to docs home](../index.md)
