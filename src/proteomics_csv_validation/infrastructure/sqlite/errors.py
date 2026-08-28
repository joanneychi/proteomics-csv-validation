"""SQLite ledger infrastructure errors."""

from __future__ import annotations


class LedgerError(Exception):
    """Base error for local ledger operations."""


class LedgerSchemaError(LedgerError):
    """Raised when ledger schema identity is unsupported."""


class LedgerIntegrityError(LedgerError):
    """Raised when ledger integrity verification fails."""
