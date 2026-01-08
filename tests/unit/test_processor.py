"""Tests for invoice_tracker.processor module."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from invoice_tracker.processor import (
    create_record,
    move_file,
    process_batch,
    process_single,
    scan_incoming,
)
from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    InvoiceRecord,
    Settings,
)


@pytest.fixture
def processor_settings(tmp_path: Path) -> Settings:
    """Create test settings with temporary directories.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary path fixture.

    Returns
    -------
    Settings
        Settings configured for testing.
    """
    incoming = tmp_path / "incoming"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    excel_file = tmp_path / "data" / "tracker.xlsx"

    incoming.mkdir(parents=True)
    processed.mkdir(parents=True)
    failed.mkdir(parents=True)
    excel_file.parent.mkdir(parents=True)

    return Settings(
        _cli_parse_args=False,
        incoming_dir=incoming,
        processed_dir=processed,
        failed_dir=failed,
        excel_file=excel_file,
    )


class TestScanIncoming:
    """Tests for scan_incoming function."""

    def test_returns_empty_list_for_missing_directory(
        self, tmp_path: Path
    ) -> None:
        """scan_incoming returns empty list if directory doesn't exist."""
        settings = Settings(
            _cli_parse_args=False,
            incoming_dir=tmp_path / "nonexistent",
        )

        result = scan_incoming(settings)

        assert result == []

    def test_returns_empty_list_for_empty_directory(
        self, processor_settings: Settings
    ) -> None:
        """scan_incoming returns empty list for directory with no images."""
        result = scan_incoming(processor_settings)

        assert result == []

    def test_finds_supported_extensions(self, processor_settings: Settings) -> None:
        """scan_incoming finds files with supported extensions."""
        # Create test files
        (processor_settings.incoming_dir / "invoice1.png").touch()
        (processor_settings.incoming_dir / "invoice2.jpg").touch()
        (processor_settings.incoming_dir / "invoice3.jpeg").touch()
        (processor_settings.incoming_dir / "document.pdf").touch()  # unsupported

        result = scan_incoming(processor_settings)

        assert len(result) == 3
        names = {f.name for f in result}
        assert "invoice1.png" in names
        assert "invoice2.jpg" in names
        assert "invoice3.jpeg" in names
        assert "document.pdf" not in names

    def test_finds_uppercase_extensions(self, processor_settings: Settings) -> None:
        """scan_incoming finds files with uppercase extensions."""
        (processor_settings.incoming_dir / "invoice.PNG").touch()
        (processor_settings.incoming_dir / "invoice.JPG").touch()

        result = scan_incoming(processor_settings)

        assert len(result) == 2

    def test_returns_sorted_list(self, processor_settings: Settings) -> None:
        """scan_incoming returns files in sorted order."""
        (processor_settings.incoming_dir / "c.png").touch()
        (processor_settings.incoming_dir / "a.png").touch()
        (processor_settings.incoming_dir / "b.png").touch()

        result = scan_incoming(processor_settings)

        names = [f.name for f in result]
        assert names == ["a.png", "b.png", "c.png"]


class TestMoveFile:
    """Tests for move_file function."""

    def test_moves_file_to_destination(self, tmp_path: Path) -> None:
        """move_file moves file to destination directory."""
        source = tmp_path / "source.png"
        source.touch()
        dest_dir = tmp_path / "destination"

        result = move_file(source, dest_dir)

        assert result == dest_dir / "source.png"
        assert result.exists()
        assert not source.exists()

    def test_creates_destination_directory(self, tmp_path: Path) -> None:
        """move_file creates destination directory if needed."""
        source = tmp_path / "source.png"
        source.touch()
        dest_dir = tmp_path / "nested" / "destination"

        result = move_file(source, dest_dir)

        assert result.parent.exists()
        assert result.exists()

    def test_handles_name_conflicts(self, tmp_path: Path) -> None:
        """move_file handles name conflicts by appending suffix."""
        source1 = tmp_path / "source.png"
        source1.write_text("file1")
        dest_dir = tmp_path / "destination"
        dest_dir.mkdir()

        # Move first file
        result1 = move_file(source1, dest_dir)
        assert result1.name == "source.png"

        # Create another file with same name
        source2 = tmp_path / "source.png"
        source2.write_text("file2")

        # Move second file - should get renamed
        result2 = move_file(source2, dest_dir)
        assert result2.name == "source_1.png"

        # Verify both files exist with correct content
        assert result1.read_text() == "file1"
        assert result2.read_text() == "file2"


class TestCreateRecord:
    """Tests for create_record function."""

    def test_creates_record_with_metadata(
        self, sample_invoice_data: InvoiceData, tmp_path: Path
    ) -> None:
        """create_record adds source_file and processed_at metadata."""
        source_file = tmp_path / "invoice.png"

        record = create_record(sample_invoice_data, source_file)

        assert isinstance(record, InvoiceRecord)
        assert record.party == sample_invoice_data.party
        assert record.invoice_id == sample_invoice_data.invoice_id
        assert record.source_file == "invoice.png"
        assert isinstance(record.processed_at, datetime)


