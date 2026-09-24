"""Promotion detection against stored state, and the Brain-V1-B doctor checks."""

from __future__ import annotations

import pytest
from vorquel_brain_contract import FORBIDDEN_EPISTEMIC_PROMOTIONS

from vorquel_brain_retrieval import (
    InMemoryBrainStore,
    Scope,
    detect_promotion,
    detect_promotions,
    run_doctor,
    violations_only,
)
from vorquel_brain_retrieval.doctor import FAIL, OK, WARN
from vorquel_brain_retrieval.store import COLLECTIONS

# ---------------------------------------------------------------------------
# Promotion detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (before, after)
        for before, afters in FORBIDDEN_EPISTEMIC_PROMOTIONS.items()
        for after in afters
    ],
)
def test_every_forbidden_promotion_is_caught_against_stored_state(store, before, after):
    """The whole forbidden table, with ``before`` read from the store.

    This is the change from Brain-V1-A. The caller supplies only ``after``; the
    stored status is what it is compared against, so a caller cannot make a
    promotion legal by claiming a convenient starting point.
    """
    payload = {key: list(store.all_of(object_type)) for object_type, key in COLLECTIONS.items()}
    stored = dict(store.by_id("Claim", "clm_chaves_dor"), claim_id="clm_probe",
                  epistemic_status=before)
    payload["claims"] = [*payload["claims"], stored]
    variant = InMemoryBrainStore.from_mapping(payload)

    finding = detect_promotion(variant, dict(stored, epistemic_status=after))

    assert finding.before == before
    assert finding.after == after
    assert finding.verdict == finding.FORBIDDEN
    assert finding.violations


def test_a_forbidden_promotion_becomes_a_candidate_conflict_not_a_mutation(store):
    stored = store.by_id("Claim", "clm_santos_hipotese")
    finding = detect_promotion(store, dict(stored, epistemic_status="OBSERVADO"))

    conflict = finding.as_candidate_conflict()
    assert conflict["conflict_type"] == "FORBIDDEN_EPISTEMIC_PROMOTION"
    assert conflict["stored_epistemic_status"] == "INFERIDO"
    assert conflict["proposed_epistemic_status"] == "OBSERVADO"
    assert "not applied" in conflict["resolution"]

    # Nothing was written anywhere.
    assert store.by_id("Claim", "clm_santos_hipotese")["epistemic_status"] == "INFERIDO"


def test_nothing_is_auto_corrected(store):
    """The proposal comes back untouched; only a judgement is returned."""
    stored = store.by_id("Claim", "clm_santos_hipotese")
    proposal = dict(stored, epistemic_status="MEDIDO")
    before = dict(proposal)

    detect_promotion(store, proposal)

    assert proposal == before, "the detector rewrote the proposal it was asked to judge"


def test_a_proposal_for_an_unknown_id_is_a_creation_not_a_promotion(store):
    stored = store.by_id("Claim", "clm_chaves_dor")
    finding = detect_promotion(store, dict(stored, claim_id="clm_brand_new"))
    assert finding.verdict == finding.NEW_OBJECT
    assert finding.before is None
    assert finding.violations == ()


def test_many_proposals_are_judged_in_the_order_given(store):
    stored = store.by_id("Claim", "clm_santos_hipotese")
    findings = detect_promotions(
        store,
        [
            dict(stored, epistemic_status="MEDIDO"),
            dict(stored, epistemic_status="INFERIDO"),
            dict(stored, claim_id="clm_novo"),
        ],
    )
    assert [f.verdict for f in findings] == [
        findings[0].FORBIDDEN,
        findings[1].UNCHANGED,
        findings[2].NEW_OBJECT,
    ]
    assert len(violations_only(findings)) == 1


def test_an_unpromotable_object_type_is_refused(store):
    with pytest.raises(ValueError, match="no promotable epistemic status"):
        detect_promotion(store, store.by_id("Decision", "dec_jacq_escopo"))


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def test_the_doctor_runs_every_brain_v1_b_check(store, repo_root):
    report = run_doctor(store, repo_root=repo_root)
    assert {f.check for f in report.findings} == {
        "enum_drift",
        "scope_storage_mismatch",
        "broken_provenance",
        "stale_state",
        "cross_scope_leak",
        "secret_pack_risk",
        "invalid_promotion",
    }


