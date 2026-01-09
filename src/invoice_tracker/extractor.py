"""Invoice data extraction using Ollama vision models.

This module provides functions to extract structured invoice data from images
and PDFs using Ollama's vision capabilities. It is part of the core logic layer
and handles communication with the Ollama API.
"""

import copy
import time
from pathlib import Path
from typing import Any

import fitz
import ollama

from invoice_tracker.settings import ExtractionError, InvoiceData, Settings

# Retry settings
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1.0

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with dates (YYYY-MM-DD format) and amounts (numeric only, no currency symbols). For multi-page documents, the total amount is typically on the last page."""


def _simplify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Simplify a JSON schema for Ollama compatibility.

    Ollama crashes when processing images with schemas containing anyOf patterns
    (like those Pydantic generates for Decimal fields). This function simplifies
    such schemas by replacing anyOf with the first compatible simple type.

    Parameters
    ----------
    schema : dict[str, Any]
        The original JSON schema from Pydantic.

    Returns
    -------
    dict[str, Any]
        A simplified schema without anyOf patterns.
    """
    schema = copy.deepcopy(schema)

    # Remove description at top level (not needed for constrained decoding)
    schema.pop("description", None)
    schema.pop("title", None)

    if "properties" in schema:
        for _prop_name, prop_schema in schema["properties"].items():
            # Remove title from each property
            prop_schema.pop("title", None)

            # Simplify anyOf to first type (usually number for Decimal)
            if "anyOf" in prop_schema:
                for option in prop_schema["anyOf"]:
                    if option.get("type") in ("number", "integer", "string"):
                        prop_schema["type"] = option["type"]
                        if "format" in option:
                            prop_schema["format"] = option["format"]
                        break
                del prop_schema["anyOf"]

    return schema


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


def check_ollama_connection(settings: Settings) -> bool:
    """Check if Ollama is reachable and the configured model is available.

    Parameters
    ----------
    settings : Settings
        Application settings containing Ollama configuration.

    Returns
    -------
    bool
        True if Ollama is reachable and model is available, False otherwise.
    """
    try:
        client = ollama.Client(host=settings.ollama_url, timeout=settings.ollama_timeout)
        models = client.list()
        model_names = [m.model for m in models.models]
        return settings.ollama_model in model_names
    except Exception:
        return False


def extract_invoice(file_path: Path, settings: Settings) -> InvoiceData:
    """Extract invoice data from an image or PDF using Ollama vision model.

    Uses the configured Ollama model to analyze the invoice image or PDF and
    extract structured data. For PDFs, all pages are converted to images and
    passed together. Implements retry logic with exponential backoff.

    Parameters
    ----------
    file_path : Path
        Path to the invoice image or PDF file.
    settings : Settings
        Application settings containing Ollama configuration.

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

    client = ollama.Client(host=settings.ollama_url, timeout=settings.ollama_timeout)
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat(
                model=settings.ollama_model,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT,
                        "images": images,
                    }
                ],
                format=_simplify_schema(InvoiceData.model_json_schema()),
                options={"temperature": 0},
            )

            content = response.message.content
            if content is None:
                raise ExtractionError("Empty response from Ollama")

            return InvoiceData.model_validate_json(content)

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                backoff = INITIAL_BACKOFF_SECONDS * (2**attempt)
                time.sleep(backoff)

    raise ExtractionError(f"Failed to extract invoice data: {last_error}")


__all__ = [
    "check_ollama_connection",
    "extract_invoice",
    "pdf_to_images",
    "EXTRACTION_PROMPT",
]
