"""Application settings and data models.

This module defines the configuration settings using pydantic-settings
and the data models used throughout the invoice tracking application.

Settings can be configured via:
- CLI arguments: --ollama-model llava
- Environment variables: INVOICE_OLLAMA_MODEL=llava
"""

from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, CliPositionalArg, SettingsConfigDict


class OllamaBackend(str, Enum):
    """Ollama backend selection with baked-in configuration.

    Each backend has an associated base URL and authentication requirements.

    Attributes
    ----------
    LOCAL : str
        Local Ollama instance at localhost:11434.
    CLOUD : str
        Ollama cloud API requiring authentication.
    """

    LOCAL = "local"
    CLOUD = "cloud"

    @property
    def base_url(self) -> str:
        """Get the base URL for this backend.

        Returns
        -------
        str
            The default API endpoint URL.
        """
        return {
            OllamaBackend.LOCAL: "http://localhost:11434",
            OllamaBackend.CLOUD: "https://ollama.com",
        }[self]

    @property
    def requires_api_key(self) -> bool:
        """Check if this backend requires an API key.

        Returns
        -------
        bool
            True if authentication is required.
        """
        return self == OllamaBackend.CLOUD


class Settings(BaseSettings):
    """Invoice tracker configuration.

    All settings can be overridden via:
    - CLI arguments: --ollama-model llava
    - Environment variables: INVOICE_OLLAMA_MODEL=llava
    """

    model_config = SettingsConfigDict(
        cli_parse_args=True,
        cli_prog_name="invoice-tracker",
        cli_kebab_case=True,
        cli_implicit_flags=True,
        env_prefix="INVOICE_",
    )

    # CLI-only arguments
    file: CliPositionalArg[Path | None] = Field(
        default=None,
        description="Single invoice file to process (default: process all in incoming/)",
    )
    dry_run: bool = Field(
        default=False,
        description="Extract and validate without persisting or moving files",
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose/debug logging",
    )

    # Paths (configurable via env vars)
    incoming_dir: Path = Field(
        default=Path("./invoices/incoming"),
        description="Directory to scan for invoice images",
    )
    processed_dir: Path = Field(
        default=Path("./invoices/processed"),
        description="Directory for successfully processed invoices",
    )
    failed_dir: Path = Field(
        default=Path("./invoices/failed"),
        description="Directory for failed extractions",
    )
    excel_file: Path = Field(
        default=Path("./data/tracker.xlsx"),
        description="Excel file for invoice tracking",
    )

    # Ollama settings
    ollama_backend: OllamaBackend = Field(
        default=OllamaBackend.LOCAL,
        description="Ollama backend: 'local' for local instance, 'cloud' for Ollama cloud",
    )
    ollama_api_key: SecretStr | None = Field(
        default=None,
        description="API key for Ollama cloud (required when backend=cloud)",
    )
    ollama_url_override: str | None = Field(
        default=None,
        description="Override the backend's default URL (advanced)",
    )
    ollama_model: str = Field(
        default="gemma3:27b",
        description="Vision model for invoice extraction",
    )
    ollama_timeout: int = Field(
        default=120,
        description="API timeout in seconds",
    )

    # BAML settings
    use_baml: bool = Field(
        default=False,
        description="Use BAML client for extraction instead of direct Ollama client",
    )

    @property
    def ollama_url(self) -> str:
        """Get the effective Ollama API URL.

        Returns the override URL if set, otherwise the backend's default URL.

        Returns
        -------
        str
            The Ollama API endpoint URL.
        """
        return self.ollama_url_override or self.ollama_backend.base_url

    @model_validator(mode="after")
    def validate_ollama_config(self) -> "Settings":
        """Validate Ollama configuration consistency.

        Ensures API key is provided when using a backend that requires it.

        Returns
        -------
        Settings
            The validated instance.

        Raises
        ------
        ValueError
            If API key is missing for a backend that requires it.
        """
        if self.ollama_backend.requires_api_key and not self.ollama_api_key:
            raise ValueError(
                f"ollama_api_key is required when using '{self.ollama_backend.value}' backend"
            )
        return self

    # Processing settings
    supported_extensions: list[str] = Field(
        default_factory=lambda: [".png", ".jpg", ".jpeg", ".pdf"],
        description="Supported image file extensions",
    )


class InvoiceData(BaseModel):
    """Structured data extracted from an invoice.

    This model is used for LLM structured output and validation.

    Attributes
    ----------
    party : str
        Name of the invoicing party/company.
    invoice_id : str
        Unique invoice identifier.
    issue_date : date
        Date the invoice was issued.
    due_date : date
        Payment due date.
    amount : float
        Total amount to pay.
    currency : str
        Currency code (default: EUR).
    recipient : str
        Person/entity the invoice is addressed to.
    """

    party: str = Field(description="Name of the invoicing party/company")
    invoice_id: str = Field(description="Unique invoice identifier")
    issue_date: date = Field(description="Date the invoice was issued (YYYY-MM-DD)")
    due_date: date = Field(description="Payment due date (YYYY-MM-DD)")
    amount: float = Field(description="Total amount to pay")
    currency: str = Field(default="EUR", description="Currency code")
    recipient: str = Field(description="Person/entity the invoice is addressed to")


class InvoiceRecord(InvoiceData):
    """Invoice record for storage.

    Extends InvoiceData with metadata for persistence. Designed for easy
    migration to SQLModel in Phase 2.

    Attributes
    ----------
    source_file : str
        Original invoice filename.
    processed_at : datetime
        Timestamp of processing.
    """

    source_file: str = Field(description="Original invoice filename")
    processed_at: datetime = Field(description="Timestamp of processing")

    @classmethod
    def get_column_headers(cls) -> list[str]:
        """Derive Excel column headers from model fields.

        Returns
        -------
        list[str]
            List of column header names derived from field descriptions.
        """
        return [
            field_info.description or field_name.replace("_", " ").title()
            for field_name, field_info in cls.model_fields.items()
        ]


class ProcessingResult(BaseModel):
    """Result of processing a single invoice.

    Attributes
    ----------
    source_file : Path
        Path to the source invoice file.
    success : bool
        Whether processing was successful.
    data : InvoiceData | None
        Extracted invoice data if successful.
    error : str | None
        Error message if processing failed.
    """

    source_file: Path
    success: bool
    data: InvoiceData | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_consistency(self) -> "ProcessingResult":
        """Validate that success/failure state is consistent with data/error.

        Returns
        -------
        ProcessingResult
            The validated instance.

        Raises
        ------
        ValueError
            If the result state is inconsistent.
        """
        if self.success and self.data is None:
            raise ValueError("Successful result must include data")
        if not self.success and self.error is None:
            raise ValueError("Failed result must include error message")
        return self


class ExtractionError(Exception):
    """Exception raised when invoice extraction fails."""

    pass


__all__ = [
    "OllamaBackend",
    "Settings",
    "InvoiceData",
    "InvoiceRecord",
    "ProcessingResult",
    "ExtractionError",
]
