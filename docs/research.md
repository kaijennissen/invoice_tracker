# Invoice Tracking Automation

## Project Overview

**Goal:** Automate the tracking of incoming invoices by extracting structured data from invoice images using a local LLM and persisting this data for overview and action.

**Current State:** Manual data entry into Excel with the following fields:
- Invoicing party
- Invoice ID
- Date of issue
- Payment due date
- Amount
- Recipient (for whom the invoice is)

**Target State:** Drop invoice images into a folder → automatic extraction → persistent storage → GUI for management and payment initiation.

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.13+ | Latest features, type hints |
| Dependency Management | uv | Fast, modern, lockfile support |
| LLM Runtime | Ollama | Local, simple API, structured output support |
| Settings & CLI | pydantic-settings | CLI args, env vars, defaults in one package |
| Data Validation | Pydantic | Structured outputs, type safety |
| Excel (Phase 1) | openpyxl | Read/write xlsx with formatting preservation |
| Database (Phase 2+) | SQLite + SQLModel | Simple, file-based, ORM convenience |
| GUI (Phase 2+) | Streamlit (or alternative) | Rapid prototyping, Python-native |

---

## Phase 1: CLI-Based Workflow with Excel Persistence

### 1.1 Objectives

- Process invoice images from a designated folder via CLI
- Extract structured data using Ollama with structured outputs
- Append extracted data to an Excel tracking file
- Move processed invoices to a `processed/` folder
- Move failed extractions to a `failed/` folder
- Handle errors gracefully with logging

### 1.2 Project Structure

```
invoice-tracker/
├── pyproject.toml          # uv project config
├── uv.lock                  # Locked dependencies
├── README.md
│
├── invoices/                # Created by user
│   ├── incoming/            # Drop invoices here
│   ├── processed/           # Successfully processed
│   └── failed/              # Failed extractions
│
├── data/                    # Created by user
│   └── tracker.xlsx         # Excel tracking file (auto-created)
│
├── src/
│   └── invoice_tracker/
│       ├── __init__.py
│       ├── main.py          # CLI entry point
│       ├── settings.py      # pydantic-settings + data models
│       ├── extractor.py     # Ollama LLM interaction
│       ├── excel_handler.py # Excel read/write operations
│       └── processor.py     # Orchestration logic
│
└── tests/
    ├── __init__.py
    ├── test_extractor.py
    ├── test_excel_handler.py
    └── fixtures/
        └── sample_invoice.png
```

### 1.3 Data Model

```python
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from pathlib import Path

class InvoiceData(BaseModel):
    """Structured data extracted from an invoice."""
    party: str = Field(description="Name of the invoicing party/company")
    invoice_id: str = Field(description="Unique invoice identifier")
    issue_date: date = Field(description="Date the invoice was issued")
    due_date: date = Field(description="Payment due date")
    amount: Decimal = Field(description="Total amount to pay")
    currency: str = Field(default="EUR", description="Currency code")
    recipient: str = Field(description="Person/entity the invoice is addressed to")

class ProcessingResult(BaseModel):
    """Result of processing a single invoice."""
    source_file: Path
    success: bool
    data: InvoiceData | None = None
    error: str | None = None
```

### 1.4 Configuration

Configuration is handled via **pydantic-settings** with defaults in code. No config file needed.

**Override via environment variables:**
```bash
export INVOICE_OLLAMA_MODEL=llama3.2-vision
export INVOICE_OLLAMA_URL=http://localhost:11434
export INVOICE_INCOMING_DIR=./invoices/incoming
export INVOICE_EXCEL_FILE=./data/tracker.xlsx
```

**Or via CLI arguments:**
```bash
invoice-tracker --ollama-model llama3.2-vision --incoming-dir ./my-invoices
```

