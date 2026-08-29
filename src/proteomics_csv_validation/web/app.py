"""Secure HTTP shell for the local browser interface."""

from __future__ import annotations

from pathlib import Path

from fastapi import (
    FastAPI,
)
from fastapi.responses import (
    PlainTextResponse,
)
from fastapi.staticfiles import (
    StaticFiles,
)
from fastapi.templating import (
    Jinja2Templates,
)
from starlette.middleware.trustedhost import (
    TrustedHostMiddleware,
)

_WEB_ROOT = Path(
    __file__
).resolve().parent

_ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]


def create_http_app() -> FastAPI:
    """Create the dependency-free-of-domain HTTP foundation."""

    app = FastAPI(
        title="Proteomics CSV Validation",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_ALLOWED_HOSTS,
        www_redirect=False,
    )

    app.mount(
        "/static",
        StaticFiles(
            directory=str(
                _WEB_ROOT
                / "static"
            ),
            check_dir=True,
        ),
        name="static",
    )

    app.state.templates = (
        Jinja2Templates(
            directory=str(
                _WEB_ROOT
                / "templates"
            )
        )
    )

    @app.get(
        "/health",
        include_in_schema=False,
        response_class=PlainTextResponse,
    )
    async def health() -> PlainTextResponse:
        return PlainTextResponse(
            "ok"
        )

    return app
