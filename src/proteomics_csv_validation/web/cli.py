"""Console launcher for the optional local browser interface."""

from __future__ import annotations

import argparse
from collections.abc import (
    Sequence,
)
import importlib.util
from importlib.metadata import (
    version,
)
import sys


_DISTRIBUTION_NAME = (
    "proteomics-csv-validation"
)

_LOOPBACK_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000

_REQUIRED_WEB_MODULES = (
    "fastapi",
    "uvicorn",
    "jinja2",
    "multipart",
)


def _port(
    value: str,
) -> int:
    try:
        port = int(
            value
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "port must be an integer."
        ) from exc

    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "port must be between 1024 and 65535."
        )

    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proteomics-csv-app",
        description=(
            "Run the local Proteomics CSV Validation "
            "browser application on loopback only."
        ),
    )

    parser.add_argument(
        "--port",
        type=_port,
        default=_DEFAULT_PORT,
        help=(
            "Local TCP port. "
            "Default: 8000."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=(
            "%(prog)s "
            + version(
                _DISTRIBUTION_NAME
            )
        ),
    )

    return parser


def _missing_web_modules() -> tuple[
    str,
    ...,
]:
    return tuple(
        module
        for module in _REQUIRED_WEB_MODULES
        if importlib.util.find_spec(
            module
        )
        is None
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Launch the optional web application on loopback."""

    args = _parser().parse_args(
        argv
    )

    missing = (
        _missing_web_modules()
    )

    if missing:
        print(
            "Web dependencies are not installed. "
            "Install "
            "'proteomics-csv-validation[web]' "
            "before starting the browser application.",
            file=sys.stderr,
        )
        return 2

    import uvicorn

    uvicorn.run(
        (
            "proteomics_csv_validation.web."
            "composition:create_app"
        ),
        factory=True,
        host=_LOOPBACK_HOST,
        port=args.port,
        reload=False,
        access_log=False,
        server_header=False,
        proxy_headers=False,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
