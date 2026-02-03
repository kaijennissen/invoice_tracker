"""Tests for the evaluation module."""

from datetime import date

import pytest

from invoice_tracker.evaluation import (
    CURRENCY_MAP,
    InvoiceScore,
    MatchResult,
    match_amount,
    match_currency,
    match_exact,
    match_fuzzy,
    score_invoice,
)
from invoice_tracker.settings import InvoiceData


class TestMatchExact:
    """Tests for match_exact function."""

    def test_exact_match(self):
        """Identical strings should match with score 1.0."""
        result = match_exact("INV-001", "INV-001")
        assert result.matched is True
        assert result.score == 1.0

    def test_no_match(self):
        """Different strings should not match."""
        result = match_exact("INV-001", "INV-002")
        assert result.matched is False
        assert result.score == 0.0

    def test_both_none(self):
        """Both None values should match."""
        result = match_exact(None, None)
        assert result.matched is True
        assert result.score == 1.0

    def test_extracted_none(self):
        """Extracted None should not match expected value."""
        result = match_exact(None, "INV-001")
        assert result.matched is False
        assert result.score == 0.0

    def test_expected_none(self):
        """Expected None should not match extracted value."""
        result = match_exact("INV-001", None)
        assert result.matched is False
        assert result.score == 0.0

    def test_date_strings(self):
        """Date strings should match exactly."""
        result = match_exact("2024-01-15", "2024-01-15")
        assert result.matched is True
        assert result.score == 1.0


class TestMatchFuzzy:
    """Tests for match_fuzzy function."""

    def test_exact_match(self):
        """Identical strings should have similarity 1.0."""
        result = match_fuzzy("Acme Corp", "Acme Corp")
        assert result.matched is True
        assert result.score == 1.0

    def test_case_insensitive(self):
        """Comparison should be case-insensitive."""
        result = match_fuzzy("ACME CORP", "acme corp")
        assert result.matched is True
        assert result.score == 1.0

    def test_similar_strings(self):
        """Similar strings should have meaningful similarity score."""
        result = match_fuzzy("Acme Corporation", "Acme Corp")
        assert result.score >= 0.5  # Reasonable similarity
        # More similar strings should score higher
        result2 = match_fuzzy("Acme Corp", "Acme Cor")
        assert result2.score > result.score

    def test_dissimilar_strings(self):
        """Very different strings should not match."""
        result = match_fuzzy("Alpha Company", "Zeta Industries")
        assert result.matched is False
        assert result.score < 0.5

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        result = match_fuzzy("Acme", "Acne", threshold=0.5)
        assert result.matched is True
        assert result.score >= 0.5

        result = match_fuzzy("Acme", "Acne", threshold=0.9)
        assert result.matched is False

    def test_both_none(self):
        """Both None values should match."""
        result = match_fuzzy(None, None)
        assert result.matched is True
        assert result.score == 1.0

    def test_extracted_none(self):
        """Extracted None should not match expected value."""
        result = match_fuzzy(None, "Acme")
        assert result.matched is False
        assert result.score == 0.0

    def test_empty_strings(self):
        """Empty strings should match."""
        result = match_fuzzy("", "")
        assert result.matched is True
        assert result.score == 1.0

    def test_whitespace_handling(self):
        """Whitespace should be stripped."""
        result = match_fuzzy("  Acme Corp  ", "Acme Corp")
        assert result.matched is True
        assert result.score == 1.0


class TestMatchAmount:
    """Tests for match_amount function."""

    def test_exact_match(self):
        """Identical amounts should match."""
        result = match_amount(1234.56, 1234.56)
        assert result.matched is True
        assert result.score == 1.0

    def test_within_absolute_tolerance(self):
        """Amounts within absolute tolerance should match."""
        result = match_amount(1234.56, 1234.57, abs_tolerance=0.01)
        assert result.matched is True
        assert result.score == 1.0

    def test_within_relative_tolerance(self):
        """Amounts within relative tolerance should match."""
        result = match_amount(1000.0, 1001.0, rel_tolerance=0.002)
        assert result.matched is True
        assert result.score == 1.0

    def test_outside_tolerance(self):
        """Amounts outside both tolerances should not match."""
        result = match_amount(1000.0, 1100.0, abs_tolerance=0.01, rel_tolerance=0.001)
        assert result.matched is False
        assert result.score == 0.0

    def test_both_none(self):
        """Both None values should match."""
        result = match_amount(None, None)
        assert result.matched is True
        assert result.score == 1.0

    def test_extracted_none(self):
        """Extracted None should not match expected value."""
        result = match_amount(None, 1234.56)
        assert result.matched is False
        assert result.score == 0.0

    def test_zero_expected(self):
        """Zero expected amount should handle division safely."""
        result = match_amount(0.005, 0.0, abs_tolerance=0.01)
        assert result.matched is True
        assert result.score == 1.0


