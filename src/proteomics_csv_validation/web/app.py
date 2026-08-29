"""Secure HTTP shell for the local browser interface."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.body_limit import (
    RequestBodyLimitMiddleware,
)
from starlette.middleware.trustedhost import (
    TrustedHostMiddleware,
)

from proteomics_csv_validation.web.review import (
    ReviewRuntime,
    ReviewWorkflowPort,
    install_review_routes,
    recover_review_runtime,
)

_WEB_ROOT = Path(
    __file__
).resolve().parent

_ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]

_MAX_REQUEST_BYTES = 12_000_000


def create_http_app(
    *,
    runtime: ReviewRuntime | None = None,
    workflow: ReviewWorkflowPort | None = None,
) -> FastAPI:
    """Create the secure local HTTP application."""

    if (
        runtime is None
    ) != (
        workflow is None
    ):
        raise ValueError(
            "runtime and workflow must be supplied together."
        )

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        if (
            runtime is not None
            and workflow is not None
        ):
            recover_review_runtime(
                runtime,
                workflow,
            )

        yield

    app = FastAPI(
        title="Proteomics CSV Validation",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_size=(
            _MAX_REQUEST_BYTES
        ),
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

    if (
        runtime is not None
        and workflow is not None
    ):
        app.state.review_runtime = (
            runtime
        )

        app.state.review_workflow = (
            workflow
        )

        install_review_routes(
            app,
            templates=(
                app.state.templates
            ),
            runtime=runtime,
            workflow=workflow,
        )

    return app
