# Implementation Plan

## Coding Style Summary

This section summarizes the key coding conventions from `docs/CODE_STYLE.md` that apply throughout implementation.

### Layered Architecture
1. **Configuration** - Typed settings, constants
2. **Interface/CLI** - Logging setup, config loading, top-level error handling
3. **Orchestration** - Wrappers mapping config to core function calls
4. **Core Logic** - Pure data transformations
5. **Persistence/IO** - Abstracted behind interfaces

Each layer depends only on the layer immediately below.

### Function Design
- Single responsibility per function
- Keep functions ≤50 lines
- Explicit type hints on all parameters and return values
- Verb names: `calculate_total`, `filter_newest_snapshot`

### CLI Modules
- Set up logging at module start
- Load configuration via settings object
- Catch exceptions at top level, log errors, exit with non-zero status
- Keep business logic out of CLI - pass only primitives/schemas to core functions

### Naming Conventions
- `snake_case` for functions, methods, variables
- `PascalCase` for classes and exceptions
- `UPPER_CASE` for constants
- Descriptive names reflecting purpose, not implementation

### Imports & Exports
- Always use absolute imports
- Explicitly re-export from submodules via `__all__ = [...]`

### Documentation
- Numpy-style docstrings on all functions and classes
- Module docstring at file top describing purpose and usage

---

## Phase 1: CLI-Based Workflow with Excel Persistence

### Goal

Process invoice images via CLI, extract structured data using Ollama, persist to Excel, and organize files into processed/failed folders.

### Prerequisites

- **Python 3.13+**
- **Ollama v0.5+** (required for structured output support)
- **Vision model:** `ollama pull qwen3-vl:8b` (~6GB VRAM)

### User Setup

```bash
# Create required directories
mkdir -p invoices/{incoming,processed,failed} data

# Pull vision model
ollama pull qwen3-vl:8b
```

### Implementation Steps

#### Step 1: Project Setup

**Objective:** Establish project structure and dependencies.

Tasks:
- [ ] Rename package from `your_project_name` to `invoice_tracker`
- [ ] Update `pyproject.toml` with project metadata
- [ ] Add dependencies: `pydantic-settings`, `openpyxl`, `ollama`
- [ ] Register CLI entry point:
  ```toml
  [project.scripts]
  invoice-tracker = "invoice_tracker.main:main"
  ```

**Dependencies:** None

---

#### Step 2: Settings & Models (`settings.py`)

**Objective:** Define application settings and data models using pydantic-settings.

**Settings class** (handles CLI args, env vars, and defaults):
```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, CliPositionalArg, SettingsConfigDict

class Settings(BaseSettings):
    """Invoice tracker configuration.

    All settings can be overridden via:
    - CLI arguments: --ollama-model llava
    - Environment variables: INVOICE_OLLAMA_MODEL=llava
    """
    model_config = SettingsConfigDict(
        cli_parse_args=True,
        cli_prog_name='invoice-tracker',
        cli_kebab_case=True,
        cli_implicit_flags=True,
        env_prefix='INVOICE_',
    )

    # CLI-only arguments
    file: CliPositionalArg[Path | None] = Field(
        default=None,
        description="Single invoice file to process (default: process all in incoming/)"
    )
    dry_run: bool = Field(
        default=False,
        description="Extract and validate without persisting or moving files"
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose/debug logging"
    )

    # Paths (configurable via env vars)
    incoming_dir: Path = Field(
        default=Path("./invoices/incoming"),
        description="Directory to scan for invoice images"
    )
    processed_dir: Path = Field(
        default=Path("./invoices/processed"),
        description="Directory for successfully processed invoices"
    )
    failed_dir: Path = Field(
        default=Path("./invoices/failed"),
        description="Directory for failed extractions"
    )
    excel_file: Path = Field(
        default=Path("./data/tracker.xlsx"),
        description="Excel file for invoice tracking"
    )

    # Ollama settings
    ollama_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL"
    )
    ollama_model: str = Field(
        default="qwen3-vl:8b",
        description="Vision model for invoice extraction"
    )
    ollama_timeout: int = Field(
        default=120,
        description="API timeout in seconds"
    )

    # Processing settings
    supported_extensions: list[str] = Field(
        default=[".png", ".jpg", ".jpeg"],
        description="Supported image file extensions"
    )
```

