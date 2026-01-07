# Template Reference Guide

This guide provides comprehensive customization options and advanced configuration for the Python project template.

## Table of Contents

- [Python Version Management](#python-version-management)
- [Dependencies](#dependencies)
- [Project Structure](#project-structure)
- [Code Quality Configuration](#code-quality-configuration)
- [Testing Configuration](#testing-configuration)
- [CI/CD Customization](#cicd-customization)
- [Docker Configuration](#docker-configuration)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Common Patterns](#common-patterns)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Python Version Management

### Version Configuration Files

The Python version is managed in multiple places that must stay synchronized:

- **`.python-version`**: Controls uv's Python version selection and GitHub Actions
- **`Dockerfile`**: Base images must match your Python version
- **`pyproject.toml`**: Multiple sections reference the Python version

### Version Compatibility Notes

- **Python 3.13+**: Latest version with performance improvements and new features
- **Python 3.13.7**: Current template version with latest performance improvements
- **Python 3.11+**: Required for modern type union syntax (`int | float`)
- **Python 3.10+**: Required for some ruff rules and type hints
- **Older versions**: May require code changes (e.g., `Union[int, float]` instead of `int | float`)

### Changing Python Version Example

To change from 3.13.7 to 3.12, update all four locations:

```toml
# pyproject.toml
[project]
requires-python = ">=3.12"
classifiers = [
    "Programming Language :: Python :: 3.12",
]

[tool.ruff]
target-version = "py312"

[tool.mypy]
python_version = "3.12"
```

```dockerfile
# Dockerfile
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
# ...
FROM python:${PYTHON_VERSION}-slim-bookworm AS final
```

```
# .python-version
3.13.7
```

## Dependencies

### Adding Dependencies

Use uv to manage dependencies:

```bash
# Production dependencies
uv add requests pandas numpy

# Development dependencies (uses dependency-groups)
uv add --group dev pytest-xdist ruff mypy

# App-specific dependencies
uv add --group app streamlit pandera plotly
```

### Manual Dependency Configuration

Edit `pyproject.toml` directly using modern dependency-groups format:

```toml
[project]
dependencies = [
    "requests>=2.31.0",
    "pandas>=2.0,<3.0",
    "numpy>=1.24.0",
]

[dependency-groups]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.0.280",
    "mypy>=1.5.0",
    "pre-commit>=3.0.0",
]
app = [
    "streamlit>=1.28.0",
    "pandera>=0.17.0",
    "plotly>=5.17.0",
]
web = ["fastapi>=0.100.0", "uvicorn[standard]>=0.23.0"]
ml = ["scikit-learn>=1.3.0", "tensorflow>=2.13.0"]
```

### Common Dependency Groups

Using modern dependency-groups format:

```toml
[dependency-groups]
# Data science and analysis
data = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "matplotlib>=3.7.0",
    "seaborn>=0.12.0",
    "jupyter>=1.0.0",
    "polars>=0.20.0",
]

# Web development
web = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
    "pydantic>=2.0.0",
    "httpx>=0.25.0",
]

# Database connections
db = [
    "sqlalchemy>=2.0.0",
    "psycopg2-binary>=2.9.0",
    "alembic>=1.12.0",
]

# Extended testing tools
test-extras = [
    "pytest-xdist>=3.3.0",
    "pytest-mock>=3.11.0",
    "factory-boy>=3.3.0",
    "hypothesis>=6.80.0",
]

# Development tools
dev = [
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pre-commit>=3.0.0",
    "ipykernel>=6.25.0",
]
```

Note: Use `uv sync --group <group-name>` to install specific dependency groups.

## Project Structure

### Recommended Package Layout

```
src/
├── your_package/
│   ├── __init__.py
│   ├── main.py              # Entry point / CLI
│   ├── config.py            # Configuration management
│   ├── exceptions.py        # Custom exceptions
│   ├── models/              # Data models
│   │   ├── __init__.py
│   │   └── user.py
│   ├── services/            # Business logic
│   │   ├── __init__.py
│   │   └── user_service.py
│   ├── api/                 # Web API (if applicable)
│   │   ├── __init__.py
│   │   ├── routes/
│   │   └── middleware/
│   ├── db/                  # Database layer
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── repositories/
│   └── utils/               # Utility functions
│       ├── __init__.py
│       └── helpers.py
```

### Alternative Flat Structure

For simpler projects:

```
src/
├── your_package/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── services.py
│   ├── exceptions.py
│   └── utils.py
```

## Code Quality Configuration

### Advanced Ruff Configuration

```toml
[tool.ruff]
target-version = "py313"
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "N",   # pep8-naming
    "S",   # flake8-bandit (security)
    "T20", # flake8-print
    "PT",  # flake8-pytest-style
    "RET", # flake8-return
    "SIM", # flake8-simplify
]

ignore = [
    "E501",  # line too long, handled by formatter
    "B008",  # do not perform function calls in argument defaults
    "S101",  # use of assert
    "T201",  # print statements (adjust as needed)
]

# Per-file ignores
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "T201", "PT011"]  # Allow assert, print in tests
"__init__.py" = ["F401"]               # Allow unused imports
"scripts/*" = ["T201"]                 # Allow print in scripts

[tool.ruff.lint.isort]
known-first-party = ["your_package"]
force-sort-within-sections = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
```

### MyPy Advanced Configuration

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
disallow_subclassing_any = true
disallow_untyped_calls = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
implicit_reexport = false
strict_equality = true

# Per-module configuration
[[tool.mypy.overrides]]
module = "third_party_lib.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

## Testing Configuration

### Advanced Pytest Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-report=xml",
    "--cov-fail-under=80",
    "--tb=short",
    "-ra",  # Show all test outcomes except passed
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "e2e: marks tests as end-to-end tests",
    "external: marks tests that require external services",
]
filterwarnings = [
    "error",
    "ignore::UserWarning",
    "ignore::DeprecationWarning",
]
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/             # Integration tests
│   ├── test_api.py
│   └── test_database.py
├── e2e/                     # End-to-end tests
│   └── test_workflows.py
├── fixtures/                # Test data
│   ├── sample_data.json
│   └── mock_responses.py
└── helpers/                 # Test utilities
    └── factories.py
```

### Common Testing Dependencies

```bash
# Testing framework extensions
uv add --dev pytest-xdist      # Parallel testing
uv add --dev pytest-mock      # Mocking utilities
uv add --dev pytest-asyncio   # Async test support
uv add --dev pytest-benchmark # Performance testing

# Data testing
uv add --dev hypothesis       # Property-based testing
uv add --dev factory-boy     # Test data factories

# Web testing
uv add --dev httpx           # HTTP client for testing
uv add --dev respx           # HTTP mocking
```

## CI/CD Customization

### GitHub Actions Matrix Strategy

```yaml
# .github/workflows/test-matrix.yml
name: Test Matrix
on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.13", "3.14"]

    steps:
    - uses: actions/checkout@v4
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install uv
      uses: astral-sh/setup-uv@v1
    - name: Install dependencies
      run: uv sync --dev
    - name: Run tests
      run: uv run pytest
```

### Advanced Workflow Features

```yaml
# .github/workflows/advanced.yml
name: Advanced CI
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v1
    - name: Install dependencies
      run: uv sync --dev

    - name: Security scan
      run: uv run bandit -r src/

    - name: Dependency check
      run: uv run safety check

    - name: Documentation check
      run: uv run sphinx-build -W -b html docs docs/_build

    - name: Coverage report
      run: |
        uv run pytest --cov=src --cov-report=xml
        bash <(curl -s https://codecov.io/bash)
```

### Deployment Workflows

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    tags: ["v*"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v1

    - name: Build package
      run: uv build

    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: |
        uv add --dev twine
        uv run twine upload dist/*
```

## Docker Configuration

### Build Arguments

The Dockerfile supports build arguments for flexible configuration:

```dockerfile
# Build arguments with defaults
ARG PYTHON_VERSION=3.13.6
ARG UV_VERSION=latest

# Use in FROM statements
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
```

#### Python Version Management

Build with different Python versions:

```bash
# Use default Python 3.13.7
docker build -t myapp .

# Build with Python 3.12
docker build --build-arg PYTHON_VERSION=3.12 -t myapp:py312 .

# Build with specific patch version
docker build --build-arg PYTHON_VERSION=3.13.7 -t myapp:py313 .
```

#### Available Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `PYTHON_VERSION` | `3.13.6` | Python base image version |
| `UV_VERSION` | `latest` | uv tool version |

#### Docker Compose with Build Args

```yaml
# docker-compose.yml
services:
  app:
    build:
      context: .
      args:
        PYTHON_VERSION: 3.12
        UV_VERSION: 0.4.0
```

#### CI/CD with Build Arguments

```yaml
# .github/workflows/docker-matrix.yml
name: Docker Matrix Build
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13.7"]

    steps:
    - uses: actions/checkout@v4

    - name: Build Docker image
      run: |
        docker build \
          --build-arg PYTHON_VERSION=${{ matrix.python-version }} \
          --tag myapp:py${{ matrix.python-version }} \
          .

    - name: Test image
      run: |
        docker run --rm myapp:py${{ matrix.python-version }} \
          python --version
```

### Multi-stage Build Optimization

```dockerfile
# Build arguments
ARG PYTHON_VERSION=3.13.6

# Multi-stage build for Python application with uv
FROM python:${PYTHON_VERSION}-slim-bookworm as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-cache --no-dev

# Production stage
FROM python:${PYTHON_VERSION}-slim-bookworm

# Install runtime dependencies if needed
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

# Copy uv from builder
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser pyproject.toml ./

# Switch to non-root user
USER appuser

# Health check - customize endpoint as needed
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import your_package; print('OK')" || exit 1

# Default command - update module name after renaming package
CMD ["python", "-m", "your_package.main"]
```

### Docker Compose for Development

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build:
      context: .
      target: builder  # Use builder stage for development
    volumes:
      - .:/app
      - uv-cache:/root/.cache/uv
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/appdb
      - REDIS_URL=redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    command: uv run python -m your_package.main --reload

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

volumes:
  postgres_data:
  redis_data:
  uv-cache:
```

## Pre-commit Hooks

### Comprehensive Hook Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: check-case-conflict
      - id: check-json
      - id: check-toml
      - id: check-yaml
      - id: debug-statements
      - id: check-executables-have-shebangs

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.0.280
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.1
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
        args: [--strict, --ignore-missing-imports]

  - repo: https://github.com/pycqa/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        additional_dependencies: ["bandit[toml]"]

  - repo: https://github.com/Lucas-C/pre-commit-hooks-safety
    rev: v1.3.2
    hooks:
      - id: python-safety-dependencies-check

  - repo: https://github.com/commitizen-tools/commitizen
    rev: 3.6.0
    hooks:
      - id: commitizen
        stages: [commit-msg]
```

## Common Patterns

### Configuration Management

```python
# src/your_package/config.py
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Application settings
    app_name: str = "Your Package"
    debug: bool = False
    log_level: str = "INFO"

    # Database settings
    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    database_pool_size: int = Field(5, env="DATABASE_POOL_SIZE")

    # Redis settings
    redis_url: Optional[str] = Field(None, env="REDIS_URL")

    # API settings
    api_host: str = Field("0.0.0.0", env="API_HOST")
    api_port: int = Field(8000, env="API_PORT")
    secret_key: Optional[str] = Field(None, env="SECRET_KEY")

    # External services
    external_api_key: Optional[str] = Field(None, env="EXTERNAL_API_KEY")
    external_api_url: str = Field("https://api.example.com", env="EXTERNAL_API_URL")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Usage
settings = get_settings()
```

### Logging Setup

```python
# src/your_package/logging_config.py
import logging
import logging.config
import sys
from typing import Dict, Any

from .config import get_settings

settings = get_settings()


def setup_logging() -> None:
    """Configure application logging."""
    config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.log_level,
                "formatter": "standard",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": "app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)


# Usage
logger = logging.getLogger(__name__)
```

### Error Handling

```python
# src/your_package/exceptions.py
"""Custom exception classes."""


class YourPackageError(Exception):
    """Base exception for all package errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(YourPackageError):
    """Raised when data validation fails."""
    pass


class ConfigurationError(YourPackageError):
    """Raised when configuration is invalid."""
    pass


class ExternalServiceError(YourPackageError):
    """Raised when external service communication fails."""

    def __init__(self, message: str, service_name: str, status_code: int = None):
        super().__init__(message)
        self.service_name = service_name
        self.status_code = status_code


class DatabaseError(YourPackageError):
    """Raised when database operations fail."""
    pass
```

### CLI Interface

```python
# src/your_package/cli.py
import argparse
import logging
from typing import List, Optional

from .config import get_settings
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="your-package",
        description="Description of your package",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Process command
    process_parser = subparsers.add_parser("process", help="Process data")
    process_parser.add_argument("input_file", help="Input file path")
    process_parser.add_argument("--output", "-o", help="Output file path")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Setup logging
    setup_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting your-package CLI")

    try:
        if args.command == "process":
            # Import here to avoid circular imports
            from .services import process_data
            result = process_data(args.input_file, args.output)
            logger.info(f"Processing completed: {result}")
            return 0
        else:
            parser.print_help()
            return 1

    except Exception as e:
        logger.error(f"Command failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
```

## Deployment

### Production Dockerfile

```dockerfile
# Production-ready Dockerfile
FROM python:3.13.6-slim-bookworm as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-cache --no-dev

# Production stage
FROM python:3.13.6-slim-bookworm

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

# Copy uv from builder
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser pyproject.toml ./

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import your_package; print('OK')" || exit 1

# Default command
CMD ["python", "-m", "your_package.main"]
```

### Kubernetes Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: your-package
spec:
  replicas: 3
  selector:
    matchLabels:
      app: your-package
  template:
    metadata:
      labels:
        app: your-package
    spec:
      containers:
      - name: your-package
        image: your-package:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-url
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Troubleshooting

### Common Issues

#### Import Errors After Package Rename

**Problem**: `ModuleNotFoundError` after renaming package

**Solutions**:
1. Check `pyproject.toml` package configuration
2. Update all import statements in tests
3. Reinstall in development mode: `uv sync --dev`
4. Clear Python cache: `find . -type d -name "__pycache__" -exec rm -r {} +`

#### Pre-commit Hooks Failing

**Problem**: Hooks fail on commit

**Solutions**:
1. Update hooks: `uv run pre-commit autoupdate`
2. Clear cache: `uv run pre-commit clean`
3. Reinstall: `uv run pre-commit install`
4. Run manually: `uv run pre-commit run --all-files`

#### Docker Build Issues

**Problem**: Build fails or is slow

**Solutions**:
1. Clear Docker cache: `docker builder prune`
2. Check file permissions: `ls -la`
3. Use `.dockerignore`:
   ```
   .git
   .pytest_cache
   .mypy_cache
   .ruff_cache
   __pycache__
   *.pyc
   .env
   ```

#### CI/CD Failures

**Problem**: GitHub Actions failing

**Common causes and solutions**:
1. **Python version mismatch**: Ensure `.python-version` (3.13.6), `pyproject.toml`, and workflows match
2. **Dependencies not locked**: Run `uv lock` and commit `uv.lock`
3. **Environment variables**: Check if secrets are properly configured
4. **Test dependencies**: Ensure test files import correct package names

#### Performance Issues

**Problem**: Tests or linting are slow

**Solutions**:
1. Use parallel testing: `uv add --dev pytest-xdist` then `pytest -n auto`
2. Cache in CI:
   ```yaml
   - name: Cache uv
     uses: actions/cache@v3
     with:
       path: ~/.cache/uv
       key: ${{ runner.os }}-uv-${{ hashFiles('**/uv.lock') }}
   ```
3. Exclude unnecessary files from linting in `pyproject.toml`

### Debugging Commands

```bash
# Check Python environment
uv run python -c "import sys; print(sys.version); print(sys.path)"

# Inspect dependencies
uv tree

# Check package installation
uv run python -c "import your_package; print(your_package.__file__)"

# Test imports
uv run python -c "from your_package.main import main; print('Import successful')"

# Check pre-commit configuration
uv run pre-commit run --all-files --verbose

# Docker debugging
docker run -it --entrypoint /bin/bash your-package:latest
```

### Getting Help

1. **GitHub Issues**: Check the template repository's issue tracker
2. **Documentation**:
   - [uv docs](https://docs.astral.sh/uv/)
   - [Ruff docs](https://docs.astral.sh/ruff/)
   - [pytest docs](https://docs.pytest.org/)
3. **Community**: Python Discord, Reddit r/Python
4. **Debugging**: Use `--verbose` flags and check log files
