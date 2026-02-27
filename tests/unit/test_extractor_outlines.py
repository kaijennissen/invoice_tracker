"""Tests for invoice_tracker.extractor_outlines module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from invoice_tracker.extractor import ExtractionStrategy
from invoice_tracker.extractor_outlines import OutlinesExtractor
from invoice_tracker.settings import (
    ExtractionError,
    ExtractionMethod,
    InvoiceData,
    Settings,
)


@pytest.fixture
def outlines_settings() -> Settings:
    """Create settings configured for Outlines extraction.

    Returns
    -------
    Settings
        Settings instance with extraction_method=OUTLINES.
    """
    return Settings(
        _cli_parse_args=False,
        extraction_method=ExtractionMethod.OUTLINES,
        outlines_model="test/model",
    )


@pytest.fixture
def outlines_settings_with_token() -> Settings:
    """Create settings configured for Outlines extraction with a HuggingFace token.

    Returns
    -------
    Settings
        Settings instance with extraction_method=OUTLINES and huggingface_token set.
    """
    return Settings(
        _cli_parse_args=False,
        extraction_method=ExtractionMethod.OUTLINES,
        outlines_model="test/model",
        huggingface_token="hf_test123",
    )


@pytest.fixture
def sample_invoice_data() -> InvoiceData:
    """Return sample InvoiceData for mocking extraction results.

    Returns
    -------
    InvoiceData
        Sample invoice data.
    """
    return InvoiceData(
        party="Outlines Corp",
        invoice_id="OUT-001",
        issue_date=date(2024, 6, 1),
        due_date=date(2024, 7, 1),
        amount=500.0,
        currency="EUR",
        recipient="Test User",
    )


class TestOutlinesExtractor:
    """Tests for OutlinesExtractor class."""

    def test_hf_token_returns_none_when_not_set(
        self, outlines_settings: Settings
    ) -> None:
        """_hf_token returns None when no huggingface_token is configured."""
        extractor = OutlinesExtractor(outlines_settings)
        assert extractor._hf_token is None

    def test_hf_token_returns_secret_value_when_set(
        self, outlines_settings_with_token: Settings
    ) -> None:
        """_hf_token returns the secret value when huggingface_token is configured."""
        extractor = OutlinesExtractor(outlines_settings_with_token)
        assert extractor._hf_token == "hf_test123"

    def test_implements_protocol(self, outlines_settings: Settings) -> None:
        """OutlinesExtractor satisfies the ExtractionStrategy protocol."""
        extractor = OutlinesExtractor(outlines_settings)
        assert isinstance(extractor, ExtractionStrategy)

    def test_lazy_loading_model_not_loaded_on_init(
        self, outlines_settings: Settings
    ) -> None:
        """Model is not loaded until extract() is called."""
        extractor = OutlinesExtractor(outlines_settings)
        assert extractor._model is None

    def test_extract_success(
        self,
        outlines_settings: Settings,
        sample_invoice_data: InvoiceData,
    ) -> None:
        """OutlinesExtractor.extract returns InvoiceData on success."""
        mock_model = MagicMock()
        mock_model.return_value = sample_invoice_data

        mock_pil_image = MagicMock()
        mock_image_module = MagicMock()
        mock_image_module.open.return_value = mock_pil_image

        extractor = OutlinesExtractor(outlines_settings)
        extractor._model = mock_model  # skip lazy loading

        with patch.dict(
            "sys.modules",
            {"PIL": MagicMock(Image=mock_image_module), "PIL.Image": mock_image_module},
        ):
            result = extractor.extract([b"dummy image"])

        assert isinstance(result, InvoiceData)
        assert result.party == "Outlines Corp"
        assert result.invoice_id == "OUT-001"
        assert result.amount == 500.0

    def test_extract_raises_on_model_failure(self, outlines_settings: Settings) -> None:
        """OutlinesExtractor.extract raises ExtractionError on model failure."""
        mock_model = MagicMock()
        mock_model.side_effect = RuntimeError("CUDA out of memory")

        mock_image_module = MagicMock()

        extractor = OutlinesExtractor(outlines_settings)
        extractor._model = mock_model

        with (
            patch.dict(
                "sys.modules",
                {
                    "PIL": MagicMock(Image=mock_image_module),
                    "PIL.Image": mock_image_module,
                },
            ),
            patch("invoice_tracker.retry.time.sleep"),
            pytest.raises(ExtractionError, match="Outlines extraction failed"),
        ):
            extractor.extract([b"dummy image"])

    def test_extract_raises_on_unexpected_result_type(
        self, outlines_settings: Settings
    ) -> None:
        """OutlinesExtractor.extract raises ExtractionError on wrong return type."""
        mock_model = MagicMock()
        mock_model.return_value = "not an InvoiceData"

        mock_image_module = MagicMock()

        extractor = OutlinesExtractor(outlines_settings)
        extractor._model = mock_model

        with (
            patch.dict(
                "sys.modules",
                {
                    "PIL": MagicMock(Image=mock_image_module),
                    "PIL.Image": mock_image_module,
                },
            ),
            patch("invoice_tracker.retry.time.sleep"),
            pytest.raises(ExtractionError, match="Unexpected result type"),
        ):
            extractor.extract([b"dummy image"])

    def test_get_model_import_error(self, outlines_settings: Settings) -> None:
        """_get_model raises ImportError with install instructions when deps missing."""
        extractor = OutlinesExtractor(outlines_settings)

        # Remove outlines from sys.modules so the lazy import triggers
        with patch.dict("sys.modules", {"outlines": None}):
            with pytest.raises(ImportError, match="uv sync --group outlines"):
                extractor._get_model()

    def test_check_connection_returns_true(self, outlines_settings: Settings) -> None:
        """check_connection returns True when model info is retrievable."""
        mock_hub = MagicMock()

        extractor = OutlinesExtractor(outlines_settings)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            assert extractor.check_connection() is True
            mock_hub.model_info.assert_called_once_with("test/model", token=None)

    def test_check_connection_passes_token(
        self, outlines_settings_with_token: Settings
    ) -> None:
        """check_connection passes the HuggingFace token to model_info."""
        mock_hub = MagicMock()

        extractor = OutlinesExtractor(outlines_settings_with_token)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            assert extractor.check_connection() is True
            mock_hub.model_info.assert_called_once_with(
                "test/model", token="hf_test123"
            )

    def test_check_connection_returns_false_on_error(
        self, outlines_settings: Settings
    ) -> None:
        """check_connection returns False when model info fails."""
        mock_hub = MagicMock()
        mock_hub.model_info.side_effect = Exception("Not found")

        extractor = OutlinesExtractor(outlines_settings)

        with patch.dict("sys.modules", {"huggingface_hub": mock_hub}):
            assert extractor.check_connection() is False

    def test_model_cached_after_first_load(self, outlines_settings: Settings) -> None:
        """Model is cached after first _get_model() call."""
        mock_outlines = MagicMock()
        mock_processor_cls = MagicMock()
        mock_model_cls = MagicMock()

        extractor = OutlinesExtractor(outlines_settings)

        with (
            patch.dict(
                "sys.modules",
                {
                    "outlines": mock_outlines,
                    "transformers": MagicMock(
                        AutoModelForImageTextToText=mock_model_cls,
                        AutoProcessor=mock_processor_cls,
                    ),
                },
            ),
        ):
            model1 = extractor._get_model()
            model2 = extractor._get_model()

            assert model1 is model2
            # from_transformers called only once
            mock_outlines.from_transformers.assert_called_once()
            mock_processor_cls.from_pretrained.assert_called_once_with(
                "test/model", token=None
            )
            mock_model_cls.from_pretrained.assert_called_once_with(
                "test/model", torch_dtype="auto", token=None
            )

    def test_get_model_passes_token(
        self, outlines_settings_with_token: Settings
    ) -> None:
        """_get_model passes the HuggingFace token to from_pretrained calls."""
        mock_outlines = MagicMock()
        mock_processor_cls = MagicMock()
        mock_model_cls = MagicMock()

        extractor = OutlinesExtractor(outlines_settings_with_token)

        with (
            patch.dict(
                "sys.modules",
                {
                    "outlines": mock_outlines,
                    "transformers": MagicMock(
                        AutoModelForImageTextToText=mock_model_cls,
                        AutoProcessor=mock_processor_cls,
                    ),
                },
            ),
        ):
            extractor._get_model()

            mock_processor_cls.from_pretrained.assert_called_once_with(
                "test/model", token="hf_test123"
            )
            mock_model_cls.from_pretrained.assert_called_once_with(
                "test/model", torch_dtype="auto", token="hf_test123"
            )
