"""Evaluation framework for comparing invoice extraction methods.

This module provides tools to evaluate and compare BAML vs Structured Outputs
extraction methods against ground truth data.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from invoice_tracker.extractor import extract_invoice
from invoice_tracker.settings import InvoiceData, Settings

log = structlog.get_logger()

# Currency symbol to code mapping
CURRENCY_MAP: dict[str, str] = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "¥": "JPY",
    "CHF": "CHF",
    "EUR": "EUR",
    "USD": "USD",
    "GBP": "GBP",
    "JPY": "JPY",
}


@dataclass
class MatchResult:
    """Result of comparing a single field.

    Attributes
    ----------
    matched : bool
        Whether the field matched according to its strategy.
    score : float
        Match score between 0.0 and 1.0.
    details : str
        Human-readable description of the match result.
    """

    matched: bool
    score: float
    details: str


@dataclass
class InvoiceScore:
    """Evaluation score for a single invoice extraction.

    Attributes
    ----------
    invoice_file : str
        Path to the invoice file.
    method : str
        Extraction method used (e.g., "baml", "structured_outputs").
    overall_score : float
        Average score across all fields.
    field_scores : dict[str, MatchResult]
        Individual match results per field.
    """

    invoice_file: str
    method: str
    overall_score: float
    field_scores: dict[str, MatchResult] = field(default_factory=dict)


def match_exact(extracted: str | None, expected: str | None) -> MatchResult:
    """Compare two values for exact equality.

    Parameters
    ----------
    extracted : str | None
        Value extracted by the model.
    expected : str | None
        Ground truth value.

    Returns
    -------
    MatchResult
        Result with score 1.0 if equal, 0.0 otherwise.
    """
    if extracted is None and expected is None:
        return MatchResult(matched=True, score=1.0, details="Both None")

    if extracted is None or expected is None:
        return MatchResult(
            matched=False,
            score=0.0,
            details=f"Extracted: {extracted!r}, Expected: {expected!r}",
        )

    matched = str(extracted) == str(expected)
    return MatchResult(
        matched=matched,
        score=1.0 if matched else 0.0,
        details=f"Extracted: {extracted!r}, Expected: {expected!r}",
    )


def _levenshtein_similarity(s1: str, s2: str) -> float:
    """Calculate Levenshtein similarity between two strings.

    Parameters
    ----------
    s1 : str
        First string.
    s2 : str
        Second string.

    Returns
    -------
    float
        Similarity score between 0.0 and 1.0.
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Normalize: lowercase and strip whitespace
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if s1 == s2:
        return 1.0

    # Wagner-Fischer algorithm for Levenshtein distance
    len1, len2 = len(s1), len(s2)
    if len1 < len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    current_row = list(range(len2 + 1))

    for i in range(1, len1 + 1):
        previous_row = current_row
        current_row = [i] + [0] * len2

        for j in range(1, len2 + 1):
            add = previous_row[j] + 1
            delete = current_row[j - 1] + 1
            change = previous_row[j - 1] + (0 if s1[i - 1] == s2[j - 1] else 1)
            current_row[j] = min(add, delete, change)

    distance = current_row[len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len)


def match_fuzzy(
    extracted: str | None, expected: str | None, threshold: float = 0.85
) -> MatchResult:
    """Compare two strings using Levenshtein similarity.

    Parameters
    ----------
    extracted : str | None
        Value extracted by the model.
    expected : str | None
        Ground truth value.
    threshold : float
        Minimum similarity for a match (default: 0.85).

    Returns
    -------
    MatchResult
        Result with similarity score and match status.
    """
    if extracted is None and expected is None:
        return MatchResult(matched=True, score=1.0, details="Both None")

    if extracted is None or expected is None:
        return MatchResult(
            matched=False,
            score=0.0,
            details=f"Extracted: {extracted!r}, Expected: {expected!r}",
        )

    similarity = _levenshtein_similarity(extracted, expected)
    matched = similarity >= threshold

    return MatchResult(
        matched=matched,
        score=similarity,
        details=f"Similarity: {similarity:.2%} (threshold: {threshold:.0%})",
    )


