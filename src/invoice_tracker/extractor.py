"""Invoice data extraction using Ollama vision models.

This module provides functions and classes to extract structured invoice data
from images and PDFs using Ollama's vision capabilities. It is part of the core
logic layer and handles communication with the Ollama API.

Provides both:
- Module-level functions (extract_invoice, check_ollama_connection) for backward
  compatibility
- ExtractionStrategy protocol and OllamaExtractor/BamlExtractor classes for
  extensibility
"""

import base64
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

import baml_py
import baml_py.baml_py
import fitz
import ollama
import structlog
from baml_client import b
from baml_client import types as baml_types

from invoice_tracker.retry import RetryConfig, with_retry
from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    OllamaBackend,
    Settings,
    is_valid_extraction_config,
)

log = structlog.get_logger()

_EXTRACTION_RETRY = RetryConfig(max_retries=2, initial_backoff=1.0)

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with dates (YYYY-MM-DD format) and amounts (numeric only, no currency symbols). For multi-page documents, the total amount is typically on the last page."""


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Protocol for invoice data extraction backends.

    Implementations receive raw image bytes (not file paths) so that
    file I/O stays in the caller.
    """

    def extract(self, images: list[bytes]) -> InvoiceData:
        """Extract invoice data from images.

        Parameters
        ----------
        images : list[bytes]
            One or more images as raw bytes.

        Returns
        -------
        InvoiceData
            Extracted and validated invoice data.
        """
        ...

    def check_connection(self) -> bool:
        """Check whether the backend is reachable.

        Returns
        -------
        bool
            True if the backend is available.
        """
        ...


def _create_client(settings: Settings) -> ollama.Client:
    """Create Ollama client with backend-appropriate configuration.

    Configures the client with the correct URL and authentication headers
    based on the selected backend.

    Parameters
    ----------
    settings : Settings
        Application settings containing Ollama configuration.

    Returns
    -------
    ollama.Client
        Configured Ollama client instance.
    """
    headers = None
    if settings.ollama_backend.requires_api_key and settings.ollama_api_key:
        headers = {
            "Authorization": f"Bearer {settings.ollama_api_key.get_secret_value()}"
        }

    return ollama.Client(
        host=settings.ollama_url,
        timeout=settings.ollama_timeout,
        headers=headers,
    )


def pdf_to_images(pdf_path: Path) -> list[bytes]:
    """Convert PDF pages to in-memory PNG images.

    Converts each page of a PDF document to a PNG image at 2x scale
    for better quality when processing with vision models.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file.

    Returns
    -------
    list[bytes]
        List of PNG images as raw bytes (one per page).

    Raises
    ------
    FileNotFoundError
        If the PDF file doesn't exist.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    images: list[bytes] = []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for quality
            images.append(pix.tobytes("png"))
    finally:
        doc.close()

    return images


def _convert_baml_result(baml_result: baml_types.InvoiceData) -> InvoiceData:
    """Convert BAML InvoiceData (str dates) to Python InvoiceData (date objects).

    BAML generates its own InvoiceData type with string dates. This function
    converts to the application's InvoiceData with proper date objects.

    Parameters
    ----------
    baml_result : baml_types.InvoiceData
        BAML-generated invoice data with string dates.

    Returns
    -------
    InvoiceData
        Application invoice data with date objects.
    """
    return InvoiceData(
        party=baml_result.party,
        invoice_id=baml_result.invoice_id,
        issue_date=date.fromisoformat(baml_result.issue_date),
        due_date=date.fromisoformat(baml_result.due_date),
        amount=baml_result.amount,
        currency=baml_result.currency,
        recipient=baml_result.recipient,
    )


def _bytes_to_baml_image(image_bytes: bytes) -> baml_py.Image:
    """Convert raw PNG bytes to BAML Image object.

    Parameters
    ----------
    image_bytes : bytes
        Raw PNG image bytes.

    Returns
    -------
    baml_py.Image
        BAML Image object suitable for the BAML client.
    """
    return baml_py.Image.from_base64(
        media_type="image/png",
        base64=base64.b64encode(image_bytes).decode(),
    )


class OllamaExtractor:
    """Ollama-based invoice data extractor.

    Wraps the Ollama API with retry logic and structured output parsing.

    Parameters
    ----------
    settings : Settings
        Application settings containing Ollama configuration.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = _create_client(settings)

    @with_retry(_EXTRACTION_RETRY)
    def extract(self, images: list[bytes]) -> InvoiceData:
        """Extract invoice data from images via Ollama.

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
            If the response is empty.
        """
        response = self._client.chat(
            model=self._settings.ollama_model,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT,
                    "images": images,
                }
            ],
            format=InvoiceData.model_json_schema(),
            options={"temperature": 0},
        )

        content = response.message.content
        if content is None:
            raise ExtractionError("Empty response from Ollama")

        return InvoiceData.model_validate_json(content)

    def check_connection(self) -> bool:
        """Check if Ollama is reachable and the model is available.

        Returns
        -------
        bool
            True if Ollama is reachable (and model available for local).
        """
        try:
            if self._settings.ollama_backend == OllamaBackend.CLOUD:
                return True
            models = self._client.list()
            model_names = [m.model for m in models.models]
            return self._settings.ollama_model in model_names
        except Exception:
            return False


