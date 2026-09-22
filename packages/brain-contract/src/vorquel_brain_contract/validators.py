"""The semantic rules of the contract — everything JSON Schema cannot say.

A schema can require that ``epistemic_status`` is one of nine strings. It cannot
require that ``MEDIDO`` comes with provenance, that a superseded decision stops
being presented as current, or that a gap in the record is never serialised as a
negative fact. Those are the rules that actually protect the Brain, so they live
here as pure functions over plain dicts.

Two properties hold throughout, and both are deliberate:

**Nothing is corrected silently.** Every function returns
:class:`Violation` objects. None of them edits its input, fills a default or
drops an offending field. A validator that quietly repairs data destroys the
evidence that the data was wrong, which is the failure mode this whole contract
exists to prevent.

**Absence is not success.** A missing field that a rule depends on is a
violation, never a pass. This mirrors the SAFE TEST gate already in this
repository: evidence has to be positively present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import (
    EPISTEMIC_STATUSES_REQUIRING_PROVENANCE,
    FORBIDDEN_EPISTEMIC_PROMOTIONS,
    FORBIDDEN_FIELD_NAMES,
    NO_EVIDENCE_FOUND,
    SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK,
)

ERROR = "ERROR"
CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Violation:
    """One broken rule, named so a caller learns which one rather than that 'it failed'."""

    code: str
    message: str
    path: str = ""
    severity: str = ERROR

    def __str__(self) -> str:
        where = f" at {self.path}" if self.path else ""
        return f"[{self.severity}] {self.code}{where}: {self.message}"


def _scope_of(obj: dict[str, Any]) -> tuple[str, str] | None:
    """An object's scope, whichever of the two field names it uses."""
    scope = obj.get("scope") or obj.get("entity_scope")
    if not isinstance(scope, dict):
        return None
    scope_type, scope_id = scope.get("scope_type"), scope.get("scope_id")
    if not scope_type or not scope_id:
        return None
    return (scope_type, scope_id)


def _has_provenance(obj: dict[str, Any]) -> bool:
    """True when the object points at something a reader could go and check.

    A ``source_id`` alone counts. An empty list does not, and neither does a
    provenance entry with no ``source_id`` — a pointer to nothing is not a
    pointer.
    """
    provenance = obj.get("provenance")
    if isinstance(provenance, dict) and provenance.get("source_id"):
        return True
    if isinstance(provenance, list) and any(
        isinstance(p, dict) and p.get("source_id") for p in provenance
    ):
        return True
    if obj.get("source_id"):
        return True
    source_ids = obj.get("source_ids")
    return bool(isinstance(source_ids, list) and source_ids)


# ---------------------------------------------------------------------------
# 1 & 2 — MEDIDO and OBSERVADO require provenance
# ---------------------------------------------------------------------------


def check_epistemic_provenance(obj: dict[str, Any]) -> list[Violation]:
    """``OBSERVADO`` and ``MEDIDO`` assert something about the world, so they owe a source.

    The other seven statuses may stand on reasoning, and say so by their own
    name. These two claim contact with reality, and a claim of contact with
    reality that cannot be traced is the most expensive kind of wrong thing to
    keep.
    """
    status = obj.get("epistemic_status")
    if status not in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE:
        return []
    if _has_provenance(obj):
        return []
    identifier = obj.get("claim_id") or obj.get("evidence_id") or "<unidentified>"
    return [
        Violation(
            code="EPISTEMIC_PROVENANCE_REQUIRED",
            message=(
                f"epistemic_status={status} asserts an observation of the world but the "
                "object carries no source_id, source_ids or provenance entry"
            ),
            path=identifier,
        )
    ]


# ---------------------------------------------------------------------------
# 3 — SECRET may never enter a ContextPack
# ---------------------------------------------------------------------------


