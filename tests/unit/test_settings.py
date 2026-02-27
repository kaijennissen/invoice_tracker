"""Tests for invoice_tracker.settings module."""

from datetime import date, datetime
from pathlib import Path

import pytest

from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    InvoiceRecord,
    OllamaBackend,
    ProcessingResult,
    Settings,
    is_valid_extraction_config,
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
            amount=100.00,
            currency="EUR",
            recipient="Test Recipient",
        )

        assert data.party == "Test Company"
        assert data.invoice_id == "INV-001"
        assert data.amount == 100.00

    def test_currency_defaults_to_eur(self) -> None:
        """InvoiceData currency should default to EUR."""
        data = InvoiceData(
            party="Test",
            invoice_id="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            amount=100.0,
            recipient="Test",
        )

        assert data.currency == "EUR"

    def test_model_dump_preserves_float(self) -> None:
        """InvoiceData.model_dump should preserve float type."""
        data = InvoiceData(
            party="Test",
            invoice_id="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            amount=123.45,
            recipient="Test",
        )

        dumped = data.model_dump()
        assert dumped["amount"] == 123.45


class TestInvoiceRecord:
    """Tests for InvoiceRecord model."""

    def test_create_from_invoice_data(self, sample_invoice_data: InvoiceData) -> None:
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
        assert test_settings.ollama_model == "gemma3:27b"
        assert test_settings.dry_run is False
        assert test_settings.verbose is False

    def test_settings_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings should load from environment variables with INVOICE_ prefix."""
        monkeypatch.setenv("INVOICE_OLLAMA_MODEL", "llava")
        monkeypatch.setenv("INVOICE_OLLAMA_URL_OVERRIDE", "http://custom:11434")
        monkeypatch.setenv("INVOICE_INCOMING_DIR", "/custom/incoming")

        settings = Settings(_cli_parse_args=False, process=None, eval=None)

        assert settings.ollama_model == "llava"
        assert settings.ollama_url == "http://custom:11434"  # Via override
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


class TestOllamaBackendFromModel:
    """Tests for OllamaBackend.from_model() auto-detection."""

    def test_cloud_suffix_returns_cloud(self) -> None:
        """Model ending with '-cloud' should return CLOUD backend."""
        assert OllamaBackend.from_model("qwen3-coder:480b-cloud") == OllamaBackend.CLOUD

    def test_cloud_suffix_simple_tag(self) -> None:
        """Simple tag with '-cloud' suffix should return CLOUD."""
        assert OllamaBackend.from_model("qwen3:8b-cloud") == OllamaBackend.CLOUD

    def test_local_model_returns_local(self) -> None:
        """Model without '-cloud' suffix should return LOCAL backend."""
        assert OllamaBackend.from_model("gemma3:27b") == OllamaBackend.LOCAL

    def test_local_model_no_tag(self) -> None:
        """Model without tag should return LOCAL."""
        assert OllamaBackend.from_model("llava") == OllamaBackend.LOCAL

    def test_cloud_in_name_but_not_suffix(self) -> None:
        """'-cloud' in model name but not as suffix should return LOCAL."""
        assert OllamaBackend.from_model("cloud-model:8b") == OllamaBackend.LOCAL


class TestOllamaBackendMembers:
    """Tests for OllamaBackend enum members."""

    def test_has_exactly_two_members(self) -> None:
        """OllamaBackend should have exactly LOCAL and CLOUD."""
        assert list(OllamaBackend) == [OllamaBackend.LOCAL, OllamaBackend.CLOUD]


class TestIsValidExtractionConfig:
    """Tests for is_valid_extraction_config function."""

    def test_cloud_without_baml_is_invalid(self) -> None:
        """Cloud backend without BAML should be invalid."""
        assert is_valid_extraction_config(OllamaBackend.CLOUD, False) is False

    def test_cloud_with_baml_is_valid(self) -> None:
        """Cloud backend with BAML should be valid."""
        assert is_valid_extraction_config(OllamaBackend.CLOUD, True) is True

    def test_local_without_baml_is_valid(self) -> None:
        """Local backend without BAML should be valid."""
        assert is_valid_extraction_config(OllamaBackend.LOCAL, False) is True

    def test_local_with_baml_is_valid(self) -> None:
        """Local backend with BAML should be valid."""
        assert is_valid_extraction_config(OllamaBackend.LOCAL, True) is True


class TestSettingsBackendAutoDetection:
    """Tests for Settings auto-detecting backend from model string."""

    def test_local_model_derives_local_backend(self) -> None:
        """Local model should derive LOCAL backend."""
        settings = Settings(
            _cli_parse_args=False, process=None, eval=None, ollama_model="gemma3:27b"
        )
        assert settings.ollama_backend == OllamaBackend.LOCAL
        assert settings.ollama_url == "http://localhost:11434"

    def test_cloud_model_derives_cloud_backend(self) -> None:
        """Cloud model should derive CLOUD backend and URL."""
        settings = Settings(
            _cli_parse_args=False,
            process=None,
            eval=None,
            ollama_model="qwen3:8b-cloud",
            ollama_api_key="test-key",
        )
        assert settings.ollama_backend == OllamaBackend.CLOUD
        assert settings.ollama_url == "https://ollama.com"


class TestSettingsForModel:
    """Tests for Settings.for_model() helper."""

    def test_creates_copy_with_new_model(self) -> None:
        """for_model() should return a new Settings with the given model."""
        base = Settings(
            _cli_parse_args=False, process=None, eval=None, ollama_model="gemma3:27b"
        )
        copy = base.for_model("llava:13b")
        assert copy.ollama_model == "llava:13b"
        assert base.ollama_model == "gemma3:27b"  # original unchanged

    def test_auto_detects_cloud_backend(self) -> None:
        """for_model() with cloud model should auto-detect CLOUD backend."""
        base = Settings(
            _cli_parse_args=False,
            process=None,
            eval=None,
            ollama_model="gemma3:27b",
            ollama_api_key="test-key",
        )
        copy = base.for_model("qwen3-coder:480b-cloud")
        assert copy.ollama_backend == OllamaBackend.CLOUD
        assert copy.ollama_url == "https://ollama.com"

    def test_overrides_use_baml(self) -> None:
        """for_model() should override use_baml when specified."""
        base = Settings(_cli_parse_args=False, process=None, eval=None, use_baml=False)
        copy = base.for_model("gemma3:27b", use_baml=True)
        assert copy.use_baml is True

    def test_preserves_other_settings(self) -> None:
        """for_model() should preserve non-overridden settings."""
        base = Settings(
            _cli_parse_args=False,
            process=None,
            eval=None,
            ollama_timeout=300,
            ollama_url_override="http://custom:11434",
        )
        copy = base.for_model("llava:13b")
        assert copy.ollama_timeout == 300
        assert copy.ollama_url_override == "http://custom:11434"

    def test_cloud_model_without_api_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """for_model() with cloud model but no API key should raise."""
        monkeypatch.delenv("INVOICE_OLLAMA_API_KEY", raising=False)
        base = Settings(
            _cli_parse_args=False, process=None, eval=None, ollama_model="gemma3:27b"
        )
        with pytest.raises(ValueError, match="ollama_api_key is required"):
            base.for_model("qwen3:8b-cloud")


class TestSettingsOllamaValidation:
    """Tests for Ollama configuration validation."""

    def test_cloud_model_without_api_key_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloud model without API key should raise ValueError."""
        monkeypatch.delenv("INVOICE_OLLAMA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ollama_api_key is required"):
            Settings(
                _cli_parse_args=False,
                process=None,
                eval=None,
                ollama_model="qwen3:8b-cloud",
            )

    def test_cloud_model_with_api_key_succeeds(self) -> None:
        """Cloud model with API key should work and derive correct URL."""
        settings = Settings(
            _cli_parse_args=False,
            process=None,
            eval=None,
            ollama_model="deepseek-v3.1:671b-cloud",
            ollama_api_key="test-key",
        )
        assert settings.ollama_backend == OllamaBackend.CLOUD
        assert settings.ollama_url == "https://ollama.com"

    def test_local_model_without_api_key_succeeds(self) -> None:
        """Local model without API key should succeed."""
        settings = Settings(
            _cli_parse_args=False, process=None, eval=None, ollama_model="gemma3:27b"
        )
        assert settings.ollama_backend == OllamaBackend.LOCAL

    def test_ollama_url_override_takes_precedence(self) -> None:
        """ollama_url_override should override backend default."""
        settings = Settings(
            _cli_parse_args=False,
            process=None,
            eval=None,
            ollama_url_override="http://custom:11434",
        )
        assert settings.ollama_url == "http://custom:11434"
