"""CLI entry point for invoice-tracker.

This module provides the main entry point for the invoice-tracker CLI tool.
It handles command-line argument parsing, logging configuration, and orchestrates
the invoice processing workflow.
"""

import logging
import sys

import structlog

from invoice_tracker.extractor import check_ollama_connection
from invoice_tracker.processor import process_batch, process_single
from invoice_tracker.settings import Settings

# Exit codes
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_ERROR = 2


def _configure_logging(verbose: bool) -> None:
    """Configure structlog based on verbosity setting.

    Parameters
    ----------
    verbose : bool
        If True, set log level to DEBUG. Otherwise, INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )


def _run_process(settings: Settings) -> int:
    """Execute the process subcommand.

    Parameters
    ----------
    settings : Settings
        Application settings with process subcommand populated.

    Returns
    -------
    int
        Exit code.
    """
    log = structlog.get_logger()

    log.debug("settings_loaded", dry_run=settings.dry_run, verbose=settings.verbose)

    # Check Ollama connection
    if not settings.dry_run:
        if not check_ollama_connection(settings):
            log.error(
                "ollama_connection_failed",
                url=settings.ollama_url,
                model=settings.ollama_model,
            )
            return EXIT_ERROR

    # Process single file or batch
    file = settings.process.file
    if file:
        log.info("processing_single_file", file=str(file))
        result = process_single(file, settings)
        results = [result]
    else:
        log.info("processing_batch")
        results = process_batch(settings)

    # Report summary
    if not results:
        log.info("no_files_processed")
        return EXIT_SUCCESS

    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    log.info("processing_complete", success=success, failed=failed)

    # Return exit code
    if failed == len(results):
        return EXIT_ERROR  # All failed
    elif failed > 0:
        return EXIT_PARTIAL_FAILURE
    return EXIT_SUCCESS


def _run_eval(settings: Settings) -> int:
    """Execute the eval subcommand.

    Parameters
    ----------
    settings : Settings
        Application settings with eval subcommand populated.

    Returns
    -------
    int
        Exit code.
    """
    from invoice_tracker.evaluation import print_summary, run_evaluation

    eval_cmd = settings.eval
    results = run_evaluation(
        eval_cmd.ground_truth,
        eval_cmd.methods,
        settings,
        models=eval_cmd.models,
    )
    print_summary(results)
    return EXIT_SUCCESS


def main() -> int:
    """Execute the invoice-tracker CLI.

    Returns
    -------
    int
        Exit code: 0 for success, 1 for partial failure, 2 for error.
    """
    try:
        # Load settings (parses CLI args automatically)
        settings = Settings()
    except Exception as e:
        # Can't use structlog if Settings failed
        print(f"Error loading settings: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Configure logging
    _configure_logging(settings.verbose)

    try:
        if settings.eval is not None:
            return _run_eval(settings)
        if settings.process is not None:
            return _run_process(settings)

        # No subcommand — print usage
        print("Usage: invoice-tracker {process,eval} [options]", file=sys.stderr)
        return EXIT_ERROR

    except Exception as e:
        log = structlog.get_logger()
        log.exception("unexpected_error", error=str(e))
        return EXIT_ERROR


__all__ = ["main"]
