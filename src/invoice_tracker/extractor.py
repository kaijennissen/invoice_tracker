"""Invoice data extraction using Ollama vision models.

This module provides functions to extract structured invoice data from images
and PDFs using Ollama's vision capabilities. It is part of the core logic layer
and handles communication with the Ollama API. Supports both direct Ollama client
and BAML client for extraction.
"""

import base64
import time
from datetime import date
from pathlib import Path

import baml_py
import fitz
import ollama
import structlog
from baml_client import b
from baml_client import types as baml_types

from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    OllamaBackend,
    Settings,
)

log = structlog.get_logger(level="debug")

# Retry settings
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1.0

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with dates (YYYY-MM-DD format) and amounts (numeric only, no currency symbols). For multi-page documents, the total amount is typically on the last page."""


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


def _extract_invoice_baml(images: list[bytes], file_path: Path) -> InvoiceData:
    """Extract invoice data using BAML client.

    Retries are handled by the BAML retry policy configured in clients.baml.

    Parameters
    ----------
    images : list[bytes]
        List of PNG images as raw bytes.
    file_path : Path
        Original file path (used for logging).

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
        file=str(file_path),
        num_images=len(baml_images),
    )

    try:
        result = b.ExtractInvoiceData(images=baml_images)
    except Exception as e:
        raise ExtractionError(f"BAML extraction failed: {e}") from e

    log.debug(
        "baml_extraction_response",
        file=str(file_path),
        party=result.party,
        invoice_id=result.invoice_id,
        amount=result.amount,
        currency=result.currency,
    )

    return _convert_baml_result(result)


def _extract_invoice_ollama(images: list[bytes], settings: Settings) -> InvoiceData:
    """Extract invoice data using direct Ollama client.

    Implements retry logic with exponential backoff.

    Parameters
    ----------
    images : list[bytes]
        List of PNG images as raw bytes.
    settings : Settings
        Application settings containing Ollama configuration.

    Returns
    -------
    InvoiceData
        Extracted and validated invoice data.

    Raises
    ------
    ExtractionError
        If extraction fails after all retries.
    """
    client = _create_client(settings)
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            log.debug(
                "ollama_extraction_request",
                model=settings.ollama_model,
                num_images=len(images),
                attempt=attempt + 1,
            )

            response = client.chat(
                model=settings.ollama_model,
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

            result = InvoiceData.model_validate_json(content)

            log.debug(
                "ollama_extraction_response",
                party=result.party,
                invoice_id=result.invoice_id,
                amount=result.amount,
                currency=result.currency,
            )

            return result

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                backoff = INITIAL_BACKOFF_SECONDS * (2**attempt)
                log.debug(
                    "ollama_extraction_retry",
                    attempt=attempt + 1,
                    backoff_seconds=backoff,
                    error=str(e),
                )
                time.sleep(backoff)

    raise ExtractionError(f"Failed to extract invoice data: {last_error}")


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
    try:
        client = _create_client(settings)
        if settings.ollama_backend == OllamaBackend.CLOUD:
            # Cloud doesn't support model listing - assume available
            return True
        models = client.list()
        model_names = [m.model for m in models.models]
        return settings.ollama_model in model_names
    except Exception:
        return False


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

    log.debug(
        "extraction_start",
        file=str(file_path),
        num_images=len(images),
        use_baml=settings.use_baml,
    )

    if settings.use_baml:
        return _extract_invoice_baml(images, file_path)
    else:
        return _extract_invoice_ollama(images, settings)


__all__ = [
    "check_ollama_connection",
    "extract_invoice",
    "pdf_to_images",
    "EXTRACTION_PROMPT",
    "_convert_baml_result",
    "_bytes_to_baml_image",
]
