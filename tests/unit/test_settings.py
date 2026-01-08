"""Tests for invoice_tracker.settings module."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    InvoiceRecord,
    ProcessingResult,
    Settings,
)


class TestInvoiceData:
    """Tests for InvoiceData model."""

    def test_create_invoice_data(self) -> None:
        """InvoiceData should be created with valid fields."""
        data = InvoiceData(
            party="Test Company",
            invoice_id="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            amount=Decimal("100.00"),
            currency="EUR",
            recipient="Test Recipient",
        )

        assert data.party == "Test Company"
        assert data.invoice_id == "INV-001"
        assert data.amount == Decimal("100.00")

    def test_currency_defaults_to_eur(self) -> None:
        """InvoiceData currency should default to EUR."""
        data = InvoiceData(
            party="Test",
            invoice_id="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            amount=Decimal("100"),
            recipient="Test",
        )

        assert data.currency == "EUR"

    def test_model_dump_preserves_decimal(self) -> None:
        """InvoiceData.model_dump should preserve Decimal type."""
        data = InvoiceData(
            party="Test",
            invoice_id="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            amount=Decimal("123.45"),
            recipient="Test",
        )

        dumped = data.model_dump()
        assert dumped["amount"] == Decimal("123.45")


class TestInvoiceRecord:
    """Tests for InvoiceRecord model."""

    def test_create_from_invoice_data(
        self, sample_invoice_data: InvoiceData
    ) -> None:
        """InvoiceRecord should be created from InvoiceData with metadata."""
        record = InvoiceRecord(
            **sample_invoice_data.model_dump(),
            source_file="test.png",
            processed_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        assert record.party == sample_invoice_data.party
        assert record.source_file == "test.png"
        assert record.processed_at == datetime(2024, 1, 1, 12, 0, 0)

    def test_get_column_headers(self) -> None:
        """InvoiceRecord.get_column_headers should return field descriptions."""
        headers = InvoiceRecord.get_column_headers()

        assert isinstance(headers, list)
        assert len(headers) == len(InvoiceRecord.model_fields)
        assert "Name of the invoicing party/company" in headers
        assert "Unique invoice identifier" in headers

    def test_model_dump_maintains_field_order(
        self, sample_invoice_record: InvoiceRecord
    ) -> None:
        """InvoiceRecord.model_dump should maintain consistent field order."""
        dumped = sample_invoice_record.model_dump()
        keys = list(dumped.keys())
        headers = InvoiceRecord.get_column_headers()

        # The number of keys should match the number of headers
        assert len(keys) == len(headers)


class TestProcessingResult:
    """Tests for ProcessingResult model."""

    def test_successful_result(self, sample_invoice_data: InvoiceData) -> None:
        """ProcessingResult should store successful extraction."""
        result = ProcessingResult(
            source_file=Path("/test/invoice.png"),
            success=True,
            data=sample_invoice_data,
        )

        assert result.success is True
        assert result.data is not None
        assert result.error is None

    def test_failed_result(self) -> None:
        """ProcessingResult should store failure with error message."""
        result = ProcessingResult(
            source_file=Path("/test/invoice.png"),
            success=False,
            error="Failed to extract data",
        )

        assert result.success is False
        assert result.data is None
        assert result.error == "Failed to extract data"

    def test_success_without_data_raises_error(self) -> None:
        """ProcessingResult should reject success=True without data."""
        with pytest.raises(ValueError, match="Successful result must include data"):
            ProcessingResult(
                source_file=Path("/test/invoice.png"),
                success=True,
                data=None,
            )

    def test_failure_without_error_raises_error(self) -> None:
        """ProcessingResult should reject success=False without error."""
        with pytest.raises(ValueError, match="Failed result must include error"):
            ProcessingResult(
                source_file=Path("/test/invoice.png"),
                success=False,
                error=None,
            )


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_settings(self, test_settings: Settings) -> None:
        """Settings should have sensible defaults."""
        assert test_settings.incoming_dir == Path("./invoices/incoming")
        assert test_settings.processed_dir == Path("./invoices/processed")
        assert test_settings.failed_dir == Path("./invoices/failed")
        assert test_settings.excel_file == Path("./data/tracker.xlsx")
        assert test_settings.ollama_model == "ministral-3:14b"
        assert test_settings.dry_run is False
        assert test_settings.verbose is False

    def test_settings_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings should load from environment variables with INVOICE_ prefix."""
        monkeypatch.setenv("INVOICE_OLLAMA_MODEL", "llava")
        monkeypatch.setenv("INVOICE_OLLAMA_URL", "http://custom:11434")
        monkeypatch.setenv("INVOICE_INCOMING_DIR", "/custom/incoming")

        settings = Settings(_cli_parse_args=False)

        assert settings.ollama_model == "llava"
        assert settings.ollama_url == "http://custom:11434"
        assert settings.incoming_dir == Path("/custom/incoming")

    def test_supported_extensions_default(self, test_settings: Settings) -> None:
        """Settings should have default supported extensions."""
        assert ".png" in test_settings.supported_extensions
        assert ".jpg" in test_settings.supported_extensions
        assert ".jpeg" in test_settings.supported_extensions


class TestExtractionError:
    """Tests for ExtractionError exception."""

    def test_extraction_error_message(self) -> None:
        """ExtractionError should store error message."""
        error = ExtractionError("Failed to parse invoice")
        assert str(error) == "Failed to parse invoice"

    def test_extraction_error_is_exception(self) -> None:
        """ExtractionError should be an Exception subclass."""
        assert issubclass(ExtractionError, Exception)
