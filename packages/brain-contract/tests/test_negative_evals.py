"""The negative evals: the things that must fail, and one graph that must not.

Each fixture in ``fixtures/synthetic`` names the violation codes it is supposed
to produce. A fixture that stops producing them is a regression in the guard,
not in the fixture, which is why the expectation lives beside the data.

The clean baseline matters as much as the failures. Without a graph that
produces nothing, this suite could pass with validators that fire on everything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vorquel_brain_contract import (
    CRITICAL,
    structural_errors,
    validate_graph,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"

#: Failures that are confidentiality incidents rather than data-quality problems.
#: These must be raised at CRITICAL so a caller can tell the two apart.
CRITICAL_CODES = {
    "CROSS_CLIENT_REFERENCE",
    "SECRET_IN_CONTEXT_PACK",
    "NO_EVIDENCE_SERIALIZED_AS_FALSE",
    "FORBIDDEN_FIELD",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_paths() -> list[Path]:
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    assert paths, "no synthetic fixtures found"
    return paths


def _run(case: dict[str, Any]):
    objects: dict[str, dict[str, Any]] = {}
    for key, id_field in (
        ("sources", "source_id"),
        ("evidence", "evidence_id"),
        ("claims", "claim_id"),
        ("decisions", "decision_id"),
        ("projections", "state_projection_id"),
        ("entities", "entity_id"),
    ):
        for obj in case.get(key, []) or []:
            objects[obj[id_field]] = obj

    return validate_graph(
        claims=case.get("claims"),
        evidence=case.get("evidence"),
        decisions=case.get("decisions"),
        candidates=case.get("candidates"),
        projections=case.get("projections"),
        packs=case.get("packs"),
        objects_by_id=objects,
    )


@pytest.mark.parametrize("path", _fixture_paths(), ids=lambda p: p.stem)
def test_fixture_produces_its_declared_violations(path: Path) -> None:
    case = _load(path)
    report = _run(case)
    expected = set(case["expect_violation_codes"])

    missing = expected - report.codes
    assert not missing, f"{path.stem}: expected {sorted(missing)} but got {sorted(report.codes)}"


def test_clean_baseline_produces_nothing() -> None:
    """A well-formed graph must validate silently, or the suite proves nothing."""
    report = _run(_load(FIXTURE_DIR / "z_clean_baseline.json"))
    assert report.ok, f"clean baseline produced violations:\n{report}"


@pytest.mark.parametrize("path", _fixture_paths(), ids=lambda p: p.stem)
def test_fixture_objects_are_structurally_valid(path: Path) -> None:
    """Fixtures must be schema-valid, so a semantic test never passes on a typo.

    The MEDIDO-without-source case is the one exception: it is deliberately
    missing provenance, which the schema permits and the validators reject. That
    split is the point — shape and meaning are checked in different places.
    """
    case = _load(path)
    for key in ("sources", "evidence", "claims", "decisions", "projections", "packs"):
        for obj in case.get(key, []) or []:
            errors = structural_errors(obj)
            assert not errors, f"{path.stem}/{key}: {errors}"


@pytest.mark.parametrize("path", _fixture_paths(), ids=lambda p: p.stem)
def test_confidentiality_failures_are_critical(path: Path) -> None:
    """A leak must not be reported at the same level as a missing field."""
    report = _run(_load(path))
    for violation in report.violations:
        if violation.code in CRITICAL_CODES:
            assert violation.severity == CRITICAL, (
                f"{path.stem}: {violation.code} must be CRITICAL, got {violation.severity}"
            )


def test_every_mandatory_case_has_a_fixture() -> None:
    """All ten required scenarios exist, plus the controls."""
    stems = {p.stem for p in _fixture_paths()}
    required_prefixes = ["a_", "b_", "c_", "d_", "e_", "f_", "g_", "h_", "i_", "j_"]
    for prefix in required_prefixes:
        assert any(s.startswith(prefix) for s in stems), f"missing fixture for case {prefix!r}"
    assert "z_clean_baseline" in stems
    assert "y_pii_is_not_secret" in stems


def test_validators_never_mutate_their_input() -> None:
    """Nothing is repaired in place. A silent fix would destroy the evidence."""
    case = _load(FIXTURE_DIR / "f_medido_without_source.json")
    before = json.dumps(case, sort_keys=True)
    _run(case)
    assert json.dumps(case, sort_keys=True) == before
