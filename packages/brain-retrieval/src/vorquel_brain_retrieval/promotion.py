"""Epistemic promotion detection, against what is actually stored.

In Brain-V1-A ``check_epistemic_promotion(before, after)`` was a pure function
with nothing to compare against: the caller supplied both sides, so nothing
stopped it from supplying a convenient ``before``. Here ``before`` is read from
the store and only ``after`` comes from the proposal. That is the whole change,
and it is what turns a dormant rule into an enforced one.

Three properties, all deliberate:

* **Nothing is corrected.** A forbidden promotion produces a finding. It does
  not rewrite the proposal to the allowed status, because a validator that
  quietly repairs data destroys the evidence that the data was wrong.
* **Nothing is mutated.** This module has no write path to the store. A finding
  is returned to a caller who decides; canonical state is untouched either way.
* **A new object is not a promotion.** Proposing something that does not exist
  yet is a creation, and creations are reviewed as candidates. Treating them as
  promotions from nothing would flag every first write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vorquel_brain_contract import (
    EPISTEMIC_STATUSES_REQUIRING_PROVENANCE,
    check_epistemic_promotion,
    check_epistemic_provenance,
)

from .store import ID_FIELDS, BrainStore

#: Object types whose epistemic status can be promoted at all.
PROMOTABLE = ("Claim", "Evidence")


@dataclass(frozen=True)
class PromotionFinding:
    """One proposed change, judged against the stored object."""

    object_type: str
    object_id: str
    before: str | None
    after: str | None
    verdict: str
    violations: tuple[str, ...]
    note: str = ""

    #: The stored status and the proposal agree. Nothing to decide.
    UNCHANGED = "UNCHANGED"
    #: A change the contract permits.
    ALLOWED = "ALLOWED"
    #: A change the contract forbids without new evidence and a review gate.
    FORBIDDEN = "FORBIDDEN"
    #: Nothing is stored under this id, so this is a creation, not a promotion.
    NEW_OBJECT = "NEW_OBJECT"

    @property
    def is_violation(self) -> bool:
        return self.verdict == self.FORBIDDEN

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "before": self.before,
            "after": self.after,
            "verdict": self.verdict,
            "violations": list(self.violations),
            "note": self.note,
        }

    def as_candidate_conflict(self) -> dict[str, Any]:
        """The finding as something a human review queue can pick up.

        Deliberately a plain dict and deliberately not written anywhere.
        ``record_candidate`` belongs to Brain-V1-C, and manufacturing a write
        path here would be the canonical-mutation boundary crossed by a
        convenience.
        """
        return {
            "conflict_type": "FORBIDDEN_EPISTEMIC_PROMOTION",
            "object_type": self.object_type,
            "object_id": self.object_id,
            "stored_epistemic_status": self.before,
            "proposed_epistemic_status": self.after,
            "violations": list(self.violations),
            "resolution": "requires new evidence and human review; not applied",
        }


def detect_promotion(
    store: BrainStore, proposal: dict[str, Any], *, object_type: str | None = None
) -> PromotionFinding:
    """Judge one proposed object against what is stored under its id."""
    declared = object_type or str(proposal.get("object_type", ""))
    if declared not in PROMOTABLE:
        raise ValueError(
            f"{declared!r} has no promotable epistemic status; expected one of "
            f"{', '.join(PROMOTABLE)}"
        )

    object_id = str(proposal.get(ID_FIELDS[declared], ""))
    after = proposal.get("epistemic_status")
    stored = store.by_id(declared, object_id) if object_id else None

    if stored is None:
        return PromotionFinding(
            object_type=declared,
            object_id=object_id,
            before=None,
            after=after,
            verdict=PromotionFinding.NEW_OBJECT,
            violations=(),
            note="nothing is stored under this id; this is a creation, reviewed as a candidate",
        )

    before = stored.get("epistemic_status")
    violations = [str(v) for v in check_epistemic_promotion(before, after)]

    # A status that asserts a fact owes provenance, and it owes it at the moment
    # it is claimed. Promoting *into* MEDIDO or OBSERVADO without a source is
    # the same failure as recording one that way in the first place.
    if after in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE and after != before:
        violations.extend(str(v) for v in check_epistemic_provenance(proposal))

    if violations:
        verdict = PromotionFinding.FORBIDDEN
    elif before == after:
        verdict = PromotionFinding.UNCHANGED
    else:
        verdict = PromotionFinding.ALLOWED

    return PromotionFinding(
        object_type=declared,
        object_id=object_id,
        before=str(before) if before is not None else None,
        after=str(after) if after is not None else None,
        verdict=verdict,
        violations=tuple(violations),
    )


def detect_promotions(
    store: BrainStore, proposals: list[dict[str, Any]]
) -> tuple[PromotionFinding, ...]:
    """Judge many proposals. Order follows the input, which is the caller's."""
    return tuple(detect_promotion(store, proposal) for proposal in proposals)


def violations_only(findings: tuple[PromotionFinding, ...]) -> tuple[PromotionFinding, ...]:
    return tuple(f for f in findings if f.is_violation)
