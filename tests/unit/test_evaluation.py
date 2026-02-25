"""Tests for the evaluation module."""

from datetime import date

import pytest

from invoice_tracker.evaluation import (
    InvoiceScore,
    MatchResult,
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
        assert result.score >= 0.5

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
        """Whitespace should be handled gracefully."""
        result = match_fuzzy("  Acme Corp  ", "Acme Corp")
        assert result.matched is True
        assert result.score == 1.0

    def test_missing_middle_name(self):
        """Token set ratio should handle missing tokens gracefully."""
        result = match_fuzzy("John Michael Doe", "John Doe")
        assert result.matched is True
        assert result.score >= 0.85

    def test_reordered_tokens(self):
        """Token set ratio should handle reordered tokens."""
        result = match_fuzzy("Corp Acme", "Acme Corp")
        assert result.matched is True
        assert result.score == 1.0


class TestCurrencyNormalization:
    """Tests for currency normalization on InvoiceData."""

    @pytest.fixture
    def _base_invoice_kwargs(self) -> dict:
        """Base kwargs for creating InvoiceData without currency."""
        return {
            "party": "Test",
            "invoice_id": "INV-1",
            "issue_date": date(2024, 1, 1),
            "due_date": date(2024, 2, 1),
            "amount": 100.0,
            "recipient": "Recipient",
        }

    def test_euro_symbol_normalized(self, _base_invoice_kwargs):
        """Euro symbol should be normalized to EUR."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="€")
        assert invoice.currency == "EUR"

    def test_dollar_symbol_normalized(self, _base_invoice_kwargs):
        """Dollar symbol should be normalized to USD."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="$")
        assert invoice.currency == "USD"

    def test_pound_symbol_normalized(self, _base_invoice_kwargs):
        """Pound symbol should be normalized to GBP."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="£")
        assert invoice.currency == "GBP"

    def test_yen_symbol_normalized(self, _base_invoice_kwargs):
        """Yen symbol should be normalized to JPY."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="¥")
        assert invoice.currency == "JPY"

    def test_iso_code_preserved(self, _base_invoice_kwargs):
        """ISO code should pass through unchanged."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="EUR")
        assert invoice.currency == "EUR"

    def test_lowercase_uppercased(self, _base_invoice_kwargs):
        """Lowercase currency codes should be uppercased."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency="eur")
        assert invoice.currency == "EUR"

    def test_whitespace_stripped(self, _base_invoice_kwargs):
        """Whitespace should be stripped from currency."""
        invoice = InvoiceData(**_base_invoice_kwargs, currency=" EUR ")
        assert invoice.currency == "EUR"


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
        expected_fields = {
            "party",
            "invoice_id",
            "issue_date",
            "due_date",
            "amount",
            "currency",
            "recipient",
        }
        assert set(result.field_scores.keys()) == expected_fields

    def test_fuzzy_party_matching(self, sample_extracted, sample_expected):
        """Party field should use fuzzy matching."""
        sample_expected["party"] = "Acme Corp"
        result = score_invoice(sample_extracted, sample_expected, "test")
        assert result.field_scores["party"].score > 0.5

    def test_amount_exact_matching(self, sample_extracted, sample_expected):
        """Amount uses exact matching — different values should not match."""
        sample_expected["amount"] = 1234.565
        result = score_invoice(sample_extracted, sample_expected, "test")
        assert result.field_scores["amount"].matched is False


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
