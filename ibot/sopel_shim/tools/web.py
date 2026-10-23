"""Sopel-compatible web utilities."""

import ipaddress
import logging
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request


_URL_REGEX = re.compile(
    r'(?:https?|ftp)://[^\s<>\'")\]]+',
    re.IGNORECASE,
)

# Default User-Agent matching roughly what Sopel sends.
DEFAULT_UA = 'ibot/1.0 (+https://github.com/lord3nd3r/ibot)'

LOGGER = logging.getLogger(__name__)

# Largest response body get() will read; anything beyond is dropped.
MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 10
_ALLOWED_SCHEMES = ('http', 'https')


class UnsafeURLError(ValueError):
    """Raised when a URL (or a redirect target) is not allowed."""


def search_urls(text, schemes=None):
    """Find URLs in text."""
    urls = _URL_REGEX.findall(text)
    if schemes:
        schemes = {s.lower() for s in schemes}
        filtered = []
        for url in urls:
            scheme = url.split('://', 1)[0].lower()
            if scheme in schemes:
                filtered.append(url)
        return filtered
    return urls


def quote(s, safe=''):
    """URL-encode a string."""
    return urllib.parse.quote(s, safe=safe)


def unquote(s):
    """URL-decode a string."""
    return urllib.parse.unquote(s)


def iri_to_uri(iri):
    """Convert an IRI to a URI (percent-encode non-ASCII)."""
    if not iri:
        return iri
    parts = urllib.parse.urlsplit(iri)
    # Encode each component appropriately.
    netloc = parts.netloc.encode('idna').decode('ascii') if parts.netloc else ''
    path = urllib.parse.quote(parts.path, safe='/:@!$&\'()*+,;=-._~')
    query = urllib.parse.quote(parts.query, safe='=&%:@!$/()*,;+-._~')
    fragment = urllib.parse.quote(parts.fragment, safe='=&%:@!$/()*,;+-._~')
    return urllib.parse.urlunsplit(
        (parts.scheme, netloc, path, query, fragment))


def decode(raw):
    """Decode raw HTTP response bytes to text.

    Tries UTF-8 first, then falls back to Latin-1 (never fails).
    """
    if isinstance(raw, str):
        return raw
    if raw is None:
        return ''
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1', errors='replace')


def _host_is_public(host):
    """True if every address *host* resolves to is a public address."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Let urllib raise its normal resolution error.
        return True
    for info in infos:
        addr = info[4][0].split('%', 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if getattr(ip, 'ipv4_mapped', None):
            ip = ip.ipv4_mapped
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False
    return True


def check_url(url, allow_private=False):
    """Raise UnsafeURLError unless *url* is http(s) to a public host."""
    parts = urllib.parse.urlsplit(url)
    scheme = (parts.scheme or '').lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f'URL scheme not allowed: {scheme or "(none)"}')
    if not parts.hostname:
        raise UnsafeURLError('URL has no host')
    if not allow_private and not _host_is_public(parts.hostname):
        raise UnsafeURLError(
            f'Refusing to fetch private/internal address: {parts.hostname}')


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-checks every redirect hop (scheme and destination address)."""

    max_redirections = MAX_REDIRECTS

    def __init__(self, allow_private=False):
        super().__init__()
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        check_url(newurl, allow_private=self.allow_private)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_capped(resp, max_bytes):
    if max_bytes is None or max_bytes <= 0:
        return resp.read()
    raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        LOGGER.warning("Response from %s truncated at %d bytes",
                       getattr(resp, 'geturl', lambda: '?')(), max_bytes)
        raw = raw[:max_bytes]
    return raw


def get(uri, timeout=20, headers=None, verify_ssl=True,
        max_bytes=MAX_BODY_BYTES, allow_private=False):
    """HTTP GET a URL and return ``(bytes, final_url, headers)``.

    Mimics Sopel's ``sopel.tools.web.get`` return shape closely enough
    for common URL plugins: ``(raw_bytes, url, headers_dict)``.

    Only http/https URLs are fetched; URLs (and every redirect) that resolve
    to private, loopback or link-local addresses are refused with
    ``UnsafeURLError`` unless ``allow_private=True``. At most ``max_bytes``
    of the body are read.
    """
    check_url(uri, allow_private=allow_private)

    req_headers = {'User-Agent': DEFAULT_UA}
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(uri, headers=req_headers)
    context = None
    if not verify_ssl:
        context = ssl._create_unverified_context()

    opener = urllib.request.build_opener(
        _SafeRedirectHandler(allow_private=allow_private),
        urllib.request.HTTPSHandler(context=context),
    )

    try:
        with opener.open(request, timeout=timeout) as resp:
            raw = _read_capped(resp, max_bytes)
            final_url = resp.geturl()
            resp_headers = dict(resp.headers.items())
            return raw, final_url, resp_headers
    except urllib.error.HTTPError as exc:
        # Still return body when available (Sopel plugins often handle this).
        try:
            raw = _read_capped(exc, max_bytes)
        except Exception:
            raw = b''
        return raw, uri, dict(getattr(exc, 'headers', {}) or {})