class BamlExtractor:
    """BAML-based invoice data extractor.

    Uses the BAML client for extraction with retry policy configured in
    clients.baml.

    Parameters
    ----------
    settings : Settings
        Application settings (used for logging context).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        model = settings.ollama_model
        options: dict = {
            "base_url": f"{settings.ollama_url}/v1",
            "model": model,
            "default_role": "user",
        }
        if settings.ollama_backend.requires_api_key and settings.ollama_api_key:
            options["api_key"] = settings.ollama_api_key.get_secret_value()
        cr = baml_py.baml_py.ClientRegistry()
        cr.add_llm_client(
            name="DynamicClient",
            provider="openai-generic",
            options=options,
        )
        cr.set_primary("DynamicClient")
        self._client_registry = cr

    def extract(self, images: list[bytes]) -> InvoiceData:
        """Extract invoice data from images via BAML.

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
        """
        baml_images = [_bytes_to_baml_image(img) for img in images]

        log.debug(
            "baml_extraction_request",
            num_images=len(baml_images),
        )

        try:
            result = b.ExtractInvoiceData(
                images=baml_images,
                baml_options={"client_registry": self._client_registry},
            )
        except Exception as e:
            raise ExtractionError(f"BAML extraction failed: {e}") from e

        log.debug(
            "baml_extraction_response",
            party=result.party,
            invoice_id=result.invoice_id,
            amount=result.amount,
            currency=result.currency,
        )

        return _convert_baml_result(result)

    def check_connection(self) -> bool:
        """Check if BAML backend is reachable.

        Returns
        -------
        bool
            Always True (BAML manages its own connectivity).
        """
        return True


def create_extractor(settings: Settings) -> ExtractionStrategy:
    """Create the appropriate extractor for the given settings.

    Parameters
    ----------
    settings : Settings
        Application settings.

    Returns
    -------
    ExtractionStrategy
        An extractor instance (BAML or Ollama based on settings.use_baml).
    """
    if not is_valid_extraction_config(settings.ollama_backend, settings.use_baml):
        log.warning(
            "cloud_structured_outputs_unsupported",
            model=settings.ollama_model,
            hint="Ollama cloud does not support structured output; use --use-baml for reliable extraction",
        )
    if settings.use_baml:
        return BamlExtractor(settings)
    return OllamaExtractor(settings)


# --- Backward-compatible module-level functions ---


def check_ollama_connection(settings: Settings) -> bool:
    """Check if Ollama is reachable and the configured model is available.

    For local backends, verifies the model is available. For cloud backends,
    skips model verification as the cloud API doesn't support model listing.

    Parameters
    ----------
    settings : Settings
        Application settings containing Ollama configuration.

    Returns
    -------
    bool
        True if Ollama is reachable (and model available for local), False otherwise.
    """
    return OllamaExtractor(settings).check_connection()


def extract_invoice(file_path: Path, settings: Settings) -> InvoiceData:
    """Extract invoice data from an image or PDF.

    Dispatches to either BAML or direct Ollama client based on settings.use_baml.
    For PDFs, all pages are converted to images and passed together.

    Parameters
    ----------
    file_path : Path
        Path to the invoice image or PDF file.
    settings : Settings
        Application settings containing extraction configuration.

    Returns
    -------
    InvoiceData
        Extracted and validated invoice data.

    Raises
    ------
    ExtractionError
        If extraction fails after all retries or validation fails.
    FileNotFoundError
        If the file doesn't exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Convert file to image bytes
    if file_path.suffix.lower() == ".pdf":
        images = pdf_to_images(file_path)
    else:
        images = [file_path.read_bytes()]

    extractor = create_extractor(settings)

    try:
        return extractor.extract(images)
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Failed to extract invoice data: {e}") from e


__all__ = [
    "BamlExtractor",
    "ExtractionStrategy",
    "OllamaExtractor",
    "create_extractor",
    "check_ollama_connection",
    "extract_invoice",
    "pdf_to_images",
    "EXTRACTION_PROMPT",
]
