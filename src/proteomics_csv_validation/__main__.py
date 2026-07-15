"""Module execution surface for the installed application."""

from __future__ import annotations

from proteomics_csv_validation.cli import main


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
