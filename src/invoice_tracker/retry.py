"""Reusable retry decorator with exponential backoff.

This module provides a generic retry mechanism used by the extractor and
excel_handler modules. It replaces duplicated retry logic with a single,
configurable decorator.
"""

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

import structlog

log = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior.

    Parameters
    ----------
    max_retries : int
        Number of retries after the first attempt (total attempts = max_retries + 1).
    initial_backoff : float
        Initial backoff delay in seconds.
    multiplier : float
        Multiplier applied to backoff each retry (exponential).
    catch : tuple[type[Exception], ...]
        Exception types to catch and retry on.
    """

    max_retries: int = 2
    initial_backoff: float = 1.0
    multiplier: float = 2.0
    catch: tuple[type[Exception], ...] = field(default=(Exception,))


def with_retry(
    config: RetryConfig,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that retries a function with exponential backoff.

    Re-raises the last exception directly (no wrapping).

    Parameters
    ----------
    config : RetryConfig
        Retry configuration.

    Returns
    -------
    Callable
        Decorated function with retry behavior.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.catch as e:
                    last_error = e
                    if attempt < config.max_retries:
                        backoff = config.initial_backoff * (config.multiplier**attempt)
                        log.debug(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=config.max_retries,
                            backoff=backoff,
                            error=str(e),
                        )
                        time.sleep(backoff)

            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator


__all__ = [
    "RetryConfig",
    "with_retry",
]