**Data models:**
```python
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field

class InvoiceData(BaseModel):
    """Structured data extracted from an invoice (used for LLM output)."""
    party: str = Field(description="Name of the invoicing party/company")
    invoice_id: str = Field(description="Unique invoice identifier")
    issue_date: date = Field(description="Date the invoice was issued (YYYY-MM-DD)")
    due_date: date = Field(description="Payment due date (YYYY-MM-DD)")
    amount: Decimal = Field(description="Total amount to pay")
    currency: str = Field(default="EUR", description="Currency code")
    recipient: str = Field(description="Person/entity the invoice is addressed to")

class InvoiceRecord(InvoiceData):
    """Invoice record for storage (extends InvoiceData with metadata).

    Designed for easy migration to SQLModel in Phase 2:
    - Inherit from InvoiceData to keep extraction fields
    - Add storage metadata (source_file, processed_at)
    - Use model_fields to derive Excel headers dynamically
    """
    source_file: str = Field(description="Original invoice filename")
    processed_at: datetime = Field(description="Timestamp of processing")

    @classmethod
    def get_column_headers(cls) -> list[str]:
        """Derive Excel column headers from model fields."""
        return [
            field_info.description or field_name.replace("_", " ").title()
            for field_name, field_info in cls.model_fields.items()
        ]

class ProcessingResult(BaseModel):
    """Result of processing a single invoice."""
    source_file: Path
    success: bool
    data: InvoiceData | None = None
    error: str | None = None
```

Tasks:
- [ ] Define `Settings` class with pydantic-settings as above
- [ ] Define `InvoiceData` model for extraction output
- [ ] Define `InvoiceRecord` model extending `InvoiceData` with storage metadata
- [ ] Define `ProcessingResult` model for processing status
- [ ] Write unit tests for settings loading from env vars

**Dependencies:** Step 1

---

#### Step 3: Excel Handler (`excel_handler.py`)

**Objective:** Read/write invoice data to Excel file.

**Key design:** Headers are derived from `InvoiceRecord.get_column_headers()`, not hardcoded.

```python
from .settings import InvoiceRecord

def init_excel(path: Path) -> None:
    """Create workbook with headers derived from InvoiceRecord model."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(InvoiceRecord.get_column_headers())
    wb.save(path)

def append_invoice(path: Path, record: InvoiceRecord) -> None:
    """Append invoice record to Excel file."""
    # record.model_dump().values() maintains field order
    ...
```

Tasks:
- [ ] Implement `init_excel(path: Path) -> None`
  - Create workbook with headers from `InvoiceRecord.get_column_headers()`
  - Create parent directories if needed
- [ ] Implement `append_invoice(path: Path, record: InvoiceRecord) -> None`
  - Append row using `record.model_dump().values()` for consistent field order
  - Handle file locking with retry logic (3 retries, exponential backoff)
- [ ] Implement `invoice_exists(path: Path, invoice_id: str) -> bool`
  - Scan existing rows for duplicate detection
- [ ] Write unit tests with temporary Excel files

**Dependencies:** Step 2

---

#### Step 4: Extractor (`extractor.py`)

**Objective:** Extract invoice data from images using Ollama vision models.

**Ollama API Pattern:**
```python
from ollama import chat

EXTRACTION_PROMPT = """Extract invoice data from this image. Be precise with:
- Dates: use ISO format YYYY-MM-DD
- Amounts: numeric value only (no currency symbols)
- If a field cannot be determined, use "UNKNOWN" for text fields."""

def extract_invoice(image_path: Path, settings: Settings) -> InvoiceData:
    response = chat(
        model=settings.ollama_model,
        messages=[{
            'role': 'user',
            'content': EXTRACTION_PROMPT,
            'images': [str(image_path)],
        }],
        format=InvoiceData.model_json_schema(),
        options={'temperature': 0},
    )
    return InvoiceData.model_validate_json(response.message.content)
```

Tasks:
- [ ] Implement `extract_invoice(image_path: Path, settings: Settings) -> InvoiceData`
  - Pass image path directly to `ollama.chat()` (SDK handles encoding)
  - Use `format=InvoiceData.model_json_schema()` for structured output
  - Validate response with `InvoiceData.model_validate_json()`
  - Implement retry logic (2 retries with exponential backoff)
  - Raise `ExtractionError` on failure
