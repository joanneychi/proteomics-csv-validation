"""Composition root for the local browser application."""

from __future__ import annotations

from starlette.types import (
    ASGIApp,
)

from proteomics_csv_validation.web.app import (
    create_http_app,
)
from proteomics_csv_validation.web.security import (
    SecurityHeadersMiddleware,
)


def create_app() -> ASGIApp:
    """Construct the browser application with global response hardening."""

    return SecurityHeadersMiddleware(
        create_http_app()
    )
