"""Tests for invoice_tracker.main module."""

from pathlib import Path
from unittest.mock import patch

from invoice_tracker.main import main
from invoice_tracker.settings import InvoiceData, ProcessingResult


class TestMain:
    """Tests for main CLI function."""

    def test_returns_zero_on_success(
        self, tmp_path: Path, sample_invoice_data: InvoiceData
    ) -> None:
        """main returns 0 when all files process successfully."""
        successful_result = ProcessingResult(
            source_file=tmp_path / "test.png",
            success=True,
            data=sample_invoice_data,
        )

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = None
            mock_check.return_value = True
            mock_batch.return_value = [successful_result]

            result = main()

            assert result == 0

    def test_returns_one_on_partial_failure(
        self, tmp_path: Path, sample_invoice_data: InvoiceData
    ) -> None:
        """main returns 1 when some files fail."""
        successful_result = ProcessingResult(
            source_file=tmp_path / "good.png",
            success=True,
            data=sample_invoice_data,
        )
        failed_result = ProcessingResult(
            source_file=tmp_path / "bad.png",
            success=False,
            error="Extraction failed",
        )

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = None
            mock_check.return_value = True
            mock_batch.return_value = [successful_result, failed_result]

            result = main()

            assert result == 1

    def test_returns_two_on_all_failures(self, tmp_path: Path) -> None:
        """main returns 2 when all files fail."""
        failed_result = ProcessingResult(
            source_file=tmp_path / "bad.png",
            success=False,
            error="Extraction failed",
        )

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = None
            mock_check.return_value = True
            mock_batch.return_value = [failed_result]

            result = main()

            assert result == 2

    def test_returns_two_on_ollama_connection_failure(self) -> None:
        """main returns 2 when Ollama is unreachable."""
        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = None
            mock_settings.ollama_url = "http://localhost:11434"
            mock_settings.ollama_model = "test-model"
            mock_check.return_value = False

            result = main()

            assert result == 2

    def test_skips_ollama_check_in_dry_run(
        self, tmp_path: Path, sample_invoice_data: InvoiceData
    ) -> None:
        """main skips Ollama connection check in dry run mode."""
        successful_result = ProcessingResult(
            source_file=tmp_path / "test.png",
            success=True,
            data=sample_invoice_data,
        )

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = True
            mock_settings.file = None
            mock_batch.return_value = [successful_result]

            result = main()

            assert result == 0
            mock_check.assert_not_called()

    def test_processes_single_file_when_specified(
        self, tmp_path: Path, sample_invoice_data: InvoiceData
    ) -> None:
        """main processes single file when file argument is provided."""
        test_file = tmp_path / "single.png"
        successful_result = ProcessingResult(
            source_file=test_file,
            success=True,
            data=sample_invoice_data,
        )

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_single") as mock_single,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = test_file
            mock_check.return_value = True
            mock_single.return_value = successful_result

            result = main()

            assert result == 0
            mock_single.assert_called_once_with(test_file, mock_settings)
            mock_batch.assert_not_called()

    def test_returns_zero_when_no_files(self) -> None:
        """main returns 0 when there are no files to process."""
        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = mock_settings_cls.return_value
            mock_settings.verbose = False
            mock_settings.dry_run = False
            mock_settings.file = None
            mock_check.return_value = True
            mock_batch.return_value = []

            result = main()

            assert result == 0
