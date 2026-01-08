"""Invoice data extraction using Ollama vision models.

This module provides functions to extract structured invoice data from images
using Ollama's vision capabilities. It is part of the core logic layer and
handles communication with the Ollama API.
"""

import time
from pathlib import Path

import ollama

from invoice_tracker.settings import ExtractionError, InvoiceData, Settings

# Retry settings
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1.0

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with:
- Dates: use ISO format YYYY-MM-DD
- Amounts: numeric value only (no currency symbols)
- If a field cannot be determined, use "UNKNOWN" for text fields.

Extract the following information:
- party: Name of the invoicing party/company
- invoice_id: Unique invoice identifier
- issue_date: Date the invoice was issued (YYYY-MM-DD)
- due_date: Payment due date (YYYY-MM-DD)
- amount: Total amount to pay (numeric only)
- currency: Currency code (default EUR if not specified)
- recipient: Person/entity the invoice is addressed to"""


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
        client = ollama.Client(host=settings.ollama_url)
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

    client = ollama.Client(host=settings.ollama_url)
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
                format=InvoiceData.model_json_schema(),
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
