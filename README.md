# Invoice Tracker

Invoice tracking automation tool that extracts structured data from invoice images using Ollama (local or cloud) and persists data to Excel.

## Features

- Extract structured data from invoice images using vision LLMs
- Support for local Ollama instance or Ollama cloud API
- Automatic file organization (incoming → processed/failed)
- Excel-based data persistence
- Command-line interface with environment variable configuration

## Installation

### Prerequisites

- Python 3.13.7 or higher
- [uv](https://docs.astral.sh/uv/) for dependency management
- [Ollama](https://ollama.ai/) (for local mode) or Ollama cloud API key (for cloud mode)

### Install from source

```bash
git clone https://github.com/your-username/invoice_tracker.git
cd invoice_tracker
uv sync
```

## Quick Start

### Local Ollama (Default)

Ensure Ollama is running locally with a vision model:

```bash
# Pull a vision model
ollama pull ministral-3:14b

# Process an invoice
invoice-tracker invoice.png
```

### Ollama Cloud

Use the cloud backend with your API key:

```bash
export INVOICE_OLLAMA_BACKEND=cloud
export INVOICE_OLLAMA_API_KEY="your-api-key"
invoice-tracker invoice.png
```

### Custom Endpoint

For advanced setups with a custom Ollama endpoint:

```bash
export INVOICE_OLLAMA_BACKEND=local
export INVOICE_OLLAMA_URL_OVERRIDE="http://custom-host:11434"
invoice-tracker invoice.png
```

## Configuration

All settings can be configured via environment variables with the `INVOICE_` prefix:

### Ollama Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `INVOICE_OLLAMA_BACKEND` | Backend selection: `local` or `cloud` | `local` |
| `INVOICE_OLLAMA_API_KEY` | API key for cloud backend (required when `backend=cloud`) | - |
| `INVOICE_OLLAMA_URL_OVERRIDE` | Override the backend's default URL (advanced) | - |
| `INVOICE_OLLAMA_MODEL` | Vision model for invoice extraction | `ministral-3:14b` |
| `INVOICE_OLLAMA_TIMEOUT` | API timeout in seconds | `120` |

### Backend URLs

- **Local**: `http://localhost:11434` (default)
- **Cloud**: `https://ollama.com`

### Directory Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `INVOICE_INCOMING_DIR` | Directory for incoming invoice images | `invoices/incoming` |
| `INVOICE_PROCESSED_DIR` | Directory for successfully processed invoices | `invoices/processed` |
| `INVOICE_FAILED_DIR` | Directory for failed invoice processing | `invoices/failed` |
| `INVOICE_DATA_FILE` | Path to Excel data file | `data/tracker.xlsx` |

## CLI Usage

```bash
# Show help and available options
invoice-tracker --help

# Process a single invoice
invoice-tracker path/to/invoice.png

# Process with specific backend
invoice-tracker --ollama-backend cloud --ollama-api-key "your-key" invoice.png

# Process with custom model
invoice-tracker --ollama-model llava invoice.png
```

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/your-username/invoice_tracker.git
cd invoice_tracker

# Install dependencies (development group)
uv sync --group dev

# Install pre-commit hooks
uv run pre-commit install

# Run tests to verify setup
uv run pytest
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/unit/test_extractor.py
```

### Code Quality

```bash
# Check code formatting and linting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/
```

## Migration Notes

### From versions using `INVOICE_OLLAMA_URL`

The `INVOICE_OLLAMA_URL` setting has been replaced with a backend-based configuration:

| Old Configuration | New Configuration |
|-------------------|-------------------|
| `INVOICE_OLLAMA_URL=http://localhost:11434` | No change needed (default) |
| `INVOICE_OLLAMA_URL=http://custom:11434` | `INVOICE_OLLAMA_URL_OVERRIDE=http://custom:11434` |
| `INVOICE_OLLAMA_URL=https://ollama.com` | `INVOICE_OLLAMA_BACKEND=cloud` + `INVOICE_OLLAMA_API_KEY=...` |

## Contributing

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Make your changes
3. Add tests for new functionality
4. Run the test suite (`uv run pytest`)
5. Run code quality checks (`uv run ruff check . && uv run mypy src/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request