def check_context_pack_excludes_secret(
    pack: dict[str, Any], objects_by_id: dict[str, dict[str, Any]] | None = None
) -> list[Violation]:
    """No ``SECRET`` object reaches a pack, and the pack itself is never ``SECRET``.

    Checked on the pack's own level *and* on every object it references, because
    a pack that is merely labelled ``INTERNAL`` while carrying a secret has
    leaked it just as thoroughly.
    """
    violations: list[Violation] = []
    pack_id = pack.get("context_pack_id", "<unidentified>")

    if pack.get("sensitivity_level") == SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK:
        violations.append(
            Violation(
                code="SECRET_IN_CONTEXT_PACK",
                message="a ContextPack may never carry sensitivity_level=SECRET",
                path=pack_id,
                severity=CRITICAL,
            )
        )

    for object_id in _referenced_ids(pack):
        referenced = (objects_by_id or {}).get(object_id)
        if not referenced:
            continue
        level = referenced.get("sensitivity_level") or (
            referenced.get("sensitivity") or {}
        ).get("sensitivity_level")
        if level == SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK:
            violations.append(
                Violation(
                    code="SECRET_IN_CONTEXT_PACK",
                    message=(
                        f"referenced object {object_id!r} is SECRET and may not appear "
                        "in a ContextPack at any budget or in any mode"
                    ),
                    path=f"{pack_id} -> {object_id}",
                    severity=CRITICAL,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# 4 & 5 — PII is orthogonal to the confidentiality tier
# ---------------------------------------------------------------------------


def check_pii_orthogonality(obj: dict[str, Any]) -> list[Violation]:
    """Carrying ``PII`` neither promotes an object to ``SECRET`` nor weakens its tier.

    The two axes are independent by decision (DIV-2). This catches the two ways
    code tends to conflate them: auto-escalating anything with personal data to
    ``SECRET``, which makes it unusable and unauditable, and treating
    ``CLIENT_CONFIDENTIAL`` as conditional on whether ``PII`` happens to be
    present, which makes a client's confidentiality depend on an unrelated fact.
    """
    sensitivity = obj.get("sensitivity") or {}
    level = obj.get("sensitivity_level") or sensitivity.get("sensitivity_level")
    data_classes = obj.get("data_classes")
    if data_classes is None:
        data_classes = sensitivity.get("data_classes", [])
    if "PII" not in (data_classes or []):
        return []

    identifier = _any_id(obj)
    if level == "SECRET" and not obj.get("secret_justification"):
        return [
            Violation(
                code="PII_AUTO_PROMOTED_TO_SECRET",
                message=(
                    "object carries PII and is marked SECRET with no independent "
                    "justification; PII is a data class and never by itself a reason "
                    "to raise the confidentiality tier"
                ),
                path=identifier,
            )
        ]
    return []


def check_client_confidential_unaffected_by_pii(obj: dict[str, Any]) -> list[Violation]:
    """``CLIENT_CONFIDENTIAL`` holds whether or not ``PII`` is present.

    Stated as an explicit check so the property is asserted rather than assumed:
    the tier must survive both states of the data-class axis.
    """
    sensitivity = obj.get("sensitivity") or {}
    level = obj.get("sensitivity_level") or sensitivity.get("sensitivity_level")
    if level != "CLIENT_CONFIDENTIAL":
        return []
    data_classes = obj.get("data_classes")
    if data_classes is None:
        data_classes = sensitivity.get("data_classes", [])
    if not isinstance(data_classes, list):
        return [
            Violation(
                code="DATA_CLASSES_MALFORMED",
                message="data_classes must be a list; a CLIENT_CONFIDENTIAL object "
                "cannot have its tier evaluated against a malformed data-class axis",
                path=_any_id(obj),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# 6 — a superseded decision is never the current one
# ---------------------------------------------------------------------------


def check_decision_supersession(decisions: list[dict[str, Any]]) -> list[Violation]:
    """An old decision must not still be presented as ``ACTIVE``.

    Supersession is a replacement, not a deletion: the earlier decision stays in
    the record with status ``SUPERSEDED`` and a ``superseded_by`` pointer. What
    must never happen is two decisions both claiming to be in force, because a
    consumer then has no way to pick and will pick the first one it sees.
    """
    violations: list[Violation] = []
    by_id = {d.get("decision_id"): d for d in decisions if d.get("decision_id")}

    for decision in decisions:
        decision_id = decision.get("decision_id", "<unidentified>")
        status = decision.get("status")
        superseded_by = decision.get("superseded_by")

        if superseded_by and status == "ACTIVE":
            violations.append(
                Violation(
                    code="SUPERSEDED_DECISION_STILL_ACTIVE",
                    message=(
                        f"decision is superseded by {superseded_by!r} but still carries "
                        "status=ACTIVE; a replaced decision must be SUPERSEDED"
                    ),
                    path=decision_id,
                )
            )

        successor_id = decision.get("supersedes")
        if successor_id:
            predecessor = by_id.get(successor_id)
            if predecessor is None:
                violations.append(
                    Violation(
                        code="SUPERSEDES_BROKEN_REFERENCE",
                        message=f"supersedes {successor_id!r}, which is not present",
                        path=decision_id,
                    )
                )
            elif predecessor.get("status") == "ACTIVE":
                violations.append(
                    Violation(
                        code="SUPERSEDED_DECISION_STILL_ACTIVE",
                        message=(
                            f"this decision supersedes {successor_id!r}, but that one is "
                            "still ACTIVE; both would read as current"
                        ),
                        path=decision_id,
                    )
                )
    return violations


def check_active_decisions_in_projection(
    projection: dict[str, Any], decisions_by_id: dict[str, dict[str, Any]]
) -> list[Violation]:
    """A StateProjection may not list a superseded or revoked decision as active."""
    violations: list[Violation] = []
    for decision_id in projection.get("active_decision_ids", []) or []:
        decision = decisions_by_id.get(decision_id)
        if decision is None:
            violations.append(
                Violation(
                    code="PROJECTION_BROKEN_DECISION_REFERENCE",
                    message=f"active_decision_ids names {decision_id!r}, which is not present",
                    path=projection.get("state_projection_id", "<unidentified>"),
                )
            )
        elif decision.get("status") != "ACTIVE":
            violations.append(
                Violation(
                    code="SUPERSEDED_DECISION_PRESENTED_AS_ACTIVE",
                    message=(
                        f"decision {decision_id!r} has status {decision.get('status')!r} "
                        "but is listed in active_decision_ids"
                    ),
                    path=projection.get("state_projection_id", "<unidentified>"),
                )
            )
    return violations


# ---------------------------------------------------------------------------
# 7 — epistemic promotion
# ---------------------------------------------------------------------------


def check_epistemic_promotion(before: str | None, after: str | None) -> list[Violation]:
    """Reject a status change that claims more certainty than the evidence gained.

    Inference does not become measurement because someone restated it, and a
    hypothesis does not become an observation because it stopped being
    questioned. A real promotion needs new evidence and a review, which is a
    different operation from editing a field.
    """
    if not before or not after or before == after:
        return []
    forbidden = FORBIDDEN_EPISTEMIC_PROMOTIONS.get(before, ())
    if after in forbidden:
        return [
            Violation(
                code="INVALID_EPISTEMIC_PROMOTION",
                message=(
                    f"{before} -> {after} is not a permitted promotion; it asserts "
                    "stronger knowledge without new evidence"
                ),
            )
        ]
    return []


def check_candidate_is_not_canonical(candidate: dict[str, Any]) -> list[Violation]:
    """A pending candidate may not claim an observational status as if settled."""
    if candidate.get("status") != "PENDING":
        return []
    proposed = candidate.get("proposed_epistemic_status")
    if proposed in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE and not _has_provenance(candidate):
        return [
            Violation(
                code="CANDIDATE_PROPOSES_UNSOURCED_OBSERVATION",
                message=(
                    f"candidate proposes epistemic_status={proposed} with no provenance; "
                    "review cannot grant what was never evidenced"
                ),
                path=candidate.get("candidate_id", "<unidentified>"),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# 8 — scope isolation
# ---------------------------------------------------------------------------


def check_scope_isolation(
    pack: dict[str, Any], objects_by_id: dict[str, dict[str, Any]]
) -> list[Violation]:
    """Nothing from another scope may be pulled into a scoped pack.

    Two clients sharing a consultancy is exactly the situation where a retrieval
    bug becomes a confidentiality incident, so a reference that crosses from one
    ``CLIENT`` scope into another is raised at ``CRITICAL`` rather than as an
    ordinary error.

    ``GLOBAL_VORQUEL`` is the one scope that legitimately applies everywhere —
    methodology and internal standards are meant to reach every engagement — so
    it is allowed. Any other mismatch is a leak.
    """
    violations: list[Violation] = []
    pack_scope = _scope_of(pack)
    pack_id = pack.get("context_pack_id", "<unidentified>")
    if pack_scope is None:
        return [
            Violation(
                code="PACK_SCOPE_MISSING",
                message="ContextPack has no resolvable scope, so isolation cannot be checked",
                path=pack_id,
                severity=CRITICAL,
            )
        ]

    pack_type, pack_id_value = pack_scope

    for object_id in _referenced_ids(pack):
        referenced = objects_by_id.get(object_id)
        if referenced is None:
            continue
        other = _scope_of(referenced)
        if other is None or other == pack_scope:
            continue
        other_type, other_id = other
        if other_type == "GLOBAL_VORQUEL":
            continue

        cross_client = pack_type == "CLIENT" and other_type == "CLIENT"
        violations.append(
            Violation(
                code="CROSS_CLIENT_REFERENCE" if cross_client else "CROSS_SCOPE_REFERENCE",
                message=(
                    f"object {object_id!r} is scoped to {other_type}:{other_id} but is "
                    f"referenced by a pack scoped to {pack_type}:{pack_id_value}"
                ),
                path=f"{pack_id} -> {object_id}",
                severity=CRITICAL if cross_client else ERROR,
            )
        )
    return violations


def check_evidence_supports_claim_scope(
    claim: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
) -> list[Violation]:
    """Generic material may not become a specific finding about one entity.

    This is the leak that looks harmless. A general sales deck shared in a
    conversation about one client is evidence about the deck, not about that
    client; public research about a market is evidence about the market, not a
    validated operational pain inside a particular company. Both become false
    institutional memory the moment they are attached to an entity-specific
    claim at an observational status.

    Two conditions have to hold for supporting evidence:

    - it must not belong to a *different* entity's scope, and
    - ``PUBLIC_RESEARCH`` must not underwrite ``OBSERVADO`` or ``MEDIDO``,
      because nobody observed or measured anything inside the company.
    """
    violations: list[Violation] = []
    claim_id = claim.get("claim_id", "<unidentified>")
    claim_scope = _scope_of(claim)
    status = claim.get("epistemic_status")

    for evidence_id in claim.get("supporting_evidence_ids", []) or []:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            violations.append(
                Violation(
                    code="CLAIM_BROKEN_EVIDENCE_REFERENCE",
                    message=f"supporting_evidence_ids names {evidence_id!r}, which is not present",
                    path=claim_id,
                )
            )
            continue

        evidence_scope = _scope_of(evidence)
        if (
            claim_scope
            and evidence_scope
            and evidence_scope != claim_scope
            and evidence_scope[0] != "GLOBAL_VORQUEL"
        ):
            cross_client = claim_scope[0] == "CLIENT" and evidence_scope[0] == "CLIENT"
            violations.append(
                Violation(
                    code="CROSS_CLIENT_REFERENCE" if cross_client else "CROSS_SCOPE_REFERENCE",
                    message=(
                        f"evidence {evidence_id!r} is scoped to "
                        f"{evidence_scope[0]}:{evidence_scope[1]} but supports a claim scoped "
                        f"to {claim_scope[0]}:{claim_scope[1]}"
                    ),
                    path=claim_id,
                    severity=CRITICAL if cross_client else ERROR,
                )
            )

        if (
            evidence.get("evidence_type") == "PUBLIC_RESEARCH"
            and status in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE
        ):
            violations.append(
                Violation(
                    code="PUBLIC_RESEARCH_CANNOT_GROUND_OBSERVATION",
                    message=(
                        f"evidence {evidence_id!r} is PUBLIC_RESEARCH and cannot support a "
                        f"claim at epistemic_status={status}; nothing was observed or "
                        "measured inside the entity"
                    ),
                    path=claim_id,
                )
            )

        if (
            evidence_scope
            and evidence_scope[0] == "GLOBAL_VORQUEL"
            and claim_scope
            and claim_scope[0] != "GLOBAL_VORQUEL"
            and status in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE
            and not evidence.get("subject_entity_id")
        ):
            violations.append(
                Violation(
                    code="GENERIC_EVIDENCE_CANNOT_GROUND_ENTITY_OBSERVATION",
                    message=(
                        f"evidence {evidence_id!r} is transversal (GLOBAL_VORQUEL, no "
                        f"subject_entity_id) and cannot ground {status} about "
                        f"{claim_scope[0]}:{claim_scope[1]}"
                    ),
                    path=claim_id,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# 9 — NO_EVIDENCE_FOUND is not FALSE
# ---------------------------------------------------------------------------


def check_no_evidence_not_false(claim: dict[str, Any]) -> list[Violation]:
    """A gap in the record must never be serialised as a negative fact.

    ``NO_EVIDENCE_FOUND`` and ``false`` are different answers. The first says
    nobody looked or nobody found; the second says the world is a particular
    way. Collapsing them is how "we have not checked whether they use a CRM"
    becomes "they do not use a CRM", and nothing downstream can tell the
    difference afterwards.
    """
    violations: list[Violation] = []
    claim_id = claim.get("claim_id", "<unidentified>")
    status = claim.get("epistemic_status")
    has_value = "object_value" in claim
    value = claim.get("object_value")

    if value == NO_EVIDENCE_FOUND and status != "DESCONHECIDO":
        violations.append(
            Violation(
                code="NO_EVIDENCE_FOUND_MISLABELLED",
                message=(
                    f"object_value is {NO_EVIDENCE_FOUND} but epistemic_status is "
                    f"{status!r}; an absence of evidence is DESCONHECIDO"
                ),
                path=claim_id,
            )
        )

    if status == "DESCONHECIDO" and has_value and value is False:
        violations.append(
            Violation(
                code="NO_EVIDENCE_SERIALIZED_AS_FALSE",
                message=(
                    "epistemic_status=DESCONHECIDO with object_value=false turns an "
                    f"absence of evidence into a negative fact; use {NO_EVIDENCE_FOUND}"
                ),
                path=claim_id,
                severity=CRITICAL,
            )
        )
    return violations


def check_gaps_are_not_findings(pack: dict[str, Any]) -> list[Violation]:
    """A pack's ``gaps`` must stay strings, never boolean answers."""
    violations: list[Violation] = []
    for index, gap in enumerate(pack.get("gaps", []) or []):
        if isinstance(gap, bool):
            violations.append(
                Violation(
                    code="GAP_SERIALIZED_AS_BOOLEAN",
                    message="a gap is a description of what is missing, not a truth value",
                    path=f"{pack.get('context_pack_id', '<unidentified>')}/gaps/{index}",
                    severity=CRITICAL,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# 10 — a pack carries enough provenance for what it includes
# ---------------------------------------------------------------------------


def check_context_pack_provenance(
    pack: dict[str, Any], objects_by_id: dict[str, dict[str, Any]] | None = None
) -> list[Violation]:
    """Every asserting object in a pack must be traceable from the pack itself.

    A pack is what an AI actually reads, so provenance that exists only back in
    the store is provenance the reader does not have. Claims and evidence assert
    things and therefore need an entry; decisions, hypotheses and unknowns
    describe the Brain's own posture and do not.

    This is also the contract's token-budget floor: trimming may shorten
    content, but ``provenance_summary`` is non-droppable, because a pack that
    fits the budget by discarding traceability has optimised away the only thing
    that made it trustworthy.
    """
    violations: list[Violation] = []
    pack_id = pack.get("context_pack_id", "<unidentified>")
    summarised = {
        entry.get("object_id")
        for entry in pack.get("provenance_summary", []) or []
        if isinstance(entry, dict)
    }

    asserting_ids = list(pack.get("evidence_ids", []) or []) + list(
        pack.get("claim_ids", []) or []
    )
    for object_id in asserting_ids:
        if object_id not in summarised:
            violations.append(
                Violation(
                    code="CONTEXT_PACK_MISSING_PROVENANCE",
                    message=(
                        f"{object_id!r} is included in the pack but has no entry in "
                        "provenance_summary; it cannot be traced by the reader"
                    ),
                    path=pack_id,
                )
            )

    for entry in pack.get("provenance_summary", []) or []:
        if not isinstance(entry, dict):
            continue
        provenance = entry.get("provenance") or []
        if not any(isinstance(p, dict) and p.get("source_id") for p in provenance):
            violations.append(
                Violation(
                    code="CONTEXT_PACK_EMPTY_PROVENANCE_ENTRY",
                    message=(
                        f"provenance_summary entry for {entry.get('object_id')!r} carries no "
                        "source_id; an empty pointer is not provenance"
                    ),
                    path=pack_id,
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Security — no object may carry the means to act
# ---------------------------------------------------------------------------


def check_no_forbidden_fields(obj: Any, path: str = "<root>") -> list[Violation]:
    """Walk an object and reject any field that would carry a secret or an executable.

    A Brain object references an artifact; it never carries a credential, a
    connection string or a command. Walking the whole structure matters because
    a token nested three levels inside ``metadata`` is still a token.
    """
    violations: list[Violation] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}/{key}"
            if key.lower() in FORBIDDEN_FIELD_NAMES:
                violations.append(
                    Violation(
                        code="FORBIDDEN_FIELD",
                        message=(
                            f"field {key!r} may not appear in a Brain object: the contract "
                            "references sources and artifacts, never the means to act"
                        ),
                        path=here,
                        severity=CRITICAL,
                    )
                )
            violations.extend(check_no_forbidden_fields(value, here))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            violations.extend(check_no_forbidden_fields(item, f"{path}/{index}"))
    return violations


# ---------------------------------------------------------------------------
# Helpers and the aggregate entry point
# ---------------------------------------------------------------------------


def _any_id(obj: dict[str, Any]) -> str:
    for key in (
        "claim_id",
        "evidence_id",
        "entity_id",
        "source_id",
        "fragment_id",
        "decision_id",
        "candidate_id",
        "event_id",
        "hypothesis_id",
        "unknown_id",
        "state_projection_id",
        "context_pack_id",
    ):
        if obj.get(key):
            return str(obj[key])
    return "<unidentified>"


def _referenced_ids(pack: dict[str, Any]) -> list[str]:
    """Every object id a pack points at, across all its reference lists."""
    keys = (
        "state_projection_ids",
        "decision_ids",
        "evidence_ids",
        "hypothesis_ids",
        "unknown_ids",
        "recent_event_ids",
        "claim_ids",
        "entity_ids",
    )
    ids: list[str] = []
    for key in keys:
        value = pack.get(key)
        if isinstance(value, list):
            ids.extend(str(item) for item in value)
    return ids


@dataclass
class ValidationReport:
    """The result of validating a whole fixture graph."""

    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def codes(self) -> set[str]:
        return {violation.code for violation in self.violations}

    def with_code(self, code: str) -> list[Violation]:
        return [violation for violation in self.violations if violation.code == code]

    def __str__(self) -> str:
        if self.ok:
            return "no violations"
        return "\n".join(str(violation) for violation in self.violations)


def validate_graph(
    *,
    claims: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    projections: list[dict[str, Any]] | None = None,
    packs: list[dict[str, Any]] | None = None,
    objects_by_id: dict[str, dict[str, Any]] | None = None,
) -> ValidationReport:
    """Run every semantic rule over a set of related objects.

    Nothing is mutated and nothing is repaired. The report names each broken
    rule so a caller can tell which one, rather than only that something failed.
    """
    claims = claims or []
    evidence = evidence or []
    decisions = decisions or []
    candidates = candidates or []
    projections = projections or []
    packs = packs or []

    index = dict(objects_by_id or {})
    evidence_by_id = {e["evidence_id"]: e for e in evidence if e.get("evidence_id")}
    decisions_by_id = {d["decision_id"]: d for d in decisions if d.get("decision_id")}
    for collection in (claims, evidence, decisions, candidates, projections):
        for obj in collection:
            index.setdefault(_any_id(obj), obj)

    violations: list[Violation] = []

    for claim in claims:
        violations.extend(check_epistemic_provenance(claim))
        violations.extend(check_no_evidence_not_false(claim))
        violations.extend(check_pii_orthogonality(claim))
        violations.extend(check_client_confidential_unaffected_by_pii(claim))
        violations.extend(check_evidence_supports_claim_scope(claim, evidence_by_id))
        violations.extend(check_no_forbidden_fields(claim, _any_id(claim)))

    for item in evidence:
        violations.extend(check_epistemic_provenance(item))
        violations.extend(check_pii_orthogonality(item))
        violations.extend(check_no_forbidden_fields(item, _any_id(item)))

    violations.extend(check_decision_supersession(decisions))

    for candidate in candidates:
        violations.extend(check_candidate_is_not_canonical(candidate))
        violations.extend(check_no_forbidden_fields(candidate, _any_id(candidate)))

    for projection in projections:
        violations.extend(check_active_decisions_in_projection(projection, decisions_by_id))

    for pack in packs:
        violations.extend(check_context_pack_excludes_secret(pack, index))
        violations.extend(check_scope_isolation(pack, index))
        violations.extend(check_context_pack_provenance(pack, index))
        violations.extend(check_gaps_are_not_findings(pack))
        violations.extend(check_no_forbidden_fields(pack, _any_id(pack)))

    return ValidationReport(violations=violations)
