"""Outlines-based invoice data extraction with client-side structured generation.

This module provides the OutlinesExtractor class that uses the Outlines library
with a HuggingFace Transformers vision model for logit-level constrained
structured generation. Dependencies are lazy-imported to avoid heavy load times
when this backend is not in use.

Requires: uv sync --group outlines
"""

from typing import Any

import structlog

from invoice_tracker.retry import RetryConfig, with_retry
from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    Settings,
)

log = structlog.get_logger()

_EXTRACTION_RETRY = RetryConfig(
    max_retries=2, initial_backoff=1.0, catch=(ExtractionError,)
)


class OutlinesExtractor:
    """Outlines-based invoice data extractor.

    Uses the Outlines library with a HuggingFace Transformers vision model
    for client-side logit-level structured generation. The model is lazy-loaded
    on first extraction to avoid slow startup when this backend is not in use.

    Parameters
    ----------
    settings : Settings
        Application settings containing the outlines_model ID.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: Any | None = None

    @property
    def _hf_token(self) -> str | None:
        """Get the HuggingFace token from settings, if configured."""
        s = self._settings
        return s.huggingface_token.get_secret_value() if s.huggingface_token else None

    def _get_model(self) -> Any:
        """Lazy-load the Transformers vision model via Outlines.

        Returns
        -------
        object
            An Outlines model wrapper that supports structured generation.

        Raises
        ------
        ImportError
            If outlines or transformers dependencies are not installed.
        """
        if self._model is None:
            try:
                import outlines
                from transformers import AutoModelForImageTextToText, AutoProcessor
            except ImportError:
                raise ImportError(
                    "Outlines dependencies not installed. Run: uv sync --group outlines"
                ) from None

            log.info(
                "loading_outlines_model",
                model=self._settings.outlines_model,
            )

            processor = AutoProcessor.from_pretrained(
                self._settings.outlines_model, token=self._hf_token
            )
            hf_model = AutoModelForImageTextToText.from_pretrained(
                self._settings.outlines_model,
                torch_dtype="auto",
                token=self._hf_token,
            )
            self._model = outlines.from_transformers(hf_model, processor)

        return self._model

    @with_retry(_EXTRACTION_RETRY)
    def extract(self, images: list[bytes]) -> InvoiceData:
        """Extract invoice data from images via Outlines structured generation.

        Parameters
        ----------
        images : list[bytes]
            One or more images as raw bytes.

        Returns
        -------
        InvoiceData
            Extracted and validated invoice data.

        Raises
        ------
        ExtractionError
            If extraction fails.
        ImportError
            If outlines dependencies are not installed.
        """
        try:
            import io

            import outlines
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Outlines dependencies not installed. Run: uv sync --group outlines"
            ) from None

        from invoice_tracker.extractor import EXTRACTION_PROMPT

        model = self._get_model()

        # Convert bytes to PIL Images, then wrap in outlines.Image
        outlines_images = []
        for img_bytes in images:
            pil_img = Image.open(io.BytesIO(img_bytes))
            # outlines.Image requires format to be set; re-save as PNG if missing
            if not pil_img.format:
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                buf.seek(0)
                pil_img = Image.open(buf)
            outlines_images.append(outlines.Image(pil_img))

        # TransformersMultiModal expects [prompt, Image, Image, ...]
        model_input: list[str | outlines.Image] = [
            EXTRACTION_PROMPT,
            *outlines_images,
        ]

        try:
            result = model(model_input, output_type=InvoiceData)
        except Exception as e:
            raise ExtractionError(f"Outlines extraction failed: {e}") from e

        if not isinstance(result, InvoiceData):
            raise ExtractionError(
                f"Unexpected result type from Outlines: {type(result)}"
            )

        return result

    def check_connection(self) -> bool:
        """Check if the HuggingFace model exists (lightweight, no model loading).

        Returns
        -------
        bool
            True if the model info can be retrieved from HuggingFace Hub.
        """
        try:
            from huggingface_hub import model_info

            model_info(self._settings.outlines_model, token=self._hf_token)
            return True
        except Exception:
            return False


__all__ = [
    "OutlinesExtractor",
]
