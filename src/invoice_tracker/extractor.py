"""Invoice data extraction using Ollama vision models.

This module provides functions to extract structured invoice data from images
using Ollama's vision capabilities. It is part of the core logic layer and
handles communication with the Ollama API.
"""

import copy
import time
from pathlib import Path
from typing import Any

import ollama

from invoice_tracker.settings import ExtractionError, InvoiceData, Settings

# Retry settings
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1.0

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with dates (YYYY-MM-DD format) and amounts (numeric only, no currency symbols)."""


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
        for prop_name, prop_schema in schema["properties"].items():
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


def _get_extraction_schema() -> dict[str, Any]:
    """Get the simplified JSON schema for invoice extraction.

    Returns
    -------
    dict[str, Any]
        Simplified JSON schema compatible with Ollama vision models.
    """
    return _simplify_schema(InvoiceData.model_json_schema())


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


def extract_invoice(image_path: Path, settings: Settings) -> InvoiceData:
    """Extract invoice data from an image using Ollama vision model.

    Uses the configured Ollama model to analyze the invoice image and
    extract structured data. Implements retry logic with exponential backoff.

    Parameters
    ----------
    image_path : Path
        Path to the invoice image file.
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
        If the image file doesn't exist.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

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
                        "images": [str(image_path)],
                    }
                ],
                format=_get_extraction_schema(),
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
    "EXTRACTION_PROMPT",
]
