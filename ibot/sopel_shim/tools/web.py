"""Sopel-compatible web utilities."""

import re
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


def get(uri, timeout=20, headers=None, verify_ssl=True):
    """HTTP GET a URL and return ``(bytes, final_url, headers)``.

    Mimics Sopel's ``sopel.tools.web.get`` return shape closely enough
    for common URL plugins: ``(raw_bytes, url, headers_dict)``.
    """
    req_headers = {'User-Agent': DEFAULT_UA}
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(uri, headers=req_headers)
    context = None
    if not verify_ssl:
        context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(
                request, timeout=timeout, context=context) as resp:
            raw = resp.read()
            final_url = resp.geturl()
            resp_headers = dict(resp.headers.items())
            return raw, final_url, resp_headers
    except urllib.error.HTTPError as exc:
        # Still return body when available (Sopel plugins often handle this).
        try:
            raw = exc.read()
        except Exception:
            raw = b''
        return raw, uri, dict(getattr(exc, 'headers', {}) or {})
