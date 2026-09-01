"""
Unit tests for EntityDiffEngine.
Verifies extraction, normalization, and divergence detection across durations,
currencies, versions, standards (RFC/ISO), dates, percentages, and clause numbers.
"""
import pytest
from backend.app.schemas.comparison import EntityType
from backend.app.services.entity_diff import EntityDiffEngine, entity_diff_engine


def test_entity_diff_durations():
    """Verifies detection of duration changes (e.g. 30 days vs 90 days)."""
    text_a = "Backups are retained for 30 days in cold storage."
    text_b = "Backups are retained for 90 days in cold storage."

    diffs = entity_diff_engine.compute_entity_diffs(text_a, text_b)

    duration_diffs = [d for d in diffs if d.entity_type == EntityType.DURATION.value]
    assert len(duration_diffs) == 1
    assert duration_diffs[0].value_a == "30 days"
    assert duration_diffs[0].value_b == "90 days"
    assert duration_diffs[0].is_divergent is True


def test_entity_diff_currency_normalization():
    """Verifies currency normalization ($50,000 vs USD 50,000)."""
    # Identical values in different formats -> not divergent
    text_a = "Project budget is capped at $50,000."
    text_b = "Project budget is capped at USD 50000."

    diffs = entity_diff_engine.compute_entity_diffs(text_a, text_b)
    curr_diffs = [d for d in diffs if d.entity_type == EntityType.CURRENCY.value]
    assert len(curr_diffs) == 1
    assert curr_diffs[0].is_divergent is False

    # Different currency values -> divergent
    text_c = "Project budget is capped at $250,000."
    diffs_c = entity_diff_engine.compute_entity_diffs(text_a, text_c)
    curr_diffs_c = [d for d in diffs_c if d.entity_type == EntityType.CURRENCY.value]
    assert len(curr_diffs_c) == 1
    assert curr_diffs_c[0].is_divergent is True


def test_entity_diff_standards_and_versions():
    """Verifies software versions and RFC/ISO standard references."""
    text_a = "Auth is governed by RFC-7519 under v1.4.0."
    text_b = "Auth is governed by RFC-7515 under v2.0.0."

    diffs = entity_diff_engine.compute_entity_diffs(text_a, text_b)

    rfc_diffs = [d for d in diffs if d.entity_type == EntityType.RFC.value]
    ver_diffs = [d for d in diffs if d.entity_type == EntityType.VERSION.value]

    assert len(rfc_diffs) == 1
    assert rfc_diffs[0].is_divergent is True

    assert len(ver_diffs) == 1
    assert ver_diffs[0].is_divergent is True


def test_entity_diff_percentages_and_dates():
    """Verifies percentages and dates."""
    text_a = "Margin is set at 5% effective 2025-01-01."
    text_b = "Margin is set at 10% effective 2026-01-01."

    diffs = entity_diff_engine.compute_entity_diffs(text_a, text_b)

    pct_diffs = [d for d in diffs if d.entity_type == EntityType.PERCENTAGE.value]
    date_diffs = [d for d in diffs if d.entity_type == EntityType.DATE.value]

    assert len(pct_diffs) == 1
    assert pct_diffs[0].is_divergent is True

    assert len(date_diffs) == 1
    assert date_diffs[0].is_divergent is True


def test_entity_diff_missing_concept_not_divergent():
    """Verifies that an entity present in only one clause (e.g. 10 minutes lockout) is NOT flagged as divergent."""
    text_a = "All corporate documents must be stored in encrypted repositories with multi-factor authentication enforced."
    text_b = "Passwords must be at least 12 characters long. Accounts are locked after 5 failed login attempts within 10 minutes."

    diffs = entity_diff_engine.compute_entity_diffs(text_a, text_b)

    # Durations: only present in text_b (10 minutes) -> value_a is None -> is_divergent MUST be False
    duration_diffs = [d for d in diffs if d.entity_type == EntityType.DURATION.value]
    assert len(duration_diffs) == 1
    assert duration_diffs[0].value_a is None
    assert duration_diffs[0].value_b == "10 minutes"
    assert duration_diffs[0].is_divergent is False

    # Numbers: only present in text_b (12, 5) -> value_a is None -> is_divergent MUST be False
    number_diffs = [d for d in diffs if d.entity_type == EntityType.NUMBER.value]
    for nd in number_diffs:
        if nd.value_a is None or nd.value_b is None:
            assert nd.is_divergent is False
