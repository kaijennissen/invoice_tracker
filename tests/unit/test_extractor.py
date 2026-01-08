"""Tests for invoice_tracker.extractor module."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_tracker.extractor import (
    EXTRACTION_PROMPT,
    check_ollama_connection,
    extract_invoice,
)
from invoice_tracker.settings import ExtractionError, InvoiceData, Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing.

    Returns
    -------
    Settings
        Settings instance configured for testing.
    """
    return Settings(_cli_parse_args=False)


@pytest.fixture
def sample_invoice_json() -> str:
    """Return sample invoice JSON response.

    Returns
    -------
    str
        JSON string representing extracted invoice data.
    """
    return """{
        "party": "Test Corp",
        "invoice_id": "INV-2024-001",
        "issue_date": "2024-01-15",
        "due_date": "2024-02-15",
        "amount": "1234.56",
        "currency": "EUR",
        "recipient": "John Doe"
    }"""


class TestCheckOllamaConnection:
    """Tests for check_ollama_connection function."""

    def test_returns_true_when_model_available(
        self, mock_settings: Settings
    ) -> None:
        """check_ollama_connection returns True when model is available."""
        mock_model = MagicMock()
        mock_model.model = mock_settings.ollama_model
        mock_models_response = MagicMock()
        mock_models_response.models = [mock_model]

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.list.return_value = mock_models_response

            result = check_ollama_connection(mock_settings)

            assert result is True

    def test_returns_false_when_model_not_available(
        self, mock_settings: Settings
    ) -> None:
        """check_ollama_connection returns False when model is not available."""
        mock_model = MagicMock()
        mock_model.model = "other-model"
        mock_models_response = MagicMock()
        mock_models_response.models = [mock_model]

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.list.return_value = mock_models_response

            result = check_ollama_connection(mock_settings)

            assert result is False

    def test_returns_false_on_connection_error(
        self, mock_settings: Settings
    ) -> None:
        """check_ollama_connection returns False on connection error."""
        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.list.side_effect = Exception("Connection failed")

            result = check_ollama_connection(mock_settings)

            assert result is False


class TestExtractInvoice:
    """Tests for extract_invoice function."""

    def test_extracts_invoice_data_successfully(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice returns InvoiceData on successful extraction."""
        # Create a dummy image file
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            result = extract_invoice(image_path, mock_settings)

            assert isinstance(result, InvoiceData)
            assert result.party == "Test Corp"
            assert result.invoice_id == "INV-2024-001"
            assert result.issue_date == date(2024, 1, 15)
            assert result.amount == Decimal("1234.56")

    def test_raises_file_not_found_for_missing_image(
        self, mock_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice raises FileNotFoundError for missing image."""
        image_path = tmp_path / "nonexistent.png"

        with pytest.raises(FileNotFoundError, match="Image file not found"):
            extract_invoice(image_path, mock_settings)

    def test_raises_extraction_error_on_empty_response(
        self, mock_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice raises ExtractionError on empty response."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_response = MagicMock()
        mock_response.message.content = None

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            with pytest.raises(ExtractionError, match="Empty response"):
                extract_invoice(image_path, mock_settings)

    def test_raises_extraction_error_on_invalid_json(
        self, mock_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice raises ExtractionError on invalid JSON response."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_response = MagicMock()
        mock_response.message.content = "not valid json"

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            with pytest.raises(ExtractionError, match="Failed to extract"):
                extract_invoice(image_path, mock_settings)

    def test_retries_on_failure(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice retries on transient failures."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            # Fail twice, then succeed
            mock_client.return_value.chat.side_effect = [
                Exception("Transient error"),
                Exception("Transient error"),
                mock_response,
            ]

            with patch("invoice_tracker.extractor.time.sleep"):
                result = extract_invoice(image_path, mock_settings)

                assert isinstance(result, InvoiceData)
                assert mock_client.return_value.chat.call_count == 3

    def test_calls_ollama_with_correct_parameters(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice calls Ollama with correct parameters."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extract_invoice(image_path, mock_settings)

            mock_client.return_value.chat.assert_called_once()
            call_kwargs = mock_client.return_value.chat.call_args.kwargs
            assert call_kwargs["model"] == mock_settings.ollama_model
            assert call_kwargs["format"] == InvoiceData.model_json_schema()
            assert call_kwargs["options"] == {"temperature": 0}


class TestExtractionPrompt:
    """Tests for extraction prompt constant."""

    def test_prompt_contains_required_fields(self) -> None:
        """EXTRACTION_PROMPT should mention all required fields."""
        required_fields = [
            "party",
            "invoice_id",
            "issue_date",
            "due_date",
            "amount",
            "currency",
            "recipient",
        ]

        for field in required_fields:
            assert field in EXTRACTION_PROMPT