def match_amount(
    extracted: float | None,
    expected: float | None,
    abs_tolerance: float = 0.01,
    rel_tolerance: float = 0.001,
) -> MatchResult:
    """Compare two amounts with tolerance.

    Matches if difference is within absolute tolerance OR relative tolerance.

    Parameters
    ----------
    extracted : float | None
        Amount extracted by the model.
    expected : float | None
        Ground truth amount.
    abs_tolerance : float
        Maximum absolute difference (default: 0.01).
    rel_tolerance : float
        Maximum relative difference (default: 0.1%).

    Returns
    -------
    MatchResult
        Result with score based on match status.
    """
    if extracted is None and expected is None:
        return MatchResult(matched=True, score=1.0, details="Both None")

    if extracted is None or expected is None:
        return MatchResult(
            matched=False,
            score=0.0,
            details=f"Extracted: {extracted}, Expected: {expected}",
        )

    abs_diff = abs(extracted - expected)
    rel_diff = abs_diff / abs(expected) if expected != 0 else float("inf")

    matched = abs_diff <= abs_tolerance or rel_diff <= rel_tolerance

    return MatchResult(
        matched=matched,
        score=1.0 if matched else 0.0,
        details=f"Diff: {abs_diff:.4f} (abs tol: {abs_tolerance}, rel: {rel_diff:.4%})",
    )


def match_currency(extracted: str | None, expected: str | None) -> MatchResult:
    """Compare currencies with symbol normalization.

    Maps currency symbols to standard codes before comparison.

    Parameters
    ----------
    extracted : str | None
        Currency extracted by the model (symbol or code).
    expected : str | None
        Ground truth currency (symbol or code).

    Returns
    -------
    MatchResult
        Result with score 1.0 if normalized currencies match.
    """
    if extracted is None and expected is None:
        return MatchResult(matched=True, score=1.0, details="Both None")

    if extracted is None or expected is None:
        return MatchResult(
            matched=False,
            score=0.0,
            details=f"Extracted: {extracted!r}, Expected: {expected!r}",
        )

    # Normalize using currency map, fallback to uppercase original
    norm_extracted = CURRENCY_MAP.get(extracted.strip(), extracted.strip().upper())
    norm_expected = CURRENCY_MAP.get(expected.strip(), expected.strip().upper())

    matched = norm_extracted == norm_expected

    return MatchResult(
        matched=matched,
        score=1.0 if matched else 0.0,
        details=f"Normalized: {norm_extracted} vs {norm_expected}",
    )


# Field name to matching function mapping
FIELD_MATCHERS: dict[str, str] = {
    "party": "fuzzy",
    "invoice_id": "exact",
    "issue_date": "exact",
    "due_date": "exact",
    "amount": "amount",
    "currency": "currency",
    "recipient": "fuzzy",
}


def score_invoice(
    extracted: InvoiceData, expected: dict, method: str
) -> InvoiceScore:
    """Score an extracted invoice against ground truth.

    Parameters
    ----------
    extracted : InvoiceData
        Invoice data extracted by the model.
    expected : dict
        Ground truth expected values.
    method : str
        Extraction method name.

    Returns
    -------
    InvoiceScore
        Detailed scoring results.
    """
    field_scores: dict[str, MatchResult] = {}

    for field_name, matcher_type in FIELD_MATCHERS.items():
        extracted_value = getattr(extracted, field_name, None)
        expected_value = expected.get(field_name)

        # Convert date objects to strings for comparison
        if hasattr(extracted_value, "isoformat"):
            extracted_value = extracted_value.isoformat()

        if matcher_type == "exact":
            result = match_exact(extracted_value, expected_value)
        elif matcher_type == "fuzzy":
            result = match_fuzzy(extracted_value, expected_value)
        elif matcher_type == "amount":
            result = match_amount(extracted_value, expected_value)
        elif matcher_type == "currency":
            result = match_currency(extracted_value, expected_value)
        else:
            result = match_exact(extracted_value, expected_value)

        field_scores[field_name] = result

    # Calculate overall score as average
    overall_score = (
        sum(r.score for r in field_scores.values()) / len(field_scores)
        if field_scores
        else 0.0
    )

    return InvoiceScore(
        invoice_file=expected.get("invoice_file", "unknown"),
        method=method,
        overall_score=overall_score,
        field_scores=field_scores,
    )