class TestMatchCurrency:
    """Tests for match_currency function."""

    def test_exact_code_match(self):
        """Identical currency codes should match."""
        result = match_currency("EUR", "EUR")
        assert result.matched is True
        assert result.score == 1.0

    def test_symbol_to_code(self):
        """Currency symbols should normalize to codes."""
        result = match_currency("EUR", "EUR")
        assert result.matched is True

    def test_euro_symbol(self):
        """Euro symbol should match EUR code."""
        assert CURRENCY_MAP["€"] == "EUR"
        result = match_currency("€", "EUR")
        assert result.matched is True
        assert result.score == 1.0

    def test_dollar_symbol(self):
        """Dollar symbol should match USD code."""
        assert CURRENCY_MAP["$"] == "USD"
        result = match_currency("$", "USD")
        assert result.matched is True
        assert result.score == 1.0

    def test_pound_symbol(self):
        """Pound symbol should match GBP code."""
        assert CURRENCY_MAP["£"] == "GBP"
        result = match_currency("£", "GBP")
        assert result.matched is True
        assert result.score == 1.0

    def test_case_insensitive(self):
        """Currency codes should be case-insensitive."""
        result = match_currency("eur", "EUR")
        assert result.matched is True
        assert result.score == 1.0

    def test_mismatched_currencies(self):
        """Different currencies should not match."""
        result = match_currency("EUR", "USD")
        assert result.matched is False
        assert result.score == 0.0

    def test_both_none(self):
        """Both None values should match."""
        result = match_currency(None, None)
        assert result.matched is True
        assert result.score == 1.0

    def test_extracted_none(self):
        """Extracted None should not match expected value."""
        result = match_currency(None, "EUR")
        assert result.matched is False
        assert result.score == 0.0

    def test_whitespace_handling(self):
        """Whitespace should be stripped."""
        result = match_currency(" EUR ", "EUR")
        assert result.matched is True
        assert result.score == 1.0


class TestScoreInvoice:
    """Tests for score_invoice function."""

    @pytest.fixture
    def sample_extracted(self) -> InvoiceData:
        """Create sample extracted invoice data."""
        return InvoiceData(
            party="Acme Corporation",
            invoice_id="INV-2024-00123",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            amount=1234.56,
            currency="EUR",
            recipient="John Doe",
        )

    @pytest.fixture
    def sample_expected(self) -> dict:
        """Create sample expected values."""
        return {
            "invoice_file": "invoices/test.pdf",
            "party": "Acme Corporation",
            "invoice_id": "INV-2024-00123",
            "issue_date": "2024-01-15",
            "due_date": "2024-02-15",
            "amount": 1234.56,
            "currency": "EUR",
            "recipient": "John Doe",
        }

    def test_perfect_match(self, sample_extracted, sample_expected):
        """Perfect match should have score 1.0."""
        result = score_invoice(sample_extracted, sample_expected, "test")
        assert result.overall_score == 1.0
        assert result.method == "test"
        assert all(fs.matched for fs in result.field_scores.values())

    def test_partial_match(self, sample_extracted, sample_expected):
        """Partial match should have score between 0 and 1."""
        sample_expected["invoice_id"] = "DIFFERENT-ID"
        result = score_invoice(sample_extracted, sample_expected, "test")
        assert 0.0 < result.overall_score < 1.0
        assert result.field_scores["invoice_id"].matched is False

    def test_all_fields_scored(self, sample_extracted, sample_expected):
        """All defined fields should be scored."""
        result = score_invoice(sample_extracted, sample_expected, "test")
        expected_fields = {"party", "invoice_id", "issue_date", "due_date", "amount", "currency", "recipient"}
        assert set(result.field_scores.keys()) == expected_fields

    def test_fuzzy_party_matching(self, sample_extracted, sample_expected):
        """Party field should use fuzzy matching."""
        sample_expected["party"] = "Acme Corp"  # Slightly different
        result = score_invoice(sample_extracted, sample_expected, "test")
        # Should still be a partial match due to fuzzy matching
        assert result.field_scores["party"].score > 0.5

    def test_amount_tolerance(self, sample_extracted, sample_expected):
        """Amount should match within tolerance."""
        sample_expected["amount"] = 1234.565  # Tiny difference
        result = score_invoice(sample_extracted, sample_expected, "test")
        assert result.field_scores["amount"].matched is True


class TestInvoiceScoreDataclass:
    """Tests for InvoiceScore dataclass."""

    def test_creation(self):
        """InvoiceScore should be created with all fields."""
        score = InvoiceScore(
            invoice_file="test.pdf",
            method="baml",
            overall_score=0.95,
            field_scores={"party": MatchResult(True, 1.0, "Match")},
        )
        assert score.invoice_file == "test.pdf"
        assert score.method == "baml"
        assert score.overall_score == 0.95
        assert "party" in score.field_scores

    def test_default_field_scores(self):
        """field_scores should default to empty dict."""
        score = InvoiceScore(
            invoice_file="test.pdf",
            method="baml",
            overall_score=0.5,
        )
        assert score.field_scores == {}


class TestMatchResultDataclass:
    """Tests for MatchResult dataclass."""

    def test_creation(self):
        """MatchResult should be created with all fields."""
        result = MatchResult(matched=True, score=0.95, details="Test details")
        assert result.matched is True
        assert result.score == 0.95
        assert result.details == "Test details"