def test_the_healthy_checks_pass_on_the_fixture(store, repo_root):
    report = run_doctor(store, repo_root=repo_root)
    by_check = {f.check: f for f in report.findings}
    for check in ("enum_drift", "scope_storage_mismatch", "broken_provenance",
                  "cross_scope_leak", "secret_pack_risk", "invalid_promotion"):
        assert by_check[check].status == OK, f"{check}: {by_check[check].message}"


def test_the_doctor_reports_the_deliberately_stale_projection(store, repo_root):
    """The fixture carries one stale projection so this check has something to find."""
    report = run_doctor(store, repo_root=repo_root)
    finding = next(f for f in report.findings if f.check == "stale_state")
    assert finding.status == WARN
    assert any("sp_chaves_antigo" in detail for detail in finding.details)
    assert report.overall == WARN


def test_the_doctor_reports_and_never_repairs(store, repo_root):
    """Running it twice changes nothing, because it changes nothing."""
    before = store.fingerprint()
    run_doctor(store, repo_root=repo_root)
    run_doctor(store, repo_root=repo_root)
    assert store.fingerprint() == before


def _variant(store, **collections):
    payload = {key: list(store.all_of(object_type)) for object_type, key in COLLECTIONS.items()}
    payload.update(collections)
    return InMemoryBrainStore.from_mapping(payload)


def test_the_doctor_detects_broken_provenance(store, repo_root):
    broken = dict(
        store.by_id("Claim", "clm_chaves_tempo"),
        claim_id="clm_fonte_fantasma",
        source_ids=["src_nao_existe"],
        provenance=[{"source_id": "src_nao_existe"}],
    )
    variant = _variant(store, claims=[*store.all_of("Claim"), broken])

    finding = next(f for f in run_doctor(variant, repo_root=repo_root).findings
                   if f.check == "broken_provenance")
    assert finding.status == FAIL
    assert any("src_nao_existe" in detail for detail in finding.details)


def test_the_doctor_detects_a_cross_scope_reference(store, repo_root):
    leaking = dict(
        store.by_id("Claim", "clm_jacq_dor"),
        claim_id="clm_vazamento",
        subject_entity_id="ent_clinica",
    )
    variant = _variant(store, claims=[*store.all_of("Claim"), leaking])

    finding = next(f for f in run_doctor(variant, repo_root=repo_root).findings
                   if f.check == "cross_scope_leak")
    assert finding.status == FAIL
    assert any("clm_vazamento" in detail for detail in finding.details)


def test_the_doctor_detects_a_secret_reachable_from_a_non_secret_object(store, repo_root):
    reaching = dict(
        store.by_id("Claim", "clm_chaves_dor"),
        claim_id="clm_aponta_segredo",
        object_entity_id="ent_cofre",
        scope=Scope("CLIENT", "chaves").as_mapping(),
    )
    variant = _variant(store, claims=[*store.all_of("Claim"), reaching])

    finding = next(f for f in run_doctor(variant, repo_root=repo_root).findings
                   if f.check == "secret_pack_risk")
    assert finding.status == FAIL
    assert any("ent_cofre" in detail for detail in finding.details)


def test_the_doctor_detects_a_promotion_already_stored(store, repo_root):
    promoted = dict(
        store.by_id("Claim", "clm_chaves_tempo"),
        claim_id="clm_promovido",
        epistemic_status="MEDIDO",
        supersedes="clm_santos_hipotese",
    )
    variant = _variant(store, claims=[*store.all_of("Claim"), promoted])

    finding = next(f for f in run_doctor(variant, repo_root=repo_root).findings
                   if f.check == "invalid_promotion")
    assert finding.status == FAIL
    assert any("clm_promovido" in detail for detail in finding.details)