**Defaults:**
| Setting | Default | Description |
|---------|---------|-------------|
| `incoming_dir` | `./invoices/incoming` | Directory to scan for invoices |
| `processed_dir` | `./invoices/processed` | Successfully processed files |
| `failed_dir` | `./invoices/failed` | Failed extractions |
| `excel_file` | `./data/tracker.xlsx` | Output Excel file |
| `ollama_url` | `http://localhost:11434` | Ollama API URL |
| `ollama_model` | `qwen3-vl:8b` | Vision model |
| `ollama_timeout` | `120` | API timeout (seconds) |
| `supported_extensions` | `.png, .jpg, .jpeg` | Image formats |

### 1.5 Component Specifications

#### 1.5.1 CLI Interface (`main.py`)

Commands:
```bash
# Process all invoices in incoming folder
invoice-tracker

# Process a single file
invoice-tracker path/to/invoice.png

# Dry run (extract only, no persistence)
invoice-tracker --dry-run

# Override settings
invoice-tracker --ollama-model llama3.2-vision

# Verbose output
invoice-tracker --verbose

# Help
invoice-tracker --help
```

Implementation approach:
- Use `pydantic-settings` for CLI parsing (no separate CLI framework needed)
- Settings class handles CLI args, env vars, and defaults
- Return appropriate exit codes (0 = success, 1 = partial failure, 2 = error)

#### 1.5.2 Extractor (`extractor.py`)

Responsibilities:
- Send invoice image to Ollama
- Request structured output matching `InvoiceData` schema
- Handle API errors, timeouts, malformed responses
- Return `InvoiceData` or raise descriptive exception

Key implementation details:
- Use `ollama` Python package for API interaction
- Encode images as base64 for API payload
- Use Ollama's structured output feature (JSON mode with schema)
- Implement retry logic (max 2 retries with backoff)

Prompt strategy:
```
You are an invoice data extraction assistant. Extract the following
information from the provided invoice image. Be precise with dates
(use ISO format YYYY-MM-DD) and amounts (numeric value only).

If a field cannot be determined, use "UNKNOWN" for text fields
and null for dates/amounts.
```

#### 1.5.3 Excel Handler (`excel_handler.py`)

Responsibilities:
- Initialize Excel file with headers if not exists
- Append new invoice records
- Preserve existing formatting
- Handle concurrent access gracefully (retry on lock)

Functions:
```python
def init_excel(path: Path, columns: list[str]) -> None:
    """Create Excel file with headers if it doesn't exist."""

def append_invoice(path: Path, invoice: InvoiceData, source_file: str) -> None:
    """Append a single invoice record to the Excel file."""

def invoice_exists(path: Path, invoice_id: str) -> bool:
    """Check if invoice ID already exists (duplicate detection)."""
```

#### 1.5.4 Processor (`processor.py`)

Responsibilities:
- Orchestrate the full processing pipeline
- Scan incoming folder for supported files
- Coordinate extraction → validation → persistence → file move
- Aggregate results for reporting

Flow:
```
scan_incoming()
    │
    ▼
for each file:
    │
    ├─► extract(file) ─► InvoiceData
    │         │
    │         ▼
    ├─► validate (Pydantic handles this)
    │         │
    │         ▼
    ├─► check_duplicate(invoice_id)
    │         │
    │         ▼
    ├─► append_to_excel()
    │         │
    │         ▼
    └─► move_to_processed() or move_to_failed()

    ▼
return ProcessingReport
```

### 1.6 Error Handling Strategy

| Error Type | Handling | User Feedback |
|------------|----------|---------------|
| Ollama not running | Fail fast, clear message | "Cannot connect to Ollama at {url}" |
| Invalid image | Move to failed/ | Log error, continue with next |
| Extraction failed | Retry once, then move to failed/ | Log with reason |
| Validation failed | Move to failed/ | Log missing/invalid fields |
| Duplicate invoice | Skip, leave in incoming/ | Warn in output |
| Excel locked | Retry 3x with backoff | Error if still locked |

### 1.7 Implementation Steps

See `docs/plan.md` for the detailed implementation plan.

### 1.8 Success Criteria

