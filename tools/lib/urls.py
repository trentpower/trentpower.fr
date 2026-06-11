"""
urls.py · single source of truth for url host matching.

`"github.com" in url` is a substring check, not a host check — it also
matches `https://github.com.evil.com/` and `https://evil.com/github.com`
(a codeql incomplete-url-substring-sanitization finding). callers that
classify a url by its domain import host_matches() instead, which
parses the url and compares the hostname exactly or as a subdomain.
"""

from __future__ import annotations

from urllib.parse import urlparse


def url_host(url: str) -> str:
    """the lowercased hostname of url, or '' when it has none."""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def host_matches(url: str, domain: str) -> bool:
    """True when url's host is exactly `domain` or a subdomain of it."""
    host = url_host(url)
    domain = domain.lower()
    return host == domain or host.endswith("." + domain)