- [ ] Implement `check_ollama_connection(settings: Settings) -> bool`
- [ ] Write unit tests with mocked `ollama.chat()` responses

**Dependencies:** Step 2

---

#### Step 5: Processor (`processor.py`)

**Objective:** Orchestrate the full processing pipeline.

**Key design:** Convert `InvoiceData` (extraction output) to `InvoiceRecord` (storage format):

```python
from datetime import datetime
from .settings import InvoiceData, InvoiceRecord

def create_record(data: InvoiceData, source_file: Path) -> InvoiceRecord:
    """Convert extracted data to storage record with metadata."""
    return InvoiceRecord(
        **data.model_dump(),
        source_file=source_file.name,
        processed_at=datetime.now(),
    )
```

Tasks:
- [ ] Implement `scan_incoming(settings: Settings) -> list[Path]`
  - Return list of supported files in incoming directory
- [ ] Implement `move_file(source: Path, destination_dir: Path) -> Path`
  - Move file to destination, handle name conflicts
- [ ] Implement `create_record(data: InvoiceData, source_file: Path) -> InvoiceRecord`
  - Add storage metadata to extracted data
- [ ] Implement `process_single(file: Path, settings: Settings) -> ProcessingResult`
  - Extract → validate → check duplicate → create record → persist → move
  - Respect `dry_run` flag
- [ ] Implement `process_batch(settings: Settings) -> list[ProcessingResult]`
  - Process all files in incoming folder
  - Continue on individual file failures
- [ ] Write integration tests for pipeline

**Dependencies:** Step 3, Step 4

---

#### Step 6: CLI Entry Point (`main.py`)

**Objective:** Wire everything together.

```python
import sys
import structlog
from .settings import Settings
from .processor import process_single, process_batch

def main() -> int:
    settings = Settings()

    # Configure logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.verbose else logging.INFO
        ),
    )
    log = structlog.get_logger()

    # Check Ollama connection
    if not check_ollama_connection(settings):
        log.error("Cannot connect to Ollama", url=settings.ollama_url)
        return 2

    # Process single file or batch
    if settings.file:
        result = process_single(settings.file, settings)
        results = [result]
    else:
        results = process_batch(settings)

    # Report summary
    success = sum(1 for r in results if r.success)
    failed = len(results) - success
    log.info("Processing complete", success=success, failed=failed)

    if failed == len(results):
        return 2  # All failed
    elif failed > 0:
        return 1  # Partial failure
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Tasks:
- [ ] Implement `main()` function as above
- [ ] Configure structlog based on `verbose` flag
- [ ] Print summary on completion
- [ ] Return appropriate exit codes

**Dependencies:** Step 5

---

#### Step 7: Testing & Documentation

**Objective:** Ensure reliability and usability.

Tasks:
- [ ] Add sample invoice images to `tests/fixtures/`
- [ ] Write end-to-end tests for full workflow
- [ ] Test error scenarios (Ollama down, invalid images, locked Excel)
- [ ] Update README with:
  - Installation instructions
  - User setup (directory creation, model pull)
  - Usage examples
  - Environment variable reference

**Dependencies:** Step 6

---

#### Step 8: PDF Support

**Objective:** Enable processing of multi-page PDF invoices.

**Problem:** Multi-page invoices often have header info on page 1 and totals on the last page. The vision model needs to see all pages to extract complete data.

**Approach:** Convert PDF pages to images and pass all pages as multiple images in a single Ollama request. The API supports multiple images in the `images` array.

**Dependencies needed:**
- `pymupdf` (pure Python, no system dependencies) or `pdf2image` (requires poppler)

**Implementation:**

Ollama accepts images as file paths, base64 strings, or raw bytes. Using raw bytes keeps everything in memory without temp files.

```python
# In extractor.py or new pdf_handler.py
import fitz  # pymupdf

def pdf_to_images(pdf_path: Path) -> list[bytes]:
    """Convert PDF pages to in-memory PNG images.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file.

    Returns
    -------
    list[bytes]
        List of PNG images as raw bytes (one per page).
    """
    doc = fitz.open(pdf_path)
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for better quality
        images.append(pix.tobytes("png"))

    doc.close()
    return images
