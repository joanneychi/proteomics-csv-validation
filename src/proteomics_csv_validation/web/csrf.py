"""Request-origin and CSRF protections for the local browser workflow."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from starlette.requests import Request

_NONCE_BYTES = 32


def issue_csrf_token(
    secret: bytes,
) -> str:
    """Create a process-bound stateless CSRF token."""

    if (
        not isinstance(
            secret,
            bytes,
        )
        or len(secret) < 32
    ):
        raise ValueError(
            "secret must contain at least 32 bytes."
        )

    nonce = secrets.token_hex(
        _NONCE_BYTES
    )

    digest = hmac.new(
        secret,
        nonce.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    return nonce + "." + digest


def validate_csrf_token(
    secret: bytes,
    token: object,
) -> bool:
    """Validate one process-bound stateless CSRF token."""

    if not isinstance(token, str):
        return False

    parts = token.split(".")

    if len(parts) != 2:
        return False

    nonce, supplied = parts

    if (
        len(nonce) != _NONCE_BYTES * 2
        or len(supplied) != 64
    ):
        return False

    try:
        bytes.fromhex(nonce)
        bytes.fromhex(supplied)
    except ValueError:
        return False

    expected = hmac.new(
        secret,
        nonce.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        supplied,
        expected,
    )


def _request_origin(
    request: Request,
) -> str | None:
    host = request.headers.get("host")

    if not host:
        return None

    return (
        request.url.scheme.casefold()
        + "://"
        + host.casefold()
    )


def _header_origin(
    value: str,
    *,
    referer: bool,
) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    if (
        parsed.scheme.casefold()
        not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None

    if (
        not referer
        and (
            parsed.path not in {"", "/"}
            or parsed.query
        )
    ):
        return None

    return (
        parsed.scheme.casefold()
        + "://"
        + parsed.netloc.casefold()
    )


def request_has_trusted_origin(
    request: Request,
) -> bool:
    """Require same-origin context for state-changing requests."""

    fetch_site = (
        request.headers.get(
            "sec-fetch-site",
            "",
        )
        .strip()
        .casefold()
    )

    if fetch_site == "cross-site":
        return False

    expected = _request_origin(request)

    if expected is None:
        return False

    origin = request.headers.get("origin")

    if origin is not None:
        return (
            _header_origin(
                origin,
                referer=False,
            )
            == expected
        )

    referer = request.headers.get("referer")

    if referer is None:
        return False

    return (
        _header_origin(
            referer,
            referer=True,
        )
        == expected
    )
