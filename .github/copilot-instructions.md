# GitHub Copilot Instructions

This file provides context and guidelines for GitHub Copilot when working on this Python project.

## Project Context

This is a modern Python project template using:
- **uv** for dependency management and virtual environments
- **ruff** for linting and code formatting
- **pytest** for testing with coverage reporting
- **mypy** for static type checking
- **pre-commit** for automated code quality checks
- **Docker** for containerization
- **GitHub Actions** for CI/CD

The project follows modern Python best practices with type hints, comprehensive testing, and automated quality checks.

This template uses Python 3.13.7 and uv's modern dependency-groups format for organizing dependencies.

## Code Style & Standards

### Python Code
- Use Python 3.13.7+ features and syntax
- Follow PEP 8 style guidelines (enforced by ruff)
- Use type hints for all functions and methods
- Prefer f-strings over .format() or % formatting
- Use dataclasses or Pydantic models for structured data
- Follow the principle of least surprise in API design

### Testing
- Write tests using pytest
- Aim for >80% code coverage
- Use descriptive test function names that explain what is being tested
- Group related tests in classes when appropriate
- Use fixtures for common test setup
- Mock external dependencies appropriately

### Naming Conventions
- Use snake_case for variables, functions, and module names
- Use PascalCase for class names
- Use UPPER_CASE for constants
- Use descriptive names that clearly indicate purpose
- Prefix internal/private methods with underscore (_)

## Architecture Patterns

### Project Structure
```
src/
├── your_package/
│   ├── __init__.py
│   ├── main.py          # Entry point
│   ├── config.py        # Configuration management
│   ├── models/          # Data models (Pydantic/dataclasses)
│   ├── services/        # Business logic
│   ├── utils/           # Utility functions
│   └── exceptions.py    # Custom exceptions
tests/
├── conftest.py          # Pytest configuration and fixtures
├── unit/                # Unit tests
├── integration/         # Integration tests
└── test_*.py           # Test modules
```

### Dependencies
- Use uv's dependency-groups format in pyproject.toml instead of optional-dependencies
- Organize dependencies into logical groups (dev, app, test, etc.)
- Example: `[dependency-groups]` section with `dev = ["pytest", "mypy", ...]`

### Dependency Injection
- Use dependency injection for services and external dependencies
- Create abstract base classes for services that have multiple implementations
- Use factory patterns for complex object creation

### Error Handling
- Create custom exception classes that inherit from appropriate base exceptions
- Use specific exception types rather than generic Exception
- Include helpful error messages with context
- Log errors appropriately with structured logging

### Configuration
Prefer environment-based configuration using Pydantic Settings:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "My App"
    debug: bool = False

    class Config:
        env_file = ".env"
```

### Logging
Use structured logging with the standard library:

```python
import logging

logger = logging.getLogger(__name__)

def example_function():
    logger.info("Processing started", extra={"user_id": 123})
    # ... function logic
    logger.info("Processing completed successfully")
```

## Development Workflow

### Before Coding
1. Understand the existing codebase structure
2. Check if similar functionality already exists
3. Consider the impact on existing APIs and backwards compatibility
4. Write or update tests first when practicing TDD

### While Coding
1. Run tests frequently: `uv run pytest`
2. Use type hints and run mypy: `uv run mypy src/`
3. Format code with ruff: `uv run ruff format .`
4. Check for linting issues: `uv run ruff check .`

### Code Review
- Write clear commit messages
- Keep PRs focused and reasonably sized
- Include tests for new functionality
- Update documentation when needed
- Ensure all CI checks pass

## Tools and Commands

### Development
```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/

# Run pre-commit hooks
uv run pre-commit run --all-files
```

### Dependencies
```bash
# Add dependency to main dependencies
uv add package-name

# Add dependency to specific group (using dependency-groups)
uv add --group dev package-name
uv add --group app package-name

# Update dependencies
uv sync --upgrade
```

## AI Assistant Guidelines

When generating code:
1. Always include appropriate type hints
2. Add docstrings for public functions and classes
3. Include error handling for expected failure cases
4. Suggest relevant tests for new functionality
5. Consider performance implications for data processing code
6. Follow the existing code patterns and architecture
7. Use the project's existing dependencies when possible

## Anti-Patterns to Avoid

- Don't use `import *` statements
- Avoid deeply nested code - prefer early returns
- Don't catch exceptions without proper handling
- Avoid hardcoded values - use configuration instead
- Don't write functions that do too many things
- Avoid mutable default arguments
- Don't ignore type checker warnings without good reason
- Avoid blocking I/O in async contexts
- Don't write tests that depend on external services without mocking
- Avoid circular imports between modules

## Data Science Specific Guidelines

When working with data science code:
- Use pandas for data manipulation with proper error handling
- Prefer Polars for performance-critical data processing
- Use type hints with pandas/numpy types when possible
- Validate data schemas with Pydantic or Pandera
- Use appropriate data formats (Parquet > CSV for performance)
- Include data validation and quality checks
- Document data transformations clearly
- Use logging to track data processing steps
