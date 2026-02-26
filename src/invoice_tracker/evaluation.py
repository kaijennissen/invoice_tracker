"""Evaluation framework for comparing invoice extraction methods.

This module provides tools to evaluate and compare BAML vs Structured Outputs
extraction methods against ground truth data.
"""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from rapidfuzz import fuzz

from invoice_tracker.extractor import extract_invoice
from invoice_tracker.settings import InvoiceData, Settings

log = structlog.get_logger()


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


def match_fuzzy(
    extracted: str | None, expected: str | None, threshold: float = 0.85
) -> MatchResult:
    """Compare two strings using token set ratio similarity.

    Uses rapidfuzz's token_set_ratio which handles missing words gracefully
    by comparing token sets rather than raw character edits.

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

    # Handle empty strings
    s1 = extracted.strip()
    s2 = expected.strip()
    if not s1 and not s2:
        return MatchResult(matched=True, score=1.0, details="Both empty")

    # token_set_ratio returns 0-100, normalize to 0-1
    similarity = fuzz.token_set_ratio(s1.lower(), s2.lower()) / 100.0
    matched = similarity >= threshold

    return MatchResult(
        matched=matched,
        score=similarity,
        details=f"Similarity: {similarity:.2%} (threshold: {threshold:.0%})",
    )


# Field name to matching function mapping
FIELD_MATCHERS: dict[str, Callable[..., MatchResult]] = {
    "party": match_fuzzy,
    "recipient": match_fuzzy,
}


def score_invoice(extracted: InvoiceData, expected: dict, method: str) -> InvoiceScore:
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

    for field_name in InvoiceData.model_fields:
        extracted_value = getattr(extracted, field_name, None)
        expected_value = expected.get(field_name)

        # Convert date objects to strings for comparison
        if hasattr(extracted_value, "isoformat"):
            extracted_value = extracted_value.isoformat()

        matcher = FIELD_MATCHERS.get(field_name, match_exact)
        field_scores[field_name] = matcher(extracted_value, expected_value)

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


def _is_valid_combo(method: str, model: str) -> bool:
    """Check whether a method/model combination is valid.

    Parameters
    ----------
    method : str
        Extraction method name.
    model : str
        Model identifier.

    Returns
    -------
    bool
        True if the combination can be evaluated.
    """
    # All local Ollama models work with both methods
    return True


def run_evaluation(
    ground_truth_path: Path,
    methods: list[str],
    settings: Settings,
    models: list[str] | None = None,
) -> dict[str, list[InvoiceScore]]:
    """Run evaluation across all ground truth invoices, methods, and models.

    Parameters
    ----------
    ground_truth_path : Path
        Path to ground_truth.json file.
    methods : list[str]
        Extraction methods to evaluate ("baml", "structured_outputs").
    settings : Settings
        Application settings.
    models : list[str] | None
        Models to evaluate. Defaults to [settings.ollama_model].

    Returns
    -------
    dict[str, list[InvoiceScore]]
        Results keyed by composite "method/model" key.
    """
    if models is None:
        models = [settings.ollama_model]

    ground_truth = load_ground_truth(ground_truth_path)
    base_dir = ground_truth_path.parent

    results: dict[str, list[InvoiceScore]] = {}

    for method, model in itertools.product(methods, models):
        if not _is_valid_combo(method, model):
            log.info("skipping_invalid_combo", method=method, model=model)
            continue

        combo_key = f"{method}/{model}"
        eval_settings = settings.model_copy(
            update={"use_baml": method == "baml", "ollama_model": model}
        )
        combo_scores: list[InvoiceScore] = []

        for entry in ground_truth:
            invoice_path = base_dir / entry["invoice_file"]
            expected = entry["expected"]

            try:
                log.info(
                    "extracting_invoice",
                    file=str(invoice_path),
                    method=method,
                    model=model,
                )
                extracted = extract_invoice(invoice_path, eval_settings)
                score = score_invoice(extracted, expected, combo_key)
                score.invoice_file = entry["invoice_file"]
                combo_scores.append(score)

            except Exception as e:
                log.error(
                    "extraction_failed",
                    file=str(invoice_path),
                    method=method,
                    model=model,
                    error=str(e),
                )
                failed_score = InvoiceScore(
                    invoice_file=entry["invoice_file"],
                    method=combo_key,
                    overall_score=0.0,
                    field_scores={
                        f: MatchResult(
                            matched=False, score=0.0, details=f"Extraction failed: {e}"
                        )
                        for f in InvoiceData.model_fields
                    },
                )
                combo_scores.append(failed_score)

        results[combo_key] = combo_scores

    return results


def _has_composite_keys(results: dict[str, list[InvoiceScore]]) -> bool:
    """Check if results use composite method/model keys."""
    return any("/" in key for key in results)


def _print_matrix(results: dict[str, list[InvoiceScore]]) -> None:
    """Print a matrix of average scores with models as rows and methods as columns.

    Parameters
    ----------
    results : dict[str, list[InvoiceScore]]
        Evaluation results keyed by composite "method/model" keys.
    """
    # Parse composite keys into (method, model) tuples
    methods: list[str] = []
    models: list[str] = []
    scores_map: dict[tuple[str, str], float] = {}

    for key, scores in results.items():
        if "/" in key:
            method, model = key.split("/", 1)
        else:
            method, model = key, "default"

        if method not in methods:
            methods.append(method)
        if model not in models:
            models.append(model)

        if scores:
            avg = sum(s.overall_score for s in scores) / len(scores)
        else:
            avg = 0.0
        scores_map[(method, model)] = avg

    # Print matrix
    print("\n" + "=" * 70)
    print("EVALUATION MATRIX (avg score)")
    print("=" * 70)

    # Header
    model_col_width = max(len(m) for m in models) + 2
    method_col_width = 18
    header = f"  {'Model':<{model_col_width}}" + "".join(
        f"{m:>{method_col_width}}" for m in methods
    )
    print(header)
    print("  " + "-" * (model_col_width + method_col_width * len(methods)))

    # Rows
    for model in models:
        row = f"  {model:<{model_col_width}}"
        for method in methods:
            score = scores_map.get((method, model))
            if score is not None:
                row += f"{score:>{method_col_width}.1%}"
            else:
                row += f"{'N/A':>{method_col_width}}"
        print(row)


def print_summary(results: dict[str, list[InvoiceScore]]) -> None:
    """Print a summary of evaluation results to console.

    Parameters
    ----------
    results : dict[str, list[InvoiceScore]]
        Evaluation results keyed by method or composite "method/model" key.
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
            print(
                f"    {field_name:12}: {field_avg:6.1%} ({matches}/{len(field_scores)} exact)"
            )

        # Individual invoice details
        print("\n  Per-invoice scores:")
        for score in scores:
            status = "PASS" if score.overall_score >= 0.85 else "FAIL"
            print(f"    [{status}] {score.invoice_file}: {score.overall_score:.1%}")

    # Print matrix when composite keys are present
    if _has_composite_keys(results):
        _print_matrix(results)

    # Method comparison when 2+ methods
    methods_with_scores = {m: s for m, s in results.items() if s}
    if len(methods_with_scores) >= 2:
        _print_method_comparison(methods_with_scores)

    print("\n" + "=" * 70)