- [ ] Can process PNG/JPG invoice images
- [ ] Correctly extracts all fields with >90% accuracy on clear invoices
- [ ] Excel file is correctly updated with new records
- [ ] Processed files are moved appropriately
- [ ] Failed extractions are logged with reason and file is preserved
- [ ] Duplicate invoices are detected and skipped
- [ ] Works offline (requires only local Ollama)

### 1.9 Optional Enhancements (Post-Phase 1)

- Watch mode using `watchdog` library
- PDF support (may require pdf-to-image conversion)
- Multi-page invoice handling
- Confidence scores for extracted fields
- Manual review queue for low-confidence extractions

---

## Phase 2: Database Backend with GUI

### 2.1 Objectives

- Replace Excel persistence with SQLite database
- Use SQLModel for ORM and schema management
- Build a web-based GUI for viewing and managing invoices
- Maintain CLI for batch processing

### 2.2 Goals

- Searchable, sortable invoice database
- Filter by date range, party, status, recipient
- Mark invoices as paid/unpaid
- Add notes or tags to invoices
- View original invoice image from GUI
- Dashboard with summary statistics (total outstanding, by recipient, etc.)

### 2.3 Technology Candidates

| Component | Options to Evaluate |
|-----------|---------------------|
| GUI Framework | Streamlit, NiceGUI, Gradio, FastAPI + HTMX |
| Database Migrations | Alembic (if needed) or SQLModel auto-create |

### 2.4 Success Criteria

- [ ] All Phase 1 functionality preserved
- [ ] Web GUI accessible locally
- [ ] Can view, filter, and search all invoices
- [ ] Can mark invoices as paid
- [ ] Can view source invoice image
- [ ] Database survives application restarts

---

## Phase 3: Payment Initiation

### 3.1 Objectives

- Extend data extraction to include payment details (IBAN, BIC, reference)
- Add payment initiation capability from GUI
- Track payment status

### 3.2 Goals

- Extract and store: IBAN, BIC/SWIFT, payment reference
- "Pay" button in GUI that initiates payment
- Integration with banking API or payment file export (SEPA XML)
- Payment status tracking (pending, completed, failed)
- Payment history log

### 3.3 Considerations

- Security implications of payment initiation
- Banking API options (varies by region/bank)
- Alternative: Generate SEPA XML file for bank upload
- Confirmation workflow before payment execution

### 3.4 Success Criteria

- [ ] Payment details are extracted and stored
- [ ] Can initiate payment from GUI
- [ ] Payment status is tracked
- [ ] Full audit trail of payment actions

---

## Appendix

### A. Ollama Vision API

**Requirement:** Ollama v0.5+ for structured output support.

#### Image Input Formats

The Python `ollama` package accepts multiple image input formats (auto-converted):

| Input Format | Example |
|--------------|---------|
| File path (string) | `'invoice.jpg'` |
| `pathlib.Path` | `Path('invoice.jpg')` |
| Raw bytes | `open('invoice.jpg', 'rb').read()` |
| Base64 string | `'iVBORw0KGgo...'` |

**Supported image formats:** PNG, JPEG/JPG (recommended). WebP/GIF have limited support.

#### Basic Vision Request

```python
from ollama import chat

response = chat(
    model='llama3.2-vision',
    messages=[{
        'role': 'user',
        'content': 'What is in this image?',
        'images': ['path/to/image.jpg'],  # SDK handles encoding
    }]
)
print(response.message.content)
```

---

### B. Ollama Structured Outputs

Pass a JSON schema to the `format` parameter to constrain output:

```python
from ollama import chat
from pydantic import BaseModel

class Country(BaseModel):
    name: str
    capital: str
    languages: list[str]

response = chat(
    model='llama3.1',
    messages=[{'role': 'user', 'content': 'Tell me about Canada.'}],
    format=Country.model_json_schema(),  # Pydantic schema
    options={'temperature': 0},  # Recommended for deterministic output
)

# Validate response
country = Country.model_validate_json(response.message.content)
```

