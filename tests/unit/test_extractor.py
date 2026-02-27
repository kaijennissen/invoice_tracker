"""Tests for invoice_tracker.extractor module."""

import base64
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import baml_py
import pytest
from baml_client import types as baml_types

from invoice_tracker.extractor import (
    BamlExtractor,
    ExtractionStrategy,
    OllamaExtractor,
    _bytes_to_baml_image,
    _convert_baml_result,
    _create_client,
    check_ollama_connection,
    create_extractor,
    extract_invoice,
    pdf_to_images,
)
from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    Settings,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing.

    Returns
    -------
    Settings
        Settings instance configured for testing.
    """
    return Settings(_cli_parse_args=False, process=None, eval=None)


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

    def test_cloud_backend_skips_model_check(self) -> None:
        """Cloud backend should skip model listing and return True."""
        settings = Settings(
            _cli_parse_args=False,
            ollama_model="qwen3:8b-cloud",
            ollama_api_key="test-key",
            process=None,
            eval=None,
        )
        with patch("invoice_tracker.extractor.ollama.Client"):
            result = check_ollama_connection(settings)
            assert result is True


class TestCreateClient:
    """Tests for _create_client factory function."""

    def test_cloud_backend_includes_auth_headers(self) -> None:
        """Cloud backend should include Authorization header."""
        settings = Settings(
            _cli_parse_args=False,
            ollama_model="qwen3:8b-cloud",
            ollama_api_key="test-api-key",
            process=None,
            eval=None,
        )
        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            _create_client(settings)
            mock_client.assert_called_once_with(
                host="https://ollama.com",
                timeout=settings.ollama_timeout,
                headers={"Authorization": "Bearer test-api-key"},
            )

    def test_local_backend_no_auth_headers(self) -> None:
        """Local backend should not include Authorization header."""
        settings = Settings(_cli_parse_args=False, process=None, eval=None)
        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            _create_client(settings)
            mock_client.assert_called_once_with(
                host="http://localhost:11434",
                timeout=settings.ollama_timeout,
                headers=None,
            )


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
            assert result.amount == 1234.56

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

            with patch("invoice_tracker.retry.time.sleep"):
                result = extract_invoice(image_path, mock_settings)

                assert isinstance(result, InvoiceData)
                assert mock_client.return_value.chat.call_count == 3

    def test_exception_chaining_preserves_cause(
        self, mock_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice chains the original exception as __cause__."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        original_error = ValueError("bad json")

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.side_effect = original_error

            with patch("invoice_tracker.retry.time.sleep"):
                with pytest.raises(ExtractionError) as exc_info:
                    extract_invoice(image_path, mock_settings)

                assert exc_info.value.__cause__ is original_error

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


class TestOllamaExtractor:
    """Tests for OllamaExtractor class."""

    def test_extract_success(
        self, mock_settings: Settings, sample_invoice_json: str
    ) -> None:
        """OllamaExtractor.extract returns InvoiceData on success."""
        mock_response = MagicMock()
        mock_response.message.content = sample_invoice_json

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extractor = OllamaExtractor(mock_settings)
            result = extractor.extract([b"dummy image"])

            assert isinstance(result, InvoiceData)
            assert result.party == "Test Corp"

    def test_extract_raises_on_empty_response(self, mock_settings: Settings) -> None:
        """OllamaExtractor.extract raises ExtractionError on empty response."""
        mock_response = MagicMock()
        mock_response.message.content = None

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.chat.return_value = mock_response

            extractor = OllamaExtractor(mock_settings)

            with pytest.raises(ExtractionError, match="Empty response"):
                extractor.extract([b"dummy image"])

    def test_check_connection_returns_true(self, mock_settings: Settings) -> None:
        """OllamaExtractor.check_connection returns True when model available."""
        mock_model = MagicMock()
        mock_model.model = mock_settings.ollama_model
        mock_models_response = MagicMock()
        mock_models_response.models = [mock_model]

        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.list.return_value = mock_models_response

            extractor = OllamaExtractor(mock_settings)
            assert extractor.check_connection() is True

    def test_check_connection_returns_false_on_error(
        self, mock_settings: Settings
    ) -> None:
        """OllamaExtractor.check_connection returns False on error."""
        with patch("invoice_tracker.extractor.ollama.Client") as mock_client:
            mock_client.return_value.list.side_effect = Exception("fail")

            extractor = OllamaExtractor(mock_settings)
            assert extractor.check_connection() is False

    def test_implements_protocol(self, mock_settings: Settings) -> None:
        """OllamaExtractor satisfies the ExtractionStrategy protocol."""
        with patch("invoice_tracker.extractor.ollama.Client"):
            extractor = OllamaExtractor(mock_settings)
            assert isinstance(extractor, ExtractionStrategy)


class TestBamlExtractor:
    """Tests for BamlExtractor class."""

    @pytest.fixture
    def baml_settings(self) -> Settings:
        """Create settings with BAML enabled.

        Returns
        -------
        Settings
            Settings instance with use_baml=True.
        """
        return Settings(_cli_parse_args=False, use_baml=True, process=None, eval=None)

    def test_extract_success(self, baml_settings: Settings) -> None:
        """BamlExtractor.extract returns InvoiceData on success."""
        mock_baml_result = baml_types.InvoiceData(
            party="BAML Corp",
            invoice_id="BAML-001",
            issue_date="2024-03-01",
            due_date="2024-04-01",
            amount=999.99,
            currency="USD",
            recipient="BAML User",
        )

        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.return_value = mock_baml_result

            extractor = BamlExtractor(baml_settings)
            result = extractor.extract([b"dummy image"])

            assert isinstance(result, InvoiceData)
            assert result.party == "BAML Corp"
            assert result.invoice_id == "BAML-001"

    def test_extract_raises_on_failure(self, baml_settings: Settings) -> None:
        """BamlExtractor.extract raises ExtractionError on failure."""
        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.side_effect = Exception("BAML API error")

            extractor = BamlExtractor(baml_settings)

            with pytest.raises(ExtractionError, match="BAML extraction failed"):
                extractor.extract([b"dummy image"])

    def test_implements_protocol(self, baml_settings: Settings) -> None:
        """BamlExtractor satisfies the ExtractionStrategy protocol."""
        extractor = BamlExtractor(baml_settings)
        assert isinstance(extractor, ExtractionStrategy)

    def test_check_connection_returns_true(self, baml_settings: Settings) -> None:
        """BamlExtractor.check_connection always returns True."""
        extractor = BamlExtractor(baml_settings)
        assert extractor.check_connection() is True


class TestCreateExtractor:
    """Tests for create_extractor factory function."""

    def test_returns_ollama_extractor_by_default(self, mock_settings: Settings) -> None:
        """create_extractor returns OllamaExtractor when use_baml is False."""
        with patch("invoice_tracker.extractor.ollama.Client"):
            extractor = create_extractor(mock_settings)
            assert isinstance(extractor, OllamaExtractor)

    def test_returns_baml_extractor_when_enabled(self) -> None:
        """create_extractor returns BamlExtractor when use_baml is True."""
        settings = Settings(
            _cli_parse_args=False, use_baml=True, process=None, eval=None
        )
        extractor = create_extractor(settings)
        assert isinstance(extractor, BamlExtractor)

    def test_warns_cloud_without_baml(self, capsys: pytest.CaptureFixture[str]) -> None:
        """create_extractor warns when cloud model used without BAML."""
        settings = Settings(
            _cli_parse_args=False,
            ollama_model="qwen3:8b-cloud",
            ollama_api_key="test-key",
            use_baml=False,
            process=None,
            eval=None,
        )
        with patch("invoice_tracker.extractor.ollama.Client"):
            create_extractor(settings)

        captured = capsys.readouterr()
        assert "cloud_structured_outputs_unsupported" in captured.out


class TestConvertBamlResult:
    """Tests for _convert_baml_result function."""

    def test_converts_baml_result_to_invoice_data(self) -> None:
        """_convert_baml_result converts BAML types to application types."""
        baml_result = baml_types.InvoiceData(
            party="Test Corp",
            invoice_id="INV-2024-001",
            issue_date="2024-01-15",
            due_date="2024-02-15",
            amount=1234.56,
            currency="EUR",
            recipient="John Doe",
        )

        result = _convert_baml_result(baml_result)

        assert isinstance(result, InvoiceData)
        assert result.party == "Test Corp"
        assert result.invoice_id == "INV-2024-001"
        assert result.issue_date == date(2024, 1, 15)
        assert result.due_date == date(2024, 2, 15)
        assert result.amount == 1234.56
        assert result.currency == "EUR"
        assert result.recipient == "John Doe"

    def test_preserves_currency(self) -> None:
        """_convert_baml_result preserves currency value."""
        baml_result = baml_types.InvoiceData(
            party="Test Corp",
            invoice_id="INV-2024-001",
            issue_date="2024-01-15",
            due_date="2024-02-15",
            amount=1234.56,
            currency="USD",
            recipient="John Doe",
        )

        result = _convert_baml_result(baml_result)

        assert result.currency == "USD"


class TestBytesToBamlImage:
    """Tests for _bytes_to_baml_image function."""

    def test_converts_bytes_to_baml_image(self) -> None:
        """_bytes_to_baml_image returns a BAML Image object."""
        image_bytes = b"fake png content"

        result = _bytes_to_baml_image(image_bytes)

        assert isinstance(result, baml_py.Image)

    def test_encodes_bytes_as_base64(self) -> None:
        """_bytes_to_baml_image correctly encodes bytes."""
        image_bytes = b"test image data"
        expected_b64 = base64.b64encode(image_bytes).decode()

        with patch("invoice_tracker.extractor.baml_py.Image.from_base64") as mock_from:
            _bytes_to_baml_image(image_bytes)

            mock_from.assert_called_once_with(
                media_type="image/png",
                base64=expected_b64,
            )


class TestExtractInvoiceBaml:
    """Tests for extract_invoice with BAML backend."""

    @pytest.fixture
    def baml_settings(self) -> Settings:
        """Create settings with BAML enabled.

        Returns
        -------
        Settings
            Settings instance with use_baml=True.
        """
        return Settings(_cli_parse_args=False, use_baml=True, process=None, eval=None)

    def test_uses_baml_when_enabled(
        self, baml_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice uses BAML client when use_baml is True."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy image content")

        mock_baml_result = baml_types.InvoiceData(
            party="BAML Corp",
            invoice_id="BAML-001",
            issue_date="2024-03-01",
            due_date="2024-04-01",
            amount=999.99,
            currency="USD",
            recipient="BAML User",
        )

        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.return_value = mock_baml_result

            result = extract_invoice(image_path, baml_settings)

            assert result.party == "BAML Corp"
            assert result.invoice_id == "BAML-001"
            mock_baml.assert_called_once()

    def test_baml_receives_correct_images(
        self, baml_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice passes correct images to BAML."""
        image_path = tmp_path / "invoice.png"
        image_content = b"fake png content"
        image_path.write_bytes(image_content)

        mock_baml_result = baml_types.InvoiceData(
            party="Test",
            invoice_id="001",
            issue_date="2024-01-01",
            due_date="2024-02-01",
            amount=100.0,
            currency="EUR",
            recipient="Test User",
        )

        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.return_value = mock_baml_result

            extract_invoice(image_path, baml_settings)

            call_kwargs = mock_baml.call_args.kwargs
            assert "images" in call_kwargs
            assert len(call_kwargs["images"]) == 1

    def test_baml_extraction_error_raises(
        self, baml_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice raises ExtractionError on BAML failure."""
        image_path = tmp_path / "invoice.png"
        image_path.write_bytes(b"dummy content")

        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.side_effect = Exception("BAML API error")

            with pytest.raises(ExtractionError, match="BAML extraction failed"):
                extract_invoice(image_path, baml_settings)

    def test_baml_handles_multipage_pdf(
        self, baml_settings: Settings, tmp_path: Path
    ) -> None:
        """extract_invoice passes all PDF pages to BAML."""
        pdf_path = tmp_path / "multipage.pdf"

        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        mock_baml_result = baml_types.InvoiceData(
            party="Test",
            invoice_id="001",
            issue_date="2024-01-01",
            due_date="2024-02-01",
            amount=100.0,
            currency="EUR",
            recipient="Test User",
        )

        with patch("invoice_tracker.extractor.b.ExtractInvoiceData") as mock_baml:
            mock_baml.return_value = mock_baml_result

            extract_invoice(pdf_path, baml_settings)

            call_kwargs = mock_baml.call_args.kwargs
            assert len(call_kwargs["images"]) == 3