def _print_method_comparison(results: dict[str, list[InvoiceScore]]) -> None:
    """Print cross-method comparison section.

    Parameters
    ----------
    results : dict[str, list[InvoiceScore]]
        Evaluation results with 2+ methods, each having scores.
    """
    methods = list(results.keys())

    print("\n" + "=" * 70)
    print("METHOD COMPARISON")
    print("=" * 70)

    # Per-invoice table
    # Build a map of invoice_file -> {method: score}
    invoice_scores: dict[str, dict[str, float]] = {}
    for method, scores in results.items():
        for score in scores:
            invoice_scores.setdefault(score.invoice_file, {})[method] = (
                score.overall_score
            )

    header = (
        f"  {'Invoice':<30}" + "".join(f"{m:>15}" for m in methods) + f"{'Winner':>15}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for invoice_file, method_scores in sorted(invoice_scores.items()):
        row = f"  {invoice_file:<30}"
        for m in methods:
            row += f"{method_scores.get(m, 0.0):>14.1%} "
        best = max(method_scores, key=lambda m: method_scores[m])
        row += f"{best:>14}"
        print(row)

    # Per-field breakdown
    print(
        f"\n  {'Field':<15}" + "".join(f"{m:>15}" for m in methods) + f"{'Winner':>15}"
    )
    print("  " + "-" * (15 + 15 * len(methods) + 15))

    # Collect field averages per method
    field_avgs: dict[str, dict[str, float]] = {}
    for method, scores in results.items():
        field_totals: dict[str, list[float]] = {}
        for score in scores:
            for field_name, match_result in score.field_scores.items():
                field_totals.setdefault(field_name, []).append(match_result.score)
        for field_name, values in field_totals.items():
            field_avgs.setdefault(field_name, {})[method] = sum(values) / len(values)

    for field_name, method_avgs in sorted(field_avgs.items()):
        row = f"  {field_name:<15}"
        for m in methods:
            row += f"{method_avgs.get(m, 0.0):>14.1%} "
        best = max(method_avgs, key=lambda m: method_avgs[m])
        row += f"{best:>14}"
        print(row)


__all__ = [
    "MatchResult",
    "InvoiceScore",
    "match_exact",
    "match_fuzzy",
    "score_invoice",
    "load_ground_truth",
    "run_evaluation",
    "print_summary",
    "_is_valid_combo",
    "_print_matrix",
    "FIELD_MATCHERS",
]

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate invoice extraction methods")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("data/evaluation/ground_truth.json"),
        help="Path to ground truth JSON file",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["structured_outputs", "baml"],
        help="Extraction methods to evaluate",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["gemma3:27b"],
        help="Models to evaluate (e.g., gemma3:27b qwen2.5:14b)",
    )
    args = parser.parse_args()

    settings = Settings(_cli_parse_args=False)
    results = run_evaluation(
        args.ground_truth, args.methods, settings, models=args.models
    )
    print_summary(results)