class TestProcessSingle:
    """Tests for process_single function."""

    def test_successful_processing(
        self, processor_settings: Settings, sample_invoice_data: InvoiceData
    ) -> None:
        """process_single returns success for valid invoice."""
        # Create test file
        invoice_file = processor_settings.incoming_dir / "test.png"
        invoice_file.touch()

        with patch(
            "invoice_tracker.processor.extract_invoice"
        ) as mock_extract:
            mock_extract.return_value = sample_invoice_data

            result = process_single(invoice_file, processor_settings)

            assert result.success is True
            assert result.data == sample_invoice_data
            assert not invoice_file.exists()  # Moved
            assert (
                processor_settings.processed_dir / "test.png"
            ).exists()

    def test_extraction_failure_moves_to_failed(
        self, processor_settings: Settings
    ) -> None:
        """process_single moves file to failed on extraction error."""
        invoice_file = processor_settings.incoming_dir / "test.png"
        invoice_file.touch()

        with patch(
            "invoice_tracker.processor.extract_invoice"
        ) as mock_extract:
            mock_extract.side_effect = ExtractionError("Test error")

            result = process_single(invoice_file, processor_settings)

            assert result.success is False
            assert "Extraction failed" in result.error  # type: ignore[operator]
            assert not invoice_file.exists()
            assert (processor_settings.failed_dir / "test.png").exists()

    def test_dry_run_does_not_persist(
        self, processor_settings: Settings, sample_invoice_data: InvoiceData
    ) -> None:
        """process_single doesn't persist or move files in dry run mode."""
        processor_settings.dry_run = True
        invoice_file = processor_settings.incoming_dir / "test.png"
        invoice_file.touch()

        with patch(
            "invoice_tracker.processor.extract_invoice"
        ) as mock_extract:
            mock_extract.return_value = sample_invoice_data

            result = process_single(invoice_file, processor_settings)

            assert result.success is True
            assert invoice_file.exists()  # Not moved
            assert not processor_settings.excel_file.exists()  # Not persisted

    def test_duplicate_leaves_file_in_incoming(
        self, processor_settings: Settings, sample_invoice_data: InvoiceData
    ) -> None:
        """process_single leaves duplicate invoices in incoming."""
        invoice_file = processor_settings.incoming_dir / "test.png"
        invoice_file.touch()

        with (
            patch("invoice_tracker.processor.extract_invoice") as mock_extract,
            patch("invoice_tracker.processor.invoice_exists") as mock_exists,
            patch("invoice_tracker.processor.init_excel"),
        ):
            mock_extract.return_value = sample_invoice_data
            mock_exists.return_value = True

            result = process_single(invoice_file, processor_settings)

            assert result.success is False
            assert "Duplicate invoice" in result.error  # type: ignore[operator]
            assert invoice_file.exists()  # Still in incoming


class TestProcessBatch:
    """Tests for process_batch function."""

    def test_processes_all_files(
        self, processor_settings: Settings, sample_invoice_data: InvoiceData
    ) -> None:
        """process_batch processes all files in incoming directory."""
        # Create test files
        (processor_settings.incoming_dir / "invoice1.png").touch()
        (processor_settings.incoming_dir / "invoice2.png").touch()

        with patch(
            "invoice_tracker.processor.extract_invoice"
        ) as mock_extract:
            # Return different invoice IDs to avoid duplicates
            mock_extract.side_effect = [
                InvoiceData(
                    party="Company A",
                    invoice_id="INV-001",
                    issue_date=date(2024, 1, 1),
                    due_date=date(2024, 2, 1),
                    amount=Decimal("100"),
                    currency="EUR",
                    recipient="Test",
                ),
                InvoiceData(
                    party="Company B",
                    invoice_id="INV-002",
                    issue_date=date(2024, 1, 1),
                    due_date=date(2024, 2, 1),
                    amount=Decimal("200"),
                    currency="EUR",
                    recipient="Test",
                ),
            ]

            results = process_batch(processor_settings)

            assert len(results) == 2
            assert all(r.success for r in results)

    def test_returns_empty_list_for_no_files(
        self, processor_settings: Settings
    ) -> None:
        """process_batch returns empty list when no files to process."""
        results = process_batch(processor_settings)

        assert results == []

    def test_continues_on_individual_failures(
        self, processor_settings: Settings, sample_invoice_data: InvoiceData
    ) -> None:
        """process_batch continues processing after individual failures."""
        (processor_settings.incoming_dir / "bad.png").touch()
        (processor_settings.incoming_dir / "good.png").touch()

        with patch(
            "invoice_tracker.processor.extract_invoice"
        ) as mock_extract:
            mock_extract.side_effect = [
                ExtractionError("Failed"),
                sample_invoice_data,
            ]

            results = process_batch(processor_settings)

            assert len(results) == 2
            assert not results[0].success  # First failed
            assert results[1].success  # Second succeeded
