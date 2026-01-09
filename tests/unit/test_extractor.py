"""Tests for invoice_tracker.extractor module."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_tracker.extractor import (
    _simplify_schema,
    check_ollama_connection,
    extract_invoice,
    pdf_to_images,
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

    def test_returns_true_when_model_available(self, mock_settings: Settings) -> None:
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

    def test_returns_false_on_connection_error(self, mock_settings: Settings) -> None:
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

        with pytest.raises(FileNotFoundError, match="File not found"):
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
            assert call_kwargs["format"] == _simplify_schema(
                InvoiceData.model_json_schema()
            )
            assert call_kwargs["options"] == {"temperature": 0}


class TestExtractionSchema:
    """Tests for extraction schema generation."""

    def test_schema_contains_required_fields(self) -> None:
        """Extraction schema should contain all required fields."""
        schema = _simplify_schema(InvoiceData.model_json_schema())
        required_fields = [
            "party",
            "invoice_id",
            "issue_date",
            "due_date",
            "amount",
            "currency",
            "recipient",
        ]

        assert "properties" in schema
        for field in required_fields:
            assert field in schema["properties"]

    def test_schema_has_no_anyof(self) -> None:
        """Extraction schema should not contain anyOf patterns."""
        schema = _simplify_schema(InvoiceData.model_json_schema())

        for prop_schema in schema["properties"].values():
            assert "anyOf" not in prop_schema

    def test_amount_is_number_type(self) -> None:
        """Amount field should be simplified to number type."""
        schema = _simplify_schema(InvoiceData.model_json_schema())

        assert schema["properties"]["amount"]["type"] == "number"


class TestPdfToImages:
    """Tests for pdf_to_images function."""

    def test_raises_file_not_found_for_missing_pdf(self, tmp_path: Path) -> None:
        """pdf_to_images raises FileNotFoundError for missing PDF."""
        pdf_path = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            pdf_to_images(pdf_path)

    def test_converts_pdf_to_images(self, tmp_path: Path) -> None:
        """pdf_to_images converts PDF pages to PNG bytes."""
        # Create a mock PDF with fitz
        pdf_path = tmp_path / "test.pdf"

        # Create a simple PDF with one page
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((10, 50), "Test Invoice")
        doc.save(pdf_path)
        doc.close()

        # Act
        result = pdf_to_images(pdf_path)

        # Assert
        assert len(result) == 1
        assert isinstance(result[0], bytes)
        # PNG files start with specific magic bytes
        assert result[0][:8] == b"\x89PNG\r\n\x1a\n"

    def test_converts_multipage_pdf(self, tmp_path: Path) -> None:
        """pdf_to_images returns one image per page."""
        # Create a mock multi-page PDF
        pdf_path = tmp_path / "multipage.pdf"

        import fitz

        doc = fitz.open()
        doc.new_page(width=200, height=100)
        doc.new_page(width=200, height=100)
        doc.new_page(width=200, height=100)
        doc.save(pdf_path)
        doc.close()

        # Act
        result = pdf_to_images(pdf_path)

        # Assert
        assert len(result) == 3
        for page_bytes in result:
            assert isinstance(page_bytes, bytes)
            assert page_bytes[:8] == b"\x89PNG\r\n\x1a\n"


class TestExtractInvoicePdf:
    """Tests for extract_invoice with PDF files."""

    def test_extracts_from_pdf(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice extracts data from PDF files."""
        # Create a simple PDF
        pdf_path = tmp_path / "invoice.pdf"

        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Invoice PDF")
        doc.save(pdf_path)
        doc.close()

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            result = extract_invoice(pdf_path, mock_settings)

            assert isinstance(result, InvoiceData)
            assert result.party == "Test Corp"
            assert result.invoice_id == "INV-2024-001"

    def test_pdf_passes_bytes_to_ollama(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice passes bytes (not paths) to Ollama for PDFs."""
        pdf_path = tmp_path / "invoice.pdf"

        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extract_invoice(pdf_path, mock_settings)

            call_kwargs = mock_client.return_value.chat.call_args.kwargs
            images = call_kwargs["messages"][0]["images"]
            # Images should be bytes, not strings
            assert all(isinstance(img, bytes) for img in images)

    def test_image_passes_bytes_to_ollama(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice passes bytes (not paths) to Ollama for images."""
        image_path = tmp_path / "invoice.png"
        image_content = b"fake png content"
        image_path.write_bytes(image_content)

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extract_invoice(image_path, mock_settings)

            call_kwargs = mock_client.return_value.chat.call_args.kwargs
            images = call_kwargs["messages"][0]["images"]
            # Images should be bytes, not strings
            assert len(images) == 1
            assert images[0] == image_content

    def test_multipage_pdf_passes_all_pages(
        self, mock_settings: Settings, tmp_path: Path, sample_invoice_json: str
    ) -> None:
        """extract_invoice passes all PDF pages as images."""
        pdf_path = tmp_path / "multipage.pdf"

        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extract_invoice(pdf_path, mock_settings)

            call_kwargs = mock_client.return_value.chat.call_args.kwargs
            images = call_kwargs["messages"][0]["images"]
            # Should have 2 images for 2-page PDF
            assert len(images) == 2
