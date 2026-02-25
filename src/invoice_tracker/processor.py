"""Invoice processing pipeline orchestration.

This module provides the orchestration layer that coordinates the invoice
processing workflow: scanning for files, extracting data, validating,
checking for duplicates, persisting, and moving files.
"""

import shutil
from datetime import datetime
from pathlib import Path

import structlog

from invoice_tracker.extractor import extract_invoice
from invoice_tracker.repository import InvoiceRepository, create_repository
from invoice_tracker.settings import (
    ExtractionError,
    InvoiceData,
    InvoiceRecord,
    ProcessingResult,
    Settings,
)

log = structlog.get_logger()


def scan_incoming(settings: Settings) -> list[Path]:
    """Scan incoming directory for supported invoice files.

    Parameters
    ----------
    settings : Settings
        Application settings containing directory and extension configuration.

    Returns
    -------
    list[Path]
        List of paths to supported invoice files.
    """
    if not settings.incoming_dir.exists():
        log.warning("incoming_directory_missing", path=str(settings.incoming_dir))
        return []

    files: list[Path] = []
    for ext in settings.supported_extensions:
        files.extend(settings.incoming_dir.glob(f"*{ext}"))
        files.extend(settings.incoming_dir.glob(f"*{ext.upper()}"))

    return sorted(files)


def move_file(source: Path, destination_dir: Path) -> Path:
    """Move a file to the destination directory.

    Handles name conflicts by appending a numeric suffix.

    Parameters
    ----------
    source : Path
        Path to the source file.
    destination_dir : Path
        Directory to move the file to.

    Returns
    -------
    Path
        Path to the moved file.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / source.name

    # Handle name conflicts
    if destination.exists():
        base = source.stem
        suffix = source.suffix
        counter = 1
        while destination.exists():
            destination = destination_dir / f"{base}_{counter}{suffix}"
            counter += 1

    shutil.move(str(source), str(destination))
    return destination


def create_record(data: InvoiceData, source_file: Path) -> InvoiceRecord:
    """Convert extracted data to storage record with metadata.

    Parameters
    ----------
    data : InvoiceData
        Extracted invoice data.
    source_file : Path
        Path to the original invoice file.

    Returns
    -------
    InvoiceRecord
        Invoice record ready for persistence.
    """
    return InvoiceRecord(
        **data.model_dump(),
        source_file=source_file.name,
        processed_at=datetime.now(),
    )


def process_single(
    file: Path,
    settings: Settings,
    repo: InvoiceRepository | None = None,
) -> ProcessingResult:
    """Process a single invoice file.

    Performs the full pipeline: extract, validate, check duplicate, persist, move.
    Respects the dry_run flag.

    Parameters
    ----------
    file : Path
        Path to the invoice file.
    settings : Settings
        Application settings.
    repo : InvoiceRepository | None
        Repository for persistence. Created from settings if not provided.

    Returns
    -------
    ProcessingResult
        Result of processing (success or failure with details).
    """
    log.info("processing_invoice", file=str(file))

    if repo is None:
        repo = create_repository(settings.excel_file)

    # Extract data
    try:
        data = extract_invoice(file, settings)
    except (ExtractionError, FileNotFoundError) as e:
        log.error("extraction_failed", file=str(file), error=str(e))
        if not settings.dry_run:
            move_file(file, settings.failed_dir)
        return ProcessingResult(
            source_file=file,
            success=False,
            error=f"Extraction failed: {e}",
        )

    log.info("extraction_successful", file=str(file), invoice_id=data.invoice_id)

    # Check for duplicate
    if not settings.dry_run:
        repo.initialize()
        if repo.exists(data.invoice_id):
            log.warning(
                "duplicate_invoice",
                file=str(file),
                invoice_id=data.invoice_id,
            )
            # Leave in incoming directory as per error handling spec
            return ProcessingResult(
                source_file=file,
                success=False,
                error=f"Duplicate invoice: {data.invoice_id}",
            )

    # Create record and persist
    if not settings.dry_run:
        record = create_record(data, file)
        repo.save(record)
        log.info("invoice_persisted", file=str(file), invoice_id=data.invoice_id)

        # Move to processed directory
        new_path = move_file(file, settings.processed_dir)
        log.info("file_moved", from_path=str(file), to_path=str(new_path))
    else:
        log.info("dry_run_mode", file=str(file), invoice_id=data.invoice_id)

    return ProcessingResult(
        source_file=file,
        success=True,
        data=data,
    )


def process_batch(
    settings: Settings,
    repo: InvoiceRepository | None = None,
) -> list[ProcessingResult]:
    """Process all invoice files in the incoming directory.

    Continues processing even if individual files fail.

    Parameters
    ----------
    settings : Settings
        Application settings.
    repo : InvoiceRepository | None
        Repository for persistence. Created from settings if not provided.

    Returns
    -------
    list[ProcessingResult]
        List of processing results for each file.
    """
    files = scan_incoming(settings)

    if not files:
        log.info("no_files_to_process")
        return []

    if repo is None:
        repo = create_repository(settings.excel_file)

    log.info("batch_processing_start", file_count=len(files))

    results = []
    for file in files:
        result = process_single(file, settings, repo=repo)
        results.append(result)

    success_count = sum(1 for r in results if r.success)
    log.info(
        "batch_processing_complete",
        total=len(results),
        success=success_count,
        failed=len(results) - success_count,
    )

    return results


__all__ = [
    "scan_incoming",
    "move_file",
    "create_record",
    "process_single",
    "process_batch",
]