**Limitations:**
- No full validation during generation (model may produce incomplete JSON)
- Very complex/nested schemas may confuse the model
- Always validate responses with Pydantic
- Incompatible with "thinking mode" models

---

### C. Combining Vision + Structured Outputs

**Yes, this is supported.** Use both `images` and `format` in the same request:

```python
from ollama import chat
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal

class InvoiceData(BaseModel):
    """Structured data extracted from an invoice."""
    party: str = Field(description="Name of the invoicing party/company")
    invoice_id: str = Field(description="Unique invoice identifier")
    issue_date: date = Field(description="Date the invoice was issued (YYYY-MM-DD)")
    due_date: date = Field(description="Payment due date (YYYY-MM-DD)")
    amount: Decimal = Field(description="Total amount to pay")
    currency: str = Field(default="EUR", description="Currency code")
    recipient: str = Field(description="Person/entity the invoice is addressed to")

def extract_invoice(image_path: str, model: str = "qwen3-vl:8b") -> InvoiceData:
    """Extract structured invoice data from an image."""
    prompt = """Extract invoice data from this image. Be precise with:
- Dates: use ISO format YYYY-MM-DD
- Amounts: numeric value only (no currency symbols)
- If a field cannot be determined, use "UNKNOWN" for text fields."""

    response = chat(
        model=model,
        messages=[{
            'role': 'user',
            'content': prompt,
            'images': [image_path],  # SDK accepts file path directly
        }],
        format=InvoiceData.model_json_schema(),
        options={'temperature': 0},
    )

    return InvoiceData.model_validate_json(response.message.content)
```

**Best Practices:**
1. Set `temperature: 0` for deterministic output
2. Include extraction instructions in the prompt AND use `format` parameter
3. Always validate with Pydantic (model may still produce invalid data)
4. Implement retry logic for occasional failures

---

### D. Vision-Capable Ollama Models

| Model | Size | VRAM | Notes |
|-------|------|------|-------|
| `qwen3-vl:8b` | 8B | ~6GB | **Recommended for invoices** - 32-language OCR, handles blur/tilt/poor lighting |
| `qwen3-vl:4b` | 4B | ~4GB | Lighter alternative, good for basic invoices |
| `llama3.2-vision` | 11B/90B | ~8GB | Strong structured output support, general purpose |
| `gemma3` | Various | Varies | Google's model, good structured output support |
| `llava` | 7B/13B/34B | ~5-20GB | General purpose, widely tested |
| `minicpm-v` | 3B | ~3GB | Lightweight, good for edge devices |
| `moondream` | 1.6B | ~2GB | Smallest, fastest, reduced accuracy |

**Recommendation for invoice processing:**
1. **Primary:** `qwen3-vl:8b` - Best OCR quality, handles varied document conditions
2. **Fallback:** `llama3.2-vision` - If qwen3-vl has issues with structured output
3. **Resource-constrained:** `qwen3-vl:4b` or `minicpm-v`

Pull models with: `ollama pull qwen3-vl:8b`

---

### E. Sample Excel Layout

| Party | Invoice ID | Issue Date | Due Date | Amount | Currency | Recipient | Source File | Processed At |
|-------|------------|------------|----------|--------|----------|-----------|-------------|--------------|
| ACME Corp | INV-2024-001 | 2024-01-15 | 2024-02-15 | 1250.00 | EUR | John Doe | invoice_001.png | 2024-01-20 10:30:00 |

---

### F. Useful Commands Reference

```bash
# Add dependencies
uv add pydantic-settings openpyxl ollama

# Add dev dependencies
uv add --dev pytest pytest-cov

# Create required directories (user setup)
mkdir -p invoices/{incoming,processed,failed} data

# Pull recommended vision model
ollama pull qwen3-vl:8b

# Check Ollama is running
curl http://localhost:11434/api/tags

# Run CLI
uv run invoice-tracker
uv run invoice-tracker invoice.png
uv run invoice-tracker --dry-run --verbose

# Run tests
uv run pytest
```
