"""Server-rendered Review controller for the local browser workflow."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import tempfile
from typing import Any

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)
from starlette.responses import (
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from proteomics_csv_validation.application.browser_review import (
    ReviewResultNotFound,
    ReviewSubmission,
    ReviewSubmissionError,
    ReviewWorkflowPort,
    ReviewHistoryUnavailable,
)

from proteomics_csv_validation.application.browser_review import (
    ReviewComparisonIneligible,
    ReviewComparisonInvalid,
    ReviewComparisonUnavailable,
    ReviewExportIneligible,
    ReviewExportUnavailable,
    ReviewResultNotFound,
)
from proteomics_csv_validation.web.csrf import (
    issue_csrf_token,
    request_has_trusted_origin,
    validate_csrf_token,
)

_CSV_LIMIT = 10_000_000
_MAPPING_LIMIT = 1_000_000
_COPY_CHUNK = 64 * 1024

_RUN_ID = re.compile(
    r"[0-9a-f]{32}"
)

_PROFILE_OPTIONS = (
    (
        "0.2.0",
        "Processed Sample Summary",
        False,
    ),
    (
        "0.3.0",
        "Reduced Metadata",
        False,
    ),
    (
        "0.1.0",
        "Processed Sample Summary",
        True,
    ),
)

_MAPPING_MODES = (
    "strict",
    "automatic",
    "explicit",
)


class UploadLimitError(
    ValueError
):
    """Raised when one staged upload exceeds its bounded byte contract."""

    def __init__(
        self,
        field_id: str,
    ) -> None:
        super().__init__(
            "Uploaded file exceeds the permitted byte limit."
        )

        self.field_id = field_id


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewRuntime:
    """Process-local browser runtime configuration."""

    data_root: Path
    csrf_secret: bytes

    @property
    def staging_root(
        self,
    ) -> Path:
        return (
            self.data_root
            / "staging"
        )


@dataclass(
    frozen=True,
    slots=True,
)
class _StagedEvidence:
    display_name: str
    sha256: str
    byte_count: int


def default_data_root() -> Path:
    """Return the platform-local per-user application data root."""

    system = platform.system()

    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "proteomics-csv-validation"
        )

    if system == "Windows":
        local = os.environ.get(
            "LOCALAPPDATA"
        )

        if not local:
            raise RuntimeError(
                "LOCALAPPDATA is required on Windows."
            )

        return (
            Path(local)
            / "proteomics-csv-validation"
        )

    xdg = os.environ.get(
        "XDG_DATA_HOME"
    )

    base = (
        Path(xdg)
        if xdg
        else (
            Path.home()
            / ".local"
            / "share"
        )
    )

    return (
        base
        / "proteomics-csv-validation"
    )


def create_review_runtime(
    *,
    data_root: Path | None = None,
    csrf_secret: bytes | None = None,
) -> ReviewRuntime:
    """Create the non-I/O Review runtime configuration."""

    root = (
        default_data_root()
        if data_root is None
        else data_root
    )

    if not isinstance(
        root,
        Path,
    ):
        raise TypeError(
            "data_root must be a pathlib.Path."
        )

    if not root.is_absolute():
        raise ValueError(
            "data_root must be absolute."
        )

    secret = (
        secrets.token_bytes(
            32
        )
        if csrf_secret is None
        else csrf_secret
    )

    if (
        not isinstance(
            secret,
            bytes,
        )
        or len(secret) < 32
    ):
        raise ValueError(
            "csrf_secret must contain at least 32 bytes."
        )

    return ReviewRuntime(
        data_root=root,
        csrf_secret=secret,
    )


def recover_review_runtime(
    runtime: ReviewRuntime,
    workflow: ReviewWorkflowPort,
) -> None:
    """Clean stale upload staging and recover interrupted durable runs."""

    runtime.data_root.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    runtime.staging_root.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    for child in runtime.staging_root.iterdir():
        if not child.name.startswith(
            "review-"
        ):
            continue

        if (
            child.is_symlink()
            or child.is_file()
        ):
            child.unlink(
                missing_ok=True
            )

        elif child.is_dir():
            shutil.rmtree(
                child
            )

    workflow.recover_interrupted_runs()


def _safe_display_name(
    raw_name: str | None,
) -> str:
    value = (
        raw_name
        or ""
    )

    value = (
        value.replace(
            "\\",
            "/",
        )
        .rsplit(
            "/",
            1,
        )[-1]
    )

    value = "".join(
        character
        for character in value
        if (
            character.isprintable()
            and character
            not in {
                "\r",
                "\n",
                "\x00",
            }
        )
    ).strip()

    name = (
        value
        or "upload"
    )

    if len(
        name
    ) > 255:
        raise ValueError(
            "The selected filename is not usable."
        )

    return name


async def _stage_upload(
    upload: UploadFile,
    target: Path,
    *,
    maximum_bytes: int,
    field_id: str,
) -> _StagedEvidence:
    digest = hashlib.sha256()
    byte_count = 0

    with target.open(
        "xb"
    ) as handle:
        while True:
            chunk = await upload.read(
                _COPY_CHUNK
            )

            if not chunk:
                break

            byte_count += len(
                chunk
            )

            if byte_count > maximum_bytes:
                raise UploadLimitError(
                    field_id
                )

            digest.update(
                chunk
            )

            handle.write(
                chunk
            )

    return _StagedEvidence(
        display_name=_safe_display_name(
            upload.filename
        ),
        sha256=digest.hexdigest(),
        byte_count=byte_count,
    )


def _review_context(
    request: Request,
    runtime: ReviewRuntime,
    *,
    values: dict[
        str,
        str,
    ] | None = None,
    errors: tuple[
        dict[
            str,
            str,
        ],
        ...,
    ] = (),
) -> dict[
    str,
    Any,
]:
    selected = {
        "profile_version": "0.2.0",
        "mapping_mode": "strict",
    }

    if values is not None:
        selected.update(
            values
        )

    return {
        "request": request,
        "csrf_token": issue_csrf_token(
            runtime.csrf_secret
        ),
        "profiles": _PROFILE_OPTIONS,
        "mapping_modes": _MAPPING_MODES,
        "values": selected,
        "errors": errors,
        "error_fields": {
            item[
                "field"
            ]
            for item in errors
            if item[
                "field"
            ]
        },
    }


def _render_review(
    templates: Jinja2Templates,
    request: Request,
    runtime: ReviewRuntime,
    *,
    values: dict[
        str,
        str,
    ] | None = None,
    errors: tuple[
        dict[
            str,
            str,
        ],
        ...,
    ] = (),
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context=_review_context(
            request,
            runtime,
            values=values,
            errors=errors,
        ),
        status_code=status_code,
    )


def _form_error(
    field: str,
    message: str,
) -> tuple[
    dict[
        str,
        str,
    ],
    ...,
]:
    return (
        {
            "field": field,
            "message": message,
        },
    )

def _review_form_shape_is_valid(
    items: tuple[
        tuple[
            str,
            object,
        ],
        ...,
    ],
) -> bool:
    """Return whether multipart items match the exact Review form shape."""

    text_fields = {
        "csrf_token",
        "profile_version",
        "mapping_mode",
    }

    file_fields = {
        "input_file",
        "mapping_file",
    }

    counts: dict[
        str,
        int,
    ] = {}

    for key, value in items:
        counts[
            key
        ] = (
            counts.get(
                key,
                0,
            )
            + 1
        )

        if isinstance(
            value,
            UploadFile,
        ):
            if key not in file_fields:
                return False

        else:
            if (
                key not in text_fields
                or not isinstance(
                    value,
                    str,
                )
            ):
                return False

    if any(
        counts.get(
            field,
            0,
        )
        != 1
        for field in text_fields
    ):
        return False

    if counts.get(
        "input_file",
        0,
    ) != 1:
        return False

    if counts.get(
        "mapping_file",
        0,
    ) > 1:
        return False

    return True


def _redirect_to_result(
    run_id: str,
) -> RedirectResponse:
    return RedirectResponse(
        url=(
            "/results/"
            + run_id
        ),
        status_code=303,
    )


def _render_workflow_error(
    templates: Jinja2Templates,
    request: Request,
    *,
    title: str,
    heading: str,
    message: str,
    status_code: int,
) -> Response:
    """Render one user-facing GET workflow failure without internal details."""

    response = templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "request": request,
            "title": title,
            "heading": heading,
            "message": message,
        },
        status_code=status_code,
    )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return response


def _render_compare_error(
    templates: Jinja2Templates,
    request: Request,
    *,
    left_value: str,
    right_value: str,
    message: str,
    status_code: int,
) -> Response:
    """Render one Compare GET failure while retaining both selections."""

    response = templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "request": request,
            "left_value": left_value,
            "right_value": right_value,
            "comparison": None,
            "error_message": message,
        },
        status_code=status_code,
    )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return response


def install_review_routes(
    app: FastAPI,
    *,
    templates: Jinja2Templates,
    runtime: ReviewRuntime,
    workflow: ReviewWorkflowPort,
) -> None:
    """Install the bounded Review vertical slice."""

    @app.get(
        "/",
        include_in_schema=False,
    )
    async def root() -> RedirectResponse:
        return RedirectResponse(
            url="/review",
            status_code=303,
        )

    @app.get(
        "/review",
        include_in_schema=False,
    )
    async def review_form(
        request: Request,
    ) -> Response:
        return _render_review(
            templates,
            request,
            runtime,
        )

    @app.post(
        "/reviews",
        include_in_schema=False,
    )
    async def submit_review(
        request: Request,
    ) -> Response:
        if not request_has_trusted_origin(
            request
        ):
            return PlainTextResponse(
                "Forbidden",
                status_code=403,
            )

        values = {
            "profile_version": "0.2.0",
            "mapping_mode": "strict",
        }

        try:
            async with request.form(
                max_files=2,
                max_fields=3,
                max_part_size=65_536,
            ) as form:
                form_items = tuple(
                    form.multi_items()
                )

                csrf_values = tuple(
                    value
                    for key, value
                    in form_items
                    if (
                        key
                        == "csrf_token"
                        and isinstance(
                            value,
                            str,
                        )
                    )
                )

                if (
                    len(
                        csrf_values
                    )
                    != 1
                    or not validate_csrf_token(
                        runtime.csrf_secret,
                        csrf_values[
                            0
                        ],
                    )
                ):
                    return PlainTextResponse(
                        "Forbidden",
                        status_code=403,
                    )

                if not _review_form_shape_is_valid(
                    form_items
                ):
                    return PlainTextResponse(
                        "Invalid multipart request.",
                        status_code=400,
                    )

                profile_raw = form.get(
                    "profile_version"
                )

                mapping_raw = form.get(
                    "mapping_mode"
                )

                profile_version = (
                    profile_raw
                    if isinstance(
                        profile_raw,
                        str,
                    )
                    else ""
                )

                mapping_mode = (
                    mapping_raw
                    if isinstance(
                        mapping_raw,
                        str,
                    )
                    else ""
                )

                values = {
                    "profile_version": (
                        profile_version
                    ),
                    "mapping_mode": (
                        mapping_mode
                    ),
                }

                allowed_profiles = {
                    value
                    for value, _, _
                    in _PROFILE_OPTIONS
                }

                if (
                    profile_version
                    not in allowed_profiles
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "profile-version",
                            "Select a supported review profile.",
                        ),
                        status_code=422,
                    )

                if (
                    mapping_mode
                    not in _MAPPING_MODES
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "mapping-mode",
                            "Select a supported column-mapping mode.",
                        ),
                        status_code=422,
                    )

                input_value = form.get(
                    "input_file"
                )

                mapping_value = form.get(
                    "mapping_file"
                )

                if not isinstance(
                    input_value,
                    UploadFile,
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "input-file",
                            "Select a CSV file to review.",
                        ),
                        status_code=422,
                    )

                try:
                    input_name = (
                        _safe_display_name(
                            input_value.filename
                        )
                    )

                except ValueError:
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "input-file",
                            (
                                "The selected filename must be "
                                "255 characters or fewer."
                            ),
                        ),
                        status_code=422,
                    )

                if not input_name.casefold().endswith(
                    ".csv"
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "input-file",
                            "The review input must use a .csv filename.",
                        ),
                        status_code=422,
                    )

                mapping_upload = (
                    mapping_value
                    if (
                        isinstance(
                            mapping_value,
                            UploadFile,
                        )
                        and bool(
                            mapping_value.filename
                        )
                    )
                    else None
                )

                if (
                    mapping_mode
                    == "explicit"
                    and mapping_upload
                    is None
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "mapping-file",
                            "Explicit mapping requires a JSON mapping file.",
                        ),
                        status_code=422,
                    )

                if (
                    mapping_mode
                    != "explicit"
                    and mapping_upload
                    is not None
                ):
                    return _render_review(
                        templates,
                        request,
                        runtime,
                        values=values,
                        errors=_form_error(
                            "mapping-file",
                            "A mapping file is used only with explicit mapping.",
                        ),
                        status_code=422,
                    )

                if mapping_upload is not None:
                    try:
                        mapping_name = (
                            _safe_display_name(
                                mapping_upload.filename
                            )
                        )

                    except ValueError:
                        return _render_review(
                            templates,
                            request,
                            runtime,
                            values=values,
                            errors=_form_error(
                                "mapping-file",
                                (
                                    "The selected filename must be "
                                    "255 characters or fewer."
                                ),
                            ),
                            status_code=422,
                        )

                    if not mapping_name.casefold().endswith(
                        ".json"
                    ):
                        return _render_review(
                            templates,
                            request,
                            runtime,
                            values=values,
                            errors=_form_error(
                                "mapping-file",
                                "The mapping input must use a .json filename.",
                            ),
                            status_code=422,
                        )

                runtime.data_root.mkdir(
                    mode=0o700,
                    parents=True,
                    exist_ok=True,
                )

                runtime.staging_root.mkdir(
                    mode=0o700,
                    parents=True,
                    exist_ok=True,
                )

                with tempfile.TemporaryDirectory(
                    prefix="review-",
                    dir=runtime.staging_root,
                ) as temporary:
                    temporary_root = Path(
                        temporary
                    )

                    input_path = (
                        temporary_root
                        / "input.csv"
                    )

                    source = await _stage_upload(
                        input_value,
                        input_path,
                        maximum_bytes=(
                            _CSV_LIMIT
                        ),
                        field_id="input-file",
                    )

                    mapping_path: (
                        Path
                        | None
                    ) = None

                    mapping_source: (
                        _StagedEvidence
                        | None
                    ) = None

                    if mapping_upload is not None:
                        mapping_path = (
                            temporary_root
                            / "mapping.json"
                        )

                        mapping_source = await _stage_upload(
                            mapping_upload,
                            mapping_path,
                            maximum_bytes=(
                                _MAPPING_LIMIT
                            ),
                            field_id=(
                                "mapping-file"
                            ),
                        )

                    try:
                        run_id = workflow.submit(
                            ReviewSubmission(
                                input_path=input_path,
                                profile_version=(
                                    profile_version
                                ),
                                mapping_mode=(
                                    mapping_mode
                                ),
                                source_display_name=(
                                    source.display_name
                                ),
                                source_sha256=(
                                    source.sha256
                                ),
                                source_byte_count=(
                                    source.byte_count
                                ),
                                mapping_path=(
                                    mapping_path
                                ),
                                mapping_display_name=(
                                    mapping_source.display_name
                                    if mapping_source
                                    is not None
                                    else None
                                ),
                                mapping_sha256=(
                                    mapping_source.sha256
                                    if mapping_source
                                    is not None
                                    else None
                                ),
                                mapping_byte_count=(
                                    mapping_source.byte_count
                                    if mapping_source
                                    is not None
                                    else None
                                ),
                            )
                        )

                    except ReviewSubmissionError:
                        return _render_review(
                            templates,
                            request,
                            runtime,
                            values=values,
                            errors=_form_error(
                                "input-file",
                                (
                                    "The structural review could not be completed "
                                    "for the submitted input. "
                                    "Review the file and selected options."
                                ),
                            ),
                            status_code=422,
                        )

                return _redirect_to_result(
                    run_id
                )

        except UploadLimitError as exc:
            return _render_review(
                templates,
                request,
                runtime,
                values=values,
                errors=_form_error(
                    exc.field_id,
                    "An uploaded file exceeds the permitted size.",
                ),
                status_code=413,
            )

        except StarletteHTTPException as exc:
            if exc.status_code in {
                400,
                413,
            }:
                return PlainTextResponse(
                    "Invalid multipart request.",
                    status_code=(
                        exc.status_code
                    ),
                )

            raise

    @app.get(
        "/history",
        include_in_schema=False,
    )
    async def review_history(
        request: Request,
    ) -> Response:
        unavailable = False

        try:
            entries = workflow.history()

        except ReviewHistoryUnavailable:
            entries = ()
            unavailable = True

        history_rows = tuple(
            {
                "run_id": entry.run_id,
                "configuration_id": (
                    entry.configuration_id
                ),
                "configuration_sha256": (
                    entry.configuration_sha256
                ),
                "status": entry.status,
                "created_at": entry.created_at,
                "started_at": entry.started_at,
                "finished_at": entry.finished_at,
                "source_display_name": (
                    entry.source_display_name
                ),
                "source_sha256": (
                    entry.source_sha256
                ),
                "source_byte_count": (
                    entry.source_byte_count
                ),
                "profile_version": (
                    entry.profile_version
                ),
                "mapping_mode": (
                    entry.mapping_mode
                ),
            }
            for entry in entries
        )

        response = templates.TemplateResponse(
            request=request,
            name="history.html",
            context={
                "request": request,
                "history": history_rows,
                "history_unavailable": (
                    unavailable
                ),
            },
            status_code=(
                503
                if unavailable
                else 200
            ),
        )

        response.headers[
            "Cache-Control"
        ] = "no-store"

        return response

    @app.get(
        "/results/{run_id}",
        include_in_schema=False,
    )
    async def result_detail(
        request: Request,
        run_id: str,
    ) -> Response:
        if (
            _RUN_ID.fullmatch(
                run_id
            )
            is None
        ):
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Review result not found",
                heading="Review result not found",
                message=(
                    "The requested review result could not be found."
                ),
                status_code=404,
            )

        try:
            view = workflow.result(
                run_id
            )

        except ReviewResultNotFound:
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Review result not found",
                heading="Review result not found",
                message=(
                    "The requested review result could not be found."
                ),
                status_code=404,
            )

        artifact = (
            {
                "sha256": (
                    view.artifact_sha256
                ),
                "byte_count": (
                    view.artifact_byte_count
                ),
                "schema_id": (
                    view.artifact_schema_id
                ),
                "schema_version": (
                    view.artifact_schema_version
                ),
            }
            if view.artifact_sha256
            is not None
            else None
        )

        context = {
            "request": request,
            "result": {
                "run_id": view.run_id,
                "configuration_id": (
                    view.configuration_id
                ),
                "status": view.status,
                "started_at": (
                    view.started_at
                ),
                "finished_at": (
                    view.finished_at
                ),
                "artifact": artifact,
                "total_findings": (
                    view.total_findings
                ),
                "validation_status": (
                    view.validation_status
                ),
                "evidence_available": (
                    view.evidence_available
                ),
                "configuration": (
                    view.configuration
                ),
                "validation": (
                    view.validation
                ),
            },
        }

        if (
            view.status
            == "SUCCEEDED"
            and not view.evidence_available
        ):
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Review evidence unavailable",
                heading="Review evidence unavailable",
                message=(
                    "Verified result evidence is unavailable for this "
                    "completed review. Detailed review evidence is withheld. "
                    "No scientific conclusion should be inferred from "
                    "this state."
                ),
                status_code=503,
            )

        return templates.TemplateResponse(
            request=request,
            name="result.html",
            context=context,
            status_code=200,
            headers={
                "Cache-Control": "no-store",
            },
        )

    @app.get(
        "/compare",
        include_in_schema=False,
    )
    async def compare_runs(
        request: Request,
        left: str | None = None,
        right: str | None = None,
    ) -> Response:
        left_value = (
            left
            if left is not None
            else ""
        )

        right_value = (
            right
            if right is not None
            else ""
        )

        left_invalid = bool(
            left_value
            and _RUN_ID.fullmatch(
                left_value
            )
            is None
        )

        right_invalid = bool(
            right_value
            and _RUN_ID.fullmatch(
                right_value
            )
            is None
        )

        if left_invalid or right_invalid:
            if left_invalid and right_invalid:
                message = (
                    "Left run ID and Right run ID are not valid review run IDs. "
                    "Enter a valid review run ID for each comparison side."
                )
            elif left_invalid:
                message = (
                    "Left run ID is not a valid review run ID. "
                    "Enter a valid review run ID for the left comparison side."
                )
            else:
                message = (
                    "Right run ID is not a valid review run ID. "
                    "Enter a valid review run ID for the right comparison side."
                )

            return _render_compare_error(
                request.app.state.templates,
                request,
                left_value=left_value,
                right_value=right_value,
                message=message,
                status_code=400,
            )

        comparison = None

        if (
            left_value
            and right_value
        ):
            if (
                left_value
                == right_value
            ):
                return _render_compare_error(
                    request.app.state.templates,
                    request,
                    left_value=left_value,
                    right_value=right_value,
                    message=(
                        "Select two distinct review runs to compare."
                    ),
                    status_code=400,
                )

            try:
                comparison = (
                    workflow.compare(
                        left_value,
                        right_value,
                    )
                )

            except ReviewComparisonInvalid:
                return _render_compare_error(
                    request.app.state.templates,
                    request,
                    left_value=left_value,
                    right_value=right_value,
                    message=(
                        "The selected comparison request could not be "
                        "accepted."
                    ),
                    status_code=400,
                )

            except ReviewResultNotFound:
                return _render_compare_error(
                    request.app.state.templates,
                    request,
                    left_value=left_value,
                    right_value=right_value,
                    message=(
                        "One or both selected review runs could not be "
                        "found."
                    ),
                    status_code=404,
                )

            except ReviewComparisonIneligible:
                return _render_compare_error(
                    request.app.state.templates,
                    request,
                    left_value=left_value,
                    right_value=right_value,
                    message=(
                        "Comparison requires two completed successful "
                        "review runs."
                    ),
                    status_code=409,
                )

            except ReviewComparisonUnavailable:
                return _render_compare_error(
                    request.app.state.templates,
                    request,
                    left_value=left_value,
                    right_value=right_value,
                    message=(
                        "Verified evidence is unavailable for one or both "
                        "selected runs, so the comparison cannot be "
                        "completed."
                    ),
                    status_code=503,
                )

        templates = (
            request.app.state.templates
        )

        return templates.TemplateResponse(
            request,
            "compare.html",
            {
                "left_value": (
                    left_value
                ),
                "right_value": (
                    right_value
                ),
                "comparison": (
                    comparison
                ),
            },
            headers={
                "Cache-Control": (
                    "no-store"
                )
            },
        )

    @app.get(
        "/results/{run_id}/export",
        include_in_schema=False,
    )
    async def export_result_bundle(
        request: Request,
        run_id: str,
    ) -> Response:
        if (
            _RUN_ID.fullmatch(
                run_id
            )
            is None
        ):
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Result Bundle export unavailable",
                heading="Result Bundle export unavailable",
                message=(
                    "The requested review result could not be found, "
                    "so no Result Bundle is available for export."
                ),
                status_code=404,
            )

        try:
            exported = (
                workflow.export_result(
                    run_id
                )
            )

        except ReviewResultNotFound:
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Result Bundle export unavailable",
                heading="Result Bundle export unavailable",
                message=(
                    "The requested review result could not be found, "
                    "so no Result Bundle is available for export."
                ),
                status_code=404,
            )

        except ReviewExportIneligible:
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Result Bundle export unavailable",
                heading="Result Bundle export unavailable",
                message=(
                    "Result Bundle export is available only for "
                    "completed successful reviews."
                ),
                status_code=409,
            )

        except ReviewExportUnavailable:
            return _render_workflow_error(
                request.app.state.templates,
                request,
                title="Result Bundle export unavailable",
                heading="Result Bundle export unavailable",
                message=(
                    "Verified result evidence is unavailable, so the "
                    "Result Bundle cannot be exported."
                ),
                status_code=503,
            )

        return Response(
            content=exported.payload,
            media_type=(
                exported.media_type
            ),
            headers={
                "Cache-Control": (
                    "no-store"
                ),
                "Content-Disposition": (
                    'attachment; filename="'
                    + exported.filename
                    + '"'
                ),
            },
        )
