"""Shared test fixtures for invoice_tracker tests."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_tracker.settings import InvoiceData, InvoiceRecord, Settings


@pytest.fixture
def sample_invoice_data() -> InvoiceData:
    """Create sample invoice data for testing.

    Returns
    -------
    InvoiceData
        Sample invoice data with realistic values.
    """
    return InvoiceData(
        party="Acme Corp",
        invoice_id="INV-2024-001",
        issue_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        amount=Decimal("1234.56"),
        currency="EUR",
        recipient="John Doe",
    )


@pytest.fixture
def sample_invoice_record(sample_invoice_data: InvoiceData) -> InvoiceRecord:
    """Create sample invoice record for testing.

    Parameters
    ----------
    sample_invoice_data : InvoiceData
        Base invoice data fixture.

    Returns
    -------
    InvoiceRecord
        Sample invoice record with metadata.
    """
    return InvoiceRecord(
        **sample_invoice_data.model_dump(),
        source_file="invoice_001.png",
        processed_at=datetime(2024, 1, 15, 10, 30, 0),
    )


@pytest.fixture
def tmp_invoice_dir(tmp_path: Path) -> dict[str, Path]:
    """Create temporary invoice directory structure.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary path fixture.

    Returns
    -------
    dict[str, Path]
        Dictionary with paths for incoming, processed, failed dirs and excel file.
    """
    incoming = tmp_path / "invoices" / "incoming"
    processed = tmp_path / "invoices" / "processed"
    failed = tmp_path / "invoices" / "failed"
    data_dir = tmp_path / "data"

    incoming.mkdir(parents=True)
    processed.mkdir(parents=True)
    failed.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    return {
        "incoming": incoming,
        "processed": processed,
        "failed": failed,
        "excel_file": data_dir / "tracker.xlsx",
    }


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with CLI parsing disabled.

    Returns
    -------
    Settings
        Settings instance configured for testing.
    """
    return Settings(_cli_parse_args=False)
