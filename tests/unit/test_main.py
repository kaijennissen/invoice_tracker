"""Tests for invoice_tracker.main module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from invoice_tracker.main import main
from invoice_tracker.settings import InvoiceData, ProcessingResult


def _make_mock_settings(
    *,
    verbose: bool = False,
    dry_run: bool = False,
    process: object | None = None,
    eval: object | None = None,
) -> MagicMock:
    """Create a mock Settings with subcommand fields."""
    mock = MagicMock()
    mock.verbose = verbose
    mock.dry_run = dry_run
    mock.process = process
    mock.eval = eval
    return mock


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
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings_cls.return_value = _make_mock_settings(process=process_cmd)
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
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings_cls.return_value = _make_mock_settings(process=process_cmd)
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
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings_cls.return_value = _make_mock_settings(process=process_cmd)
            mock_check.return_value = True
            mock_batch.return_value = [failed_result]

            result = main()

            assert result == 2

    def test_returns_two_on_ollama_connection_failure(self) -> None:
        """main returns 2 when Ollama is unreachable."""
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
        ):
            mock_settings = _make_mock_settings(process=process_cmd)
            mock_settings.ollama_url = "http://localhost:11434"
            mock_settings.ollama_model = "test-model"
            mock_settings_cls.return_value = mock_settings
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
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings_cls.return_value = _make_mock_settings(
                dry_run=True, process=process_cmd
            )
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
        process_cmd = MagicMock()
        process_cmd.file = test_file

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_single") as mock_single,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings = _make_mock_settings(process=process_cmd)
            mock_settings_cls.return_value = mock_settings
            mock_check.return_value = True
            mock_single.return_value = successful_result

            result = main()

            assert result == 0
            mock_single.assert_called_once_with(test_file, mock_settings)
            mock_batch.assert_not_called()

    def test_returns_zero_when_no_files(self) -> None:
        """main returns 0 when there are no files to process."""
        process_cmd = MagicMock()
        process_cmd.file = None

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.main.check_ollama_connection") as mock_check,
            patch("invoice_tracker.main.process_batch") as mock_batch,
        ):
            mock_settings_cls.return_value = _make_mock_settings(process=process_cmd)
            mock_check.return_value = True
            mock_batch.return_value = []

            result = main()

            assert result == 0

    def test_no_subcommand_prints_usage(self) -> None:
        """main returns 2 and prints usage when no subcommand is given."""
        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value = _make_mock_settings()

            result = main()

            assert result == 2

    def test_eval_subcommand(self) -> None:
        """main dispatches to eval subcommand."""
        eval_cmd = MagicMock()
        eval_cmd.ground_truth = Path("data/evaluation/ground_truth.json")
        eval_cmd.methods = ["baml"]
        eval_cmd.models = ["gemma3:27b"]

        with (
            patch("invoice_tracker.main.Settings") as mock_settings_cls,
            patch("invoice_tracker.evaluation.run_evaluation") as mock_run,
            patch("invoice_tracker.evaluation.print_summary"),
        ):
            mock_settings = _make_mock_settings(eval=eval_cmd)
            mock_settings_cls.return_value = mock_settings
            mock_run.return_value = {}

            result = main()

            assert result == 0
            mock_run.assert_called_once_with(
                eval_cmd.ground_truth,
                eval_cmd.methods,
                mock_settings,
                models=eval_cmd.models,
            )
