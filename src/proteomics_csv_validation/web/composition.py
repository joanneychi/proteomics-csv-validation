"""Composition entry point for the local browser application."""

from __future__ import annotations

from pathlib import Path

from starlette.types import (
    ASGIApp,
)

from proteomics_csv_validation.review_composition import (
    build_review_workflow,
)
from proteomics_csv_validation.web.app import (
    create_http_app,
)
from proteomics_csv_validation.web.review import (
    create_review_runtime,
)
from proteomics_csv_validation.web.security import (
    SecurityHeadersMiddleware,
)


def create_app(
    *,
    data_root: Path | None = None,
    csrf_secret: bytes | None = None,
) -> ASGIApp:
    """Construct the browser application with global response hardening."""

    runtime = create_review_runtime(
        data_root=data_root,
        csrf_secret=csrf_secret,
    )

    workflow = build_review_workflow(
        runtime.data_root
    )

    return SecurityHeadersMiddleware(
        create_http_app(
            runtime=runtime,
            workflow=workflow,
        )
    )
