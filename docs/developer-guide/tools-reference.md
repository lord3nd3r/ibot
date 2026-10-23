[Docs home](../index.md) › Developer guide › Tools reference

# Tools reference

This page documents the utility modules available to plugins: `sopel.tools`, `sopel.tools.web`, `sopel.tools.time`, `sopel.tools.events`, `sopel.tools.target` and `sopel.formatting`. Only the functions and classes listed here exist in ibot.

## In this article

- [Prerequisites](#prerequisites)
- [sopel.tools](#sopeltools)
- [sopel.tools.web](#sopeltoolsweb)
- [sopel.tools.time](#sopeltoolstime)
- [sopel.tools.events](#sopeltoolsevents)
- [sopel.tools.target and sopel.tools.identifiers](#sopeltoolstarget-and-sopeltoolsidentifiers)
- [sopel.formatting](#sopelformatting)
- [Not provided](#not-provided)
- [See also](#see-also)

## Prerequisites

- [Writing plugins](writing-plugins.md)

## sopel.tools

| Name | Kind | Description |
|---|---|---|
| `Identifier(str)` | class | A nick or channel name with IRC case-insensitive `==`, `!=` and hashing |
| `Identifier.lower()` | method | RFC 1459 case-fold: ASCII lower-case, plus `{`→`[`, `}`→`]`, `\|`→`\`, `~`→`^` |
| `Identifier.is_nick()` | method | `False` if it starts with `#`, `&`, `+` or `!` |
| `SopelMemory` | class | A dict with a lock around each single operation |
| `SopelMemoryWithDefault(factory)` | class | Creates missing keys with `factory()` |
| `SopelIdentifierMemory` | class | A dict with case-insensitive `Identifier` keys |
| `get_hostmask_regex(mask)` | function | Turns a `nick!user@host` mask with `*` wildcards into a compiled, case-insensitive, end-anchored regex. `?` isn't a wildcard. |
| `chain_loaders(*loaders)` | function | Combines lazy loaders into one: `loader(settings)` returns the concatenated lists |
| `web`, `time`, `target`, `events` | attributes | The submodules below |

```python
from sopel.tools import Identifier, get_hostmask_regex

Identifier('End3r') == 'end3r'                         # True
Identifier('[Bot]').lower()                             # '[bot]'
Identifier('{Bot}').lower()                             # '[bot]'
bool(get_hostmask_regex('*!*@*.example.net').match('n!u@h.example.net'))  # True
```

## sopel.tools.web

| Name | Signature | Description |
|---|---|---|
| `DEFAULT_UA` | constant | `ibot/1.0 (+https://github.com/lord3nd3r/ibot)` |
| `search_urls` | `search_urls(text, schemes=None)` | Lists the `http`, `https` and `ftp` URLs in `text`, optionally filtered to `schemes`. URLs end at whitespace, `<`, `>`, quotes, `)` or `]`. |
| `quote` | `quote(s, safe='')` | `urllib.parse.quote` |
| `unquote` | `unquote(s)` | `urllib.parse.unquote` |
| `iri_to_uri` | `iri_to_uri(iri)` | IDNA-encodes the host and percent-encodes the path, query and fragment |
| `decode` | `decode(raw)` | Bytes → `str`: UTF-8, falling back to Latin-1. `None` → `''`. |
| `get` | `get(uri, timeout=20, headers=None, verify_ssl=True, max_bytes=MAX_BODY_BYTES, allow_private=False)` | An HTTP GET using `urllib`, with address checks. Returns `(body_bytes, final_url, headers_dict)`. |
| `check_url` | `check_url(url, allow_private=False)` | Raises `UnsafeURLError` unless `url` is `http`/`https`, has a host, and (unless `allow_private`) every address the host resolves to is public. Returns `None` when the URL is allowed. |
| `UnsafeURLError` | exception, subclass of `ValueError` | Raised by `check_url()` and `get()` for a refused URL or redirect |
| `MAX_BODY_BYTES` | constant | `5242880` (5 MiB): the default body limit of `get()` |
| `MAX_REDIRECTS` | constant | `10`: the most redirects `get()` follows |

`get()` details:

| Aspect | Behaviour |
|---|---|
| Headers | `User-Agent: DEFAULT_UA`, merged with `headers` |
| Schemes | Only `http` and `https`. Anything else raises `UnsafeURLError: URL scheme not allowed: …`. |
| Address checks | Before the request, the host is resolved and the URL refused (`Refusing to fetch private/internal address: <host>`) if **any** address is private, loopback, link-local, multicast, reserved or unspecified (IPv4-mapped IPv6 addresses are unwrapped first). Pass `allow_private=True` to skip this. |
| Redirects | Followed, up to `MAX_REDIRECTS`. **Every hop** is re-checked with `check_url()`. `final_url` is the URL after redirects. |
| HTTP errors (4xx/5xx) | **Don't raise**: they return the error body, the *original* URI, and the headers. Check the content yourself. |
| Network errors | Raise `urllib.error.URLError`, `socket.timeout`, … |
| Body size | At most `max_bytes` bytes are read (default 5 MiB). A longer body is cut and logged as `Response from <url> truncated at N bytes`. `max_bytes=0` or `None` reads everything. |
| `verify_ssl=False` | Disables certificate verification |

> **Warning:** The address check resolves the host **separately** from the actual connection. If DNS resolution fails during the check, the URL is allowed through (urllib then reports its own error), and a hostile DNS server could answer differently for the second lookup (DNS rebinding). The check also looks at the target host, not at an HTTP proxy configured through `http_proxy`/`https_proxy` environment variables. Treat it as a strong default, not a guarantee, for user-supplied URLs.

> **Note:** Sopel's own `web.get` was removed in Sopel 8; this function is ibot-specific, kept for older plugins. Its extra parameters (`max_bytes`, `allow_private`) and `check_url()` don't exist in Sopel.

```python
from sopel import plugin
from sopel.tools import web

@plugin.command('status')
def status(bot, trigger):
    try:
        body, url, headers = web.get('https://status.example.com/api', timeout=10)
    except web.UnsafeURLError:
        bot.reply('That address is not allowed.')
        return
    except Exception:
        bot.reply('Status service unreachable.')
        return
    bot.say(web.decode(body)[:200])
```

## sopel.tools.time

| Name | Signature | Description |
|---|---|---|
| `parse_duration` | `parse_duration(s) -> timedelta` | Accepts a whole number of seconds (`"90"`), or `w`/`d`/`h`/`m`/`s` components in that order (`"1w2d3h4m5s"`, `"90m"`, case-insensitive). Raises `ValueError` otherwise. |

> **Note:** Matching is anchored only at the start, so trailing text is ignored: `"5mfoo"` parses as 5 minutes. Spaces aren't allowed. Sopel's other time helpers (`format_time`, `seconds_to_human`, `get_timezone`, …) **aren't** provided.

## sopel.tools.events

Class attributes that map names to numerics. For example, `events.RPL_WELCOME == '001'`.

| Group | Names |
|---|---|
| Registration | `RPL_WELCOME` 001, `RPL_YOURHOST` 002, `RPL_CREATED` 003, `RPL_MYINFO` 004, `RPL_ISUPPORT` 005 |
| LUSERS | `RPL_LUSERCLIENT` 251, `RPL_LUSEROP` 252, `RPL_LUSERUNKNOWN` 253, `RPL_LUSERCHANNELS` 254, `RPL_LUSERME` 255 |
| WHOIS/WHO | `RPL_AWAY` 301, `RPL_WHOISUSER` 311, `RPL_WHOISSERVER` 312, `RPL_WHOISOPERATOR` 313, `RPL_ENDOFWHO` 315, `RPL_WHOISIDLE` 317, `RPL_ENDOFWHOIS` 318, `RPL_WHOISCHANNELS` 319, `RPL_WHOISACCOUNT` 330, `RPL_WHOREPLY` 352 |
| Channels | `RPL_TOPIC` 332, `RPL_TOPICWHOTIME` 333, `RPL_NAMREPLY` 353, `RPL_ENDOFNAMES` 366 |
| MOTD | `RPL_MOTD` 372, `RPL_MOTDSTART` 375, `RPL_ENDOFMOTD` 376, `ERR_NOMOTD` 422 |
| Errors | `ERR_NOSUCHNICK` 401, `ERR_NOSUCHCHANNEL` 403, `ERR_CANNOTSENDTOCHAN` 404, `ERR_UNKNOWNCOMMAND` 421, `ERR_NICKNAMEINUSE` 433, `ERR_NOTREGISTERED` 451, `ERR_NEEDMOREPARAMS` 461, `ERR_ALREADYREGISTRED` 462, `ERR_CHANOPRIVSNEEDED` 482 |
| SASL | `RPL_LOGGEDIN` 900, `RPL_LOGGEDOUT` 901, `RPL_SASLSUCCESS` 903, `ERR_SASLFAIL` 904, `ERR_SASLTOOLONG` 905, `ERR_SASLABORTED` 906 |

```python
from sopel import plugin
from sopel.tools import events

@plugin.event(events.RPL_WELCOME)
def on_connect(bot, trigger):
    ...
```

## sopel.tools.target and sopel.tools.identifiers

| Module | Contents |
|---|---|
| `sopel.tools.target` | `User`, `Channel`: the same classes used in `bot.users` and `bot.channels`, so `isinstance` checks work. See [Plugin API reference](plugin-api-reference.md#channel-and-user-state). |
| `sopel.tools.identifiers` | `Identifier`, and `IdentifierFactory` (an alias of `Identifier`) |

## sopel.formatting

| Name | Value or behaviour |
|---|---|
| `BOLD`, `ITALIC`, `UNDERLINE`, `STRIKETHROUGH`, `MONOSPACE`, `RESET`, `COLOR`, `REVERSE` | `\x02`, `\x1d`, `\x1f`, `\x1e`, `\x11`, `\x0f`, `\x03`, `\x16` |
| `bold(t)`, `italic(t)`, `underline(t)`, `strikethrough(t)`, `monospace(t)` | Wrap `t` in the code |
| `color(text, fg=None, bg=None)` | `\x03FG[,BG]text\x03`. With `fg=None`, the text is returned unchanged. Numbers are zero-padded to two digits. |
| `plain(text)` | Strips bold/italic/underline/strike/monospace/reset/reverse and `\x03` colour codes |
| `colors.WHITE`… | **Integers**: `WHITE` 0, `BLACK` 1, `BLUE` 2, `GREEN` 3, `RED` 4, `BROWN`/`MAROON` 5, `PURPLE` 6, `ORANGE` 7, `YELLOW` 8, `LIGHT_GREEN`/`LIME` 9, `TEAL`/`CYAN` 10, `LIGHT_CYAN` 11, `LIGHT_BLUE`/`ROYAL_BLUE` 12, `PINK`/`LIGHT_PURPLE`/`FUCHSIA` 13, `GREY`/`GRAY` 14, `LIGHT_GREY`/`LIGHT_GRAY` 15, `DEFAULT` 99 |

```python
from sopel import formatting as f
bot.say(f.bold('Alert:') + ' ' + f.color('disk full', f.colors.RED))
```

> **Warning:** Sopel's `colors` are two-digit **strings** (`'04'`). In ibot they're integers. `color()` handles both, but code that concatenates them directly (`'\x03' + colors.RED`) raises `TypeError`. Use `color()`, or `str(c).zfill(2)`.

## Not provided

Sopel features that are missing include, among others: `tools.web.post`/`head`, `tools.time.format_time`/`seconds_to_human`/`get_timezone`, `tools.get_logger`, `tools.deprecated`, `formatting.hex_color`, and the `sopel.plugins` API (its module is an empty stub). See [Sopel compatibility](sopel-compatibility.md).

## See also

- [Plugin API reference](plugin-api-reference.md)
- [Sopel compatibility](sopel-compatibility.md)
- [Security](../security.md)

---
[← Back to docs home](../index.md)
