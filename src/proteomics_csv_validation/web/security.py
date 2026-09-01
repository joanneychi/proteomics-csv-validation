"""HTTP response hardening for the local browser interface."""

from __future__ import annotations

from collections.abc import (
    Awaitable,
    Callable,
)

from starlette.datastructures import (
    MutableHeaders,
)
from starlette.types import (
    Message,
    Receive,
    Scope,
    Send,
)


_SECURITY_HEADERS = (
    (
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'",
    ),
    (
        "Referrer-Policy",
        "same-origin",
    ),
    (
        "X-Content-Type-Options",
        "nosniff",
    ),
    (
        "X-Frame-Options",
        "DENY",
    ),
    (
        "Cross-Origin-Opener-Policy",
        "same-origin",
    ),
    (
        "Cross-Origin-Resource-Policy",
        "same-origin",
    ),
    (
        "Permissions-Policy",
        "camera=(), microphone=(), "
        "geolocation=(), payment=(), usb=()",
    ),
)


class SecurityHeadersMiddleware:
    """Attach the fixed local-application security header policy."""

    def __init__(
        self,
        app: Callable[
            [
                Scope,
                Receive,
                Send,
            ],
            Awaitable[None],
        ],
    ) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._app(
                scope,
                receive,
                send,
            )
            return

        async def send_wrapper(
            message: Message,
        ) -> None:
            if (
                message["type"]
                == "http.response.start"
            ):
                headers = MutableHeaders(
                    scope=message
                )

                for name, value in (
                    _SECURITY_HEADERS
                ):
                    headers[name] = value

            await send(
                message
            )

        await self._app(
            scope,
            receive,
            send_wrapper,
        )
