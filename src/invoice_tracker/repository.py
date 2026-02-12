"""Repository abstraction for invoice persistence.

This module defines the InvoiceRepository protocol and provides an Excel-based
implementation. The protocol enables swapping persistence backends (e.g., SQLite
in Phase 2) without changing the orchestration layer.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from invoice_tracker.excel_handler import append_invoice, init_excel, invoice_exists
from invoice_tracker.settings import InvoiceRecord


@runtime_checkable
class InvoiceRepository(Protocol):
    """Protocol for invoice persistence backends.

    Any class implementing initialize, save, and exists can serve as a
    repository for the processing pipeline.
    """

    def initialize(self) -> None:
        """Ensure the backing store is ready (create if needed)."""
        ...

    def save(self, record: InvoiceRecord) -> None:
        """Persist an invoice record.

        Parameters
        ----------
        record : InvoiceRecord
            The invoice record to save.
        """
        ...

    def exists(self, invoice_id: str) -> bool:
        """Check whether an invoice ID already exists.

        Parameters
        ----------
        invoice_id : str
            The invoice ID to look up.

        Returns
        -------
        bool
            True if the invoice ID is already persisted.
        """
        ...


class ExcelRepository:
    """Excel-backed invoice repository.

    Delegates to the excel_handler module functions.

    Parameters
    ----------
    path : Path
        Path to the Excel file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def initialize(self) -> None:
        """Create the Excel file with headers if it doesn't exist."""
        init_excel(self._path)

    def save(self, record: InvoiceRecord) -> None:
        """Append an invoice record to the Excel file.

        Parameters
        ----------
        record : InvoiceRecord
            The invoice record to save.
        """
        append_invoice(self._path, record)

    def exists(self, invoice_id: str) -> bool:
        """Check if an invoice ID exists in the Excel file.

        Parameters
        ----------
        invoice_id : str
            The invoice ID to look up.

        Returns
        -------
        bool
            True if the invoice ID is already in the file.
        """
        return invoice_exists(self._path, invoice_id)


def create_repository(path: Path) -> ExcelRepository:
    """Create the default repository for the given path.

    Parameters
    ----------
    path : Path
        Path to the persistence file.

    Returns
    -------
    ExcelRepository
        An Excel-backed repository instance.
    """
    return ExcelRepository(path)


__all__ = [
    "InvoiceRepository",
    "ExcelRepository",
    "create_repository",
]