def load_ground_truth(ground_truth_path: Path) -> list[dict]:
    """Load ground truth data from JSON file.

    Parameters
    ----------
    ground_truth_path : Path
        Path to ground_truth.json file.

    Returns
    -------
    list[dict]
        List of ground truth entries.

    Raises
    ------
    FileNotFoundError
        If ground truth file doesn't exist.
    json.JSONDecodeError
        If JSON is invalid.
    """
    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {ground_truth_path}")

    with open(ground_truth_path) as f:
        return json.load(f)


def run_evaluation(
    ground_truth_path: Path,
    methods: list[str],
    settings: Settings,
) -> dict[str, list[InvoiceScore]]:
    """Run evaluation across all ground truth invoices and methods.

    Parameters
    ----------
    ground_truth_path : Path
        Path to ground_truth.json file.
    methods : list[str]
        Extraction methods to evaluate ("baml", "structured_outputs").
    settings : Settings
        Application settings.

    Returns
    -------
    dict[str, list[InvoiceScore]]
        Results keyed by method name.
    """
    ground_truth = load_ground_truth(ground_truth_path)
    base_dir = ground_truth_path.parent

    results: dict[str, list[InvoiceScore]] = {method: [] for method in methods}

    for entry in ground_truth:
        invoice_path = base_dir / entry["invoice_file"]
        expected = entry["expected"]

        for method in methods:
            # Configure settings for this method
            use_baml = method == "baml"
            eval_settings = Settings(
                _cli_parse_args=False,
                use_baml=use_baml,
                ollama_backend=settings.ollama_backend,
                ollama_api_key=settings.ollama_api_key,
                ollama_model=settings.ollama_model,
                ollama_timeout=settings.ollama_timeout,
            )

            try:
                log.info(
                    "extracting_invoice",
                    file=str(invoice_path),
                    method=method,
                )
                extracted = extract_invoice(invoice_path, eval_settings)
                score = score_invoice(extracted, expected, method)
                score.invoice_file = entry["invoice_file"]
                results[method].append(score)

            except Exception as e:
                log.error(
                    "extraction_failed",
                    file=str(invoice_path),
                    method=method,
                    error=str(e),
                )
                # Create a zero-score result for failed extractions
                failed_score = InvoiceScore(
                    invoice_file=entry["invoice_file"],
                    method=method,
                    overall_score=0.0,
                    field_scores={
                        field: MatchResult(
                            matched=False, score=0.0, details=f"Extraction failed: {e}"
                        )
                        for field in FIELD_MATCHERS
                    },
                )
                results[method].append(failed_score)

    return results


def print_summary(results: dict[str, list[InvoiceScore]]) -> None:
    """Print a summary of evaluation results to console.

    Parameters
    ----------
    results : dict[str, list[InvoiceScore]]
        Evaluation results keyed by method.
    """
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)

    for method, scores in results.items():
        if not scores:
            print(f"\n{method.upper()}: No results")
            continue

        avg_score = sum(s.overall_score for s in scores) / len(scores)
        perfect_matches = sum(1 for s in scores if s.overall_score == 1.0)

        print(f"\n{method.upper()}")
        print("-" * 40)
        print(f"  Invoices evaluated: {len(scores)}")
        print(f"  Average score:      {avg_score:.2%}")
        print(f"  Perfect matches:    {perfect_matches}/{len(scores)}")

        # Per-field breakdown
        print("\n  Field scores:")
        field_totals: dict[str, list[float]] = {}
        for score in scores:
            for field_name, match_result in score.field_scores.items():
                if field_name not in field_totals:
                    field_totals[field_name] = []
                field_totals[field_name].append(match_result.score)

        for field_name, field_scores in sorted(field_totals.items()):
            field_avg = sum(field_scores) / len(field_scores)
            matches = sum(1 for s in field_scores if s == 1.0)
            print(f"    {field_name:12}: {field_avg:6.1%} ({matches}/{len(field_scores)} exact)")

        # Individual invoice details
        print("\n  Per-invoice scores:")
        for score in scores:
            status = "PASS" if score.overall_score >= 0.85 else "FAIL"
            print(f"    [{status}] {score.invoice_file}: {score.overall_score:.1%}")

    print("\n" + "=" * 70)


__all__ = [
    "MatchResult",
    "InvoiceScore",
    "match_exact",
    "match_fuzzy",
    "match_amount",
    "match_currency",
    "score_invoice",
    "load_ground_truth",
    "run_evaluation",
    "print_summary",
    "CURRENCY_MAP",
    "FIELD_MATCHERS",
]