```

**Update to extractor:**
```python
def extract_invoice(file_path: Path, settings: Settings) -> InvoiceData:
    """Extract invoice data from image or PDF."""

    if file_path.suffix.lower() == ".pdf":
        images = pdf_to_images(file_path)  # list[bytes]
    else:
        images = [file_path.read_bytes()]  # single image as bytes

    response = client.chat(
        model=settings.ollama_model,
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT,
            "images": images,  # Ollama accepts raw bytes directly
        }],
        format=_get_extraction_schema(),
        options={"temperature": 0},
    )

    return InvoiceData.model_validate_json(response.message.content)
```

Tasks:
- [ ] Add `pymupdf` to dependencies
- [ ] Add `.pdf` to `supported_extensions` default
- [ ] Implement `pdf_to_images(pdf_path: Path) -> list[bytes]`
- [ ] Update `extract_invoice()` to handle PDFs (pass bytes, not paths)
- [ ] Update prompt to mention "total amount is typically on the last page"
- [ ] Write unit tests with sample multi-page PDF
- [ ] Test with real multi-page invoices

**Dependencies:** Step 4

---

### CLI Reference

```bash
# Process all invoices in incoming/
invoice-tracker

# Process single file
invoice-tracker invoice.png

# Dry run (extract only, no persistence or file moves)
invoice-tracker --dry-run
invoice-tracker invoice.png --dry-run

# Override settings via CLI
invoice-tracker --ollama-model llama3.2-vision
invoice-tracker --incoming-dir /path/to/invoices

# Override via environment variables
INVOICE_OLLAMA_MODEL=llama3.2-vision invoice-tracker
INVOICE_INCOMING_DIR=/path/to/invoices invoice-tracker

# Verbose output
invoice-tracker --verbose

# Help
invoice-tracker --help
```

**Exit Codes:**
- 0: Success (all files processed)
- 1: Partial failure (some files failed)
- 2: Error (Ollama unreachable, all files failed)

---

### Success Criteria

- [ ] `invoice-tracker` processes all PNG/JPG/PDF invoices in `incoming/`
- [ ] Multi-page PDFs extract data correctly (header from page 1, totals from last page)
- [ ] `invoice-tracker invoice.png` processes a single file
- [ ] `invoice-tracker --dry-run` extracts without persisting or moving
- [ ] Extracted data appears correctly in `data/tracker.xlsx`
- [ ] Processed files move to `invoices/processed/`
- [ ] Failed files move to `invoices/failed/` with logged reason
- [ ] Duplicate invoices are detected and skipped
- [ ] Environment variables override defaults
- [ ] `--verbose` increases log detail
- [ ] Works offline with local Ollama instance

---

### Error Handling Summary

| Error | Handling | User Feedback |
|-------|----------|---------------|
| Ollama unreachable | Fail fast, exit 2 | "Cannot connect to Ollama at {url}" |
| Invalid image format | Move to failed/ | Log error, continue |
| Extraction failed | Retry once, then fail | Log reason, move to failed/ |
| Validation failed | Move to failed/ | Log missing/invalid fields |
| Duplicate invoice | Skip | Warn, leave in incoming/ |
| Excel locked | Retry 3x | Error if still locked |

---

## Phase 2: Database Backend with GUI

### Goal

Replace Excel persistence with SQLite database and provide a web-based GUI for viewing and managing invoices.

### Objectives

- Searchable, sortable invoice database
- Filter by date range, party, status, recipient
- Mark invoices as paid/unpaid
- Add notes or tags to invoices
- View original invoice image from GUI
- Dashboard with summary statistics

*Implementation details to be defined after Phase 1 completion.*

---

## Phase 3: Payment Initiation

### Goal

Extend the system to support payment initiation directly from the GUI.

### Objectives

- Extract payment details (IBAN, BIC, payment reference) from invoices
- "Pay" button in GUI to initiate payments
- SEPA XML export for bank upload
- Payment status tracking (pending, completed, failed)
- Payment history and audit trail

*Implementation details to be defined after Phase 2 completion.*
