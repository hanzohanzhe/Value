"""Request guard of the VALUE local API (P0-1, findings F5-01, F4-01, R1-01, R1-02, R1-15).

The API listens on loopback, which every web page the user opens can reach.
Browsers therefore never talk to it directly: they talk to the UI origin, and
the UI gateway (``scripts/value-ui-gateway.mjs``) checks Host, Sec-Fetch-Site
and Origin, strips the browser context and injects the session token.  This
module is the API's own check, applied to every request before routing
(``Handler._dispatch``), in this order:

1. ``Host`` must be exactly ``127.0.0.1:<port>`` or ``localhost:<port>``
   -> 421 ``GF_HOST_REJECTED`` (DNS rebinding);
2. any ``Origin`` header (including ``null``) -> 403
   ``GF_BROWSER_ORIGIN_REJECTED``: a browser request that did not come
   through the gateway;
3. ``Sec-Fetch-Site`` other than ``none`` -> 403 ``GF_BROWSER_CONTEXT_REJECTED``;
4. ``Content-Length`` that is not a decimal number -> 400
   ``GF_CONTENT_LENGTH_INVALID``; a POST with ``Transfer-Encoding`` -> 411
   ``GF_LENGTH_REQUIRED`` (the server reads bodies by length only);
5. ``X-VALUE-Session`` compared in constant time with this process's token:
   missing -> 403 ``GF_SESSION_REQUIRED``, wrong -> 403 ``GF_SESSION_INVALID``.
   Only ``GET /api/health`` without the header is answered (with the reduced
   payload) and ``OPTIONS`` needs no token (it is answered without any CORS
   grant);
6. a POST whose ``Content-Type`` is missing or a CORS "simple" type
   (``text/plain``, ``application/x-www-form-urlencoded``,
   ``multipart/form-data``) -> 415 ``GF_CONTENT_TYPE_REJECTED``.  The raw
   header is inspected: ``Message.get_content_type()`` reports ``text/plain``
   for a missing header.

``X-VALUE-Executable-Trust`` stays a UI-level informed-consent flag; it is not
a security control.  ``evaluate`` is a pure function so the whole decision
table is testable without a socket.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from typing import Mapping

from backend.api_session import SESSION_HEADER, token_matches

SIMPLE_CONTENT_TYPES = frozenset({"text/plain", "application/x-www-form-urlencoded", "multipart/form-data"})
TOKENLESS_ROUTES = frozenset({("GET", "/api/health")})
MAX_DRAIN_BYTES = 2 * 1024 * 1024

# Added to every response of the API (``Handler.end_headers``), including
# ``send_error`` pages written by http.server itself.
SECURITY_RESPONSE_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)


class UnsupportedMediaType(ValueError):
    """A request body in a media type the route does not accept (415)."""

    code = "GF_CONTENT_TYPE_REJECTED"


@dataclass(frozen=True)
class GuardDecision:
    status: int | None  # None: allowed
    code: str = ""
    message: str = ""
    authenticated: bool = False

    @property
    def allowed(self) -> bool:
        return self.status is None


def _reject(status: int, code: str, message: str) -> GuardDecision:
    return GuardDecision(status=status, code=code, message=message)


def _single(headers: Message | Mapping[str, str], name: str) -> tuple[str | None, int]:
    if isinstance(headers, Message):
        values = headers.get_all(name) or []
    else:
        values = [value for key, value in headers.items() if key.lower() == name.lower()]
    return (values[0] if values else None), len(values)


def allowed_hosts(bound_port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{int(bound_port)}", f"localhost:{int(bound_port)}"})


def media_type(raw: str | None) -> str:
    return (raw or "").split(";", 1)[0].strip().lower()


def evaluate(
    method: str,
    path: str,
    headers: Message | Mapping[str, str],
    *,
    bound_port: int,
    token: str | None,
) -> GuardDecision:
    """Decide one request before any routing or body read."""

    method = str(method).upper()
    host, host_count = _single(headers, "Host")
    if host_count != 1 or str(host).strip().lower() not in allowed_hosts(bound_port):
        return _reject(421, "GF_HOST_REJECTED", "VALUE only answers requests addressed to 127.0.0.1 or localhost on its own port.")
    _origin, origin_count = _single(headers, "Origin")
    if origin_count:
        return _reject(403, "GF_BROWSER_ORIGIN_REJECTED",
                       "Browser pages reach the VALUE API only through the VALUE UI gateway.")
    fetch_site, fetch_count = _single(headers, "Sec-Fetch-Site")
    if fetch_count and (fetch_count != 1 or str(fetch_site).strip().lower() != "none"):
        return _reject(403, "GF_BROWSER_CONTEXT_REJECTED",
                       "Browser pages reach the VALUE API only through the VALUE UI gateway.")
    length, length_count = _single(headers, "Content-Length")
    if length_count and (length_count != 1 or not str(length).strip().isdigit()):
        return _reject(400, "GF_CONTENT_LENGTH_INVALID", "Content-Length must be one decimal number.")
    _encoding, encoding_count = _single(headers, "Transfer-Encoding")
    if method == "POST" and encoding_count:
        return _reject(411, "GF_LENGTH_REQUIRED", "Send the request body with a Content-Length.")
    presented, presented_count = _single(headers, SESSION_HEADER)
    authenticated = presented_count == 1 and token_matches(token, presented)
    if presented_count and not authenticated:
        return _reject(403, "GF_SESSION_INVALID",
                       "The VALUE API session does not match; restart VALUE with its launcher.")
    if not authenticated and method != "OPTIONS" and (method, path) not in TOKENLESS_ROUTES:
        return _reject(403, "GF_SESSION_REQUIRED",
                       "The VALUE API needs its session (open VALUE through its launcher; scripts use "
                       "backend.api_session.authorized_headers).")
    if method == "POST":
        content_type, _count = _single(headers, "Content-Type")
        kind = media_type(content_type)
        if not kind or "/" not in kind or kind in SIMPLE_CONTENT_TYPES:
            return _reject(415, "GF_CONTENT_TYPE_REJECTED",
                           "Send a request body with an explicit, non-form Content-Type (for example application/json).")
    return GuardDecision(status=None, authenticated=authenticated)


def drainable_length(headers: Message | Mapping[str, str]) -> int | None:
    """Bytes to read before answering a rejected request (None: close instead)."""

    length, count = _single(headers, "Content-Length")
    if count == 0:
        return 0
    if count != 1 or not str(length).strip().isdigit():
        return None
    value = int(str(length).strip())
    return value if value <= MAX_DRAIN_BYTES else None
