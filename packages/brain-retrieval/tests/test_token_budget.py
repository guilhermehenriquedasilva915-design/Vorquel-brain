"""Token budgeting: what it cuts, in what order, and when it refuses."""

from __future__ import annotations

import pytest
from vorquel_brain_contract import structural_errors

from vorquel_brain_retrieval import (
    DROP_ORDER,
    NON_DROPPABLE,
    BudgetTooSmallError,
    estimate_tokens,
    get_context_pack,
)


def pack_at(store, scope, budget, **overrides):
    return get_context_pack(
        store,
        "reduzir tempo de resposta ao lead",
        scope,
        mode="AUDIT",
        token_budget=budget,
        entity_ids=("ent_chaves_hugo",),
        requirements=("skill:a", "skill:b", "skill:c"),
        **overrides,
    )


def test_the_estimator_is_deterministic_and_monotone():
    assert estimate_tokens("abcd") == estimate_tokens("abcd")
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)
    assert estimate_tokens([1, 2, 3]) > estimate_tokens([1, 2])
    assert estimate_tokens(None) == 0


def test_an_untrimmed_pack_reports_its_own_size_honestly(store, chaves):
    result = pack_at(store, chaves, 8000)
    assert result.estimated_tokens == estimate_tokens(result.pack)
    assert result.estimated_tokens <= 8000
    assert not result.trim_log


def test_a_tight_budget_trims_and_says_what_it_trimmed(store, chaves):
    generous = pack_at(store, chaves, 8000)
    tight = pack_at(store, chaves, 780)

    assert tight.estimated_tokens < generous.estimated_tokens
    assert tight.trim_log, "the pack shrank without recording why"
    assert any("trimmed for token budget" in gap for gap in tight.pack["gaps"])
    assert structural_errors(tight.pack) == []


def test_weaker_evidence_goes_before_stronger(store, chaves):
    generous = set(pack_at(store, chaves, 8000).pack["evidence_ids"])
    tight = set(pack_at(store, chaves, 780).pack["evidence_ids"])

    dropped = generous - tight
    assert dropped, "nothing was dropped, so the ordering claim is untested"

    strengths = {
        evidence_id: store.by_id("Evidence", evidence_id)["strength"]
        for evidence_id in generous
    }
    order = {"WEAK": 0, "MODERATE": 1, "STRONG": 2}
    worst_kept = min(order[strengths[e]] for e in tight)
    best_dropped = max(order[strengths[e]] for e in dropped)
    assert best_dropped <= worst_kept, "a stronger item was dropped before a weaker one"


def test_provenance_is_never_dropped_from_a_retained_item(store, chaves):
    for budget in (8000, 2000, 1000, 820, 800, 780, 760, 740):
        try:
            pack = pack_at(store, chaves, budget).pack
        except BudgetTooSmallError:
            continue
        kept = set(pack["claim_ids"]) | set(pack["evidence_ids"])
        traced = {entry["object_id"] for entry in pack["provenance_summary"]}
        assert kept <= traced, f"budget {budget} left an item without provenance"
        # ...and the reverse: no provenance entry outlives its item.
        assert traced <= kept, f"budget {budget} kept provenance for a dropped item"


def test_the_non_droppable_core_survives_every_issued_pack(store, chaves):
    for budget in (8000, 1000, 800, 760, 740):
        try:
            pack = pack_at(store, chaves, budget).pack
        except BudgetTooSmallError:
            continue
        for field in NON_DROPPABLE:
            assert field in pack, f"{field} was dropped at budget {budget}"
        assert pack["constraints"], "the constraints that limit action were dropped"
        assert pack["scope"]
        assert pack["objective"]


def test_an_issued_pack_never_exceeds_its_own_budget(store, chaves):
    for budget in range(740, 860, 10):
        try:
            result = pack_at(store, chaves, budget)
        except BudgetTooSmallError:
            continue
        assert result.estimated_tokens <= budget, (
            f"pack issued at budget {budget} costs {result.estimated_tokens}"
        )


def test_recording_a_trim_is_counted_against_the_budget(store, chaves):
    """Saying what was removed is content, and it is measured as content.

    The bug this guards against is subtle and was real: trim, measure, then
    append the explanation, producing a pack that reports a budget it exceeds.
    """
    result = pack_at(store, chaves, 780)
    assert result.trim_log
    assert any("trimmed for token budget" in gap for gap in result.pack["gaps"])
    assert estimate_tokens(result.pack) <= 780


def test_a_budget_too_small_refuses_rather_than_mutilating(store, chaves):
    with pytest.raises(BudgetTooSmallError) as excinfo:
        pack_at(store, chaves, 1)
    error = excinfo.value
    assert error.code == "BUDGET_TOO_SMALL"
    assert error.minimum_required > error.requested
    assert error.missing


def test_the_refusal_quotes_the_smallest_pack_that_could_be_built(store, chaves):
    """The quoted minimum is exact: reachable, and the last budget that is.

    Not the bare core — claim, decision, hypothesis and unknown pointers are not
    droppable, so quoting the core alone would promise a pack that cannot exist.
    And not the size after the final drop step either, because a step that costs
    more than it saves is rolled back rather than applied.
    """
    with pytest.raises(BudgetTooSmallError) as excinfo:
        pack_at(store, chaves, 10)
    minimum = excinfo.value.minimum_required

    # A budget at the quoted minimum succeeds...
    assert pack_at(store, chaves, minimum).estimated_tokens <= minimum
    # ...and one token less does not. The quote is the boundary, not a guess.
    with pytest.raises(BudgetTooSmallError):
        pack_at(store, chaves, minimum - 1)


def test_trimming_is_monotone(store, chaves):
    """Every applied step makes the pack smaller.

    A step that would grow the pack — because the sentence recording the removal
    is longer than what it removed — is rolled back. Without this, "trimming"
    could push a pack over the budget it was trimming towards.
    """
    sizes = []
    for budget in range(690, 900, 7):
        try:
            result = pack_at(store, chaves, budget)
        except BudgetTooSmallError:
            continue
        assert result.estimated_tokens <= budget
        sizes.append((budget, result.estimated_tokens))

    assert sizes, "no pack was issued across the sweep"
    # A larger budget never yields a smaller pack.
    for (_, smaller), (_, larger) in zip(sizes, sizes[1:], strict=False):
        assert larger >= smaller


def test_the_drop_order_is_the_documented_one():
    assert DROP_ORDER == (
        "VERBOSE_SUMMARY",
        "LOW_RELEVANCE_ARTIFACTS",
        "OLDER_EVENTS",
        "WEAKER_EVIDENCE",
        "SECONDARY_PROCEDURAL_REFS",
    )


def test_a_zero_or_negative_budget_is_refused(store, chaves):
    with pytest.raises(ValueError, match="at least 1"):
        pack_at(store, chaves, 0)
