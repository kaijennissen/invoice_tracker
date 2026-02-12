"""Tests for invoice_tracker.retry module."""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import pytest

from invoice_tracker.retry import RetryConfig, with_retry


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """RetryConfig has sensible defaults."""
        config = RetryConfig()

        assert config.max_retries == 2
        assert config.initial_backoff == 1.0
        assert config.multiplier == 2.0
        assert config.catch == (Exception,)

    def test_custom_values(self) -> None:
        """RetryConfig accepts custom values."""
        config = RetryConfig(
            max_retries=5,
            initial_backoff=0.5,
            multiplier=3.0,
            catch=(ValueError, TypeError),
        )

        assert config.max_retries == 5
        assert config.initial_backoff == 0.5
        assert config.multiplier == 3.0
        assert config.catch == (ValueError, TypeError)

    def test_frozen_immutability(self) -> None:
        """RetryConfig is immutable (frozen dataclass)."""
        config = RetryConfig()

        with pytest.raises(FrozenInstanceError):
            config.max_retries = 10  # type: ignore[misc]


class TestWithRetry:
    """Tests for with_retry decorator."""

    def test_success_on_first_try(self) -> None:
        """Decorated function returns on first success without retrying."""
        config = RetryConfig(max_retries=2)
        mock_fn = MagicMock(return_value="result")

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        result = fn()

        assert result == "result"
        assert mock_fn.call_count == 1

    def test_retry_then_succeed(self) -> None:
        """Decorated function retries on failure then returns on success."""
        config = RetryConfig(max_retries=2)
        mock_fn = MagicMock(
            side_effect=[ValueError("fail"), ValueError("fail"), "result"]
        )

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        with patch("invoice_tracker.retry.time.sleep"):
            result = fn()

        assert result == "result"
        assert mock_fn.call_count == 3

    def test_max_retries_exhausted(self) -> None:
        """Decorated function raises last exception after all retries."""
        config = RetryConfig(max_retries=2)
        error = ValueError("persistent failure")
        mock_fn = MagicMock(side_effect=error)

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        with patch("invoice_tracker.retry.time.sleep"):
            with pytest.raises(ValueError, match="persistent failure"):
                fn()

        assert mock_fn.call_count == 3  # 1 initial + 2 retries

    def test_only_catches_specified_exceptions(self) -> None:
        """Decorated function only retries on specified exception types."""
        config = RetryConfig(max_retries=2, catch=(ValueError,))
        mock_fn = MagicMock(side_effect=TypeError("wrong type"))

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        with pytest.raises(TypeError, match="wrong type"):
            fn()

        assert mock_fn.call_count == 1  # No retry for unmatched exception

    def test_exponential_backoff_timing(self) -> None:
        """Decorated function uses exponential backoff between retries."""
        config = RetryConfig(max_retries=3, initial_backoff=1.0, multiplier=2.0)
        mock_fn = MagicMock(side_effect=ValueError("fail"))

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        with patch("invoice_tracker.retry.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                fn()

            # backoff: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0, 1.0 * 2^2 = 4.0
            assert mock_sleep.call_count == 3
            mock_sleep.assert_any_call(1.0)
            mock_sleep.assert_any_call(2.0)
            mock_sleep.assert_any_call(4.0)

    def test_preserves_function_metadata(self) -> None:
        """Decorated function preserves original function's metadata."""
        config = RetryConfig()

        @with_retry(config)
        def my_function() -> str:
            """My docstring."""
            return "result"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_zero_retries_single_attempt(self) -> None:
        """Zero max_retries means only one attempt, no retries."""
        config = RetryConfig(max_retries=0)
        mock_fn = MagicMock(side_effect=ValueError("fail"))

        @with_retry(config)
        def fn() -> str:
            return mock_fn()

        with pytest.raises(ValueError, match="fail"):
            fn()

        assert mock_fn.call_count == 1
