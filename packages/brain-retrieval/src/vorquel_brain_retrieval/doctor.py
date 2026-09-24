"""Brain-V1-B doctor checks. Reports drift; never repairs it.

Scope note, since the project already has a doctor. ``vorquel-brain-doctor`` in
``packages/n8n-brain-retrieval`` diagnoses a live n8n deployment and its
database, and it stays the doctor for that. The checks here are the ones it
structurally cannot run: they are about Brain *objects* and the contract, and
they work over a :class:`~.store.BrainStore` rather than a connection. Putting
them in the n8n package would have coupled the universal Brain to the n8n one,
which is the dependency direction Brain-V1-B is arranged to avoid.

Everything here **reports**. Nothing here fixes. A doctor that silently repairs
drift removes the evidence that drift happened, and the recurrence is then
invisible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from vorquel_brain_contract import EPISTEMIC_STATUSES_REQUIRING_PROVENANCE

from .parity import ParityError, parity_report
from .policy import (
    DEFAULT_STALENESS_HORIZON,
    is_secret,
    latest_timestamp,
    parse_timestamp,
)
from .scope import Scope, ScopeError, ScopeGuard
from .store import ID_FIELDS, BrainStore

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    message: str
    details: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "status": self.status,
            "message": self.message,
            "details": list(self.details),
        }


@dataclass
class DoctorReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def overall(self) -> str:
        statuses = {f.status for f in self.findings}
        if FAIL in statuses:
            return FAIL
        return WARN if WARN in statuses else OK

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "findings": [f.as_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_enum_drift(repo_root: Any = None) -> Finding:
    """Python, schemas and storage still agree on the closed vocabularies."""
    try:
        report = parity_report(repo_root)
    except ParityError as exc:
        return Finding("enum_drift", WARN, f"parity could not be checked: {exc}")
    if report["status"] == "OK":
        return Finding(
            "enum_drift",
            OK,
            f"{len(report['checked_python_vs_schema'])} vocabularies agree with the schemas, "
            f"{len(report['checked_python_vs_storage'])} with storage",
        )
    return Finding(
        "enum_drift",
        FAIL,
        "closed vocabularies disagree between layers",
        tuple(
            f"{d['vocabulary']}: {d['left']} vs {d['right']}" for d in report["divergences"]
        ),
    )


def check_scope_storage_mismatch(repo_root: Any = None) -> Finding:
    """Every contract scope is one storage will accept.

    The gap DIV-3 recorded and 20260922_006 closed. Kept as a standing check
    rather than retired with the migration, because the next divergence between
    contract and storage will look exactly like the last one.
    """
    from vorquel_brain_contract import SCOPE_TYPES

    from .parity import storage_enum

    try:
        stored = storage_enum("scope_type", repo_root)
    except ParityError as exc:
        return Finding("scope_storage_mismatch", WARN, str(exc))

    missing = sorted(set(SCOPE_TYPES) - set(stored))
    if missing:
        return Finding(
            "scope_storage_mismatch",
            FAIL,
            "the contract defines scopes storage will reject",
            tuple(missing),
        )
    return Finding(
        "scope_storage_mismatch", OK, f"storage accepts all {len(SCOPE_TYPES)} contract scopes"
    )


def check_broken_provenance(store: BrainStore) -> Finding:
    """Asserting objects can be traced, and their pointers resolve."""
    broken: list[str] = []

    for object_type in ("Claim", "Evidence"):
        for obj in store.all_of(object_type):
            object_id = str(obj[ID_FIELDS[object_type]])
            pointers = [p for p in obj.get("provenance", []) if isinstance(p, dict)]
            source_ids = [str(s) for s in obj.get("source_ids", [])]
            if obj.get("source_id"):
                source_ids.append(str(obj["source_id"]))

            if obj.get("epistemic_status") in EPISTEMIC_STATUSES_REQUIRING_PROVENANCE and not (
                pointers or source_ids
            ):
                broken.append(
                    f"{object_id} is {obj['epistemic_status']} with no source at all"
                )

            for pointer in pointers:
                if store.by_id("Source", str(pointer.get("source_id"))) is None:
                    broken.append(f"{object_id} cites missing source {pointer.get('source_id')}")
                fragment_id = pointer.get("fragment_id")
                if fragment_id and store.by_id("SourceFragment", str(fragment_id)) is None:
                    broken.append(f"{object_id} cites missing fragment {fragment_id}")
            for source_id in source_ids:
                if store.by_id("Source", source_id) is None:
                    broken.append(f"{object_id} cites missing source {source_id}")

    if broken:
        return Finding(
            "broken_provenance", FAIL, f"{len(broken)} provenance problem(s)", tuple(sorted(broken))
        )
    return Finding("broken_provenance", OK, "every asserting object resolves to a real source")


def check_stale_state(
    store: BrainStore, horizon: timedelta = DEFAULT_STALENESS_HORIZON
) -> Finding:
    """Stored projections are not older than what they claim to summarise."""
    stale: list[str] = []
    newest = latest_timestamp(
        [obj for object_type in ("Claim", "Evidence", "Event") for obj in store.all_of(object_type)]
    )
    if newest is None:
        return Finding("stale_state", OK, "nothing dated is stored, so nothing can be stale")

    for projection in store.all_of("StateProjection"):
        as_of = parse_timestamp(projection.get("as_of"))
        projection_id = str(projection["state_projection_id"])
        if as_of is None:
            stale.append(f"{projection_id} has no readable as_of")
        elif newest - as_of > horizon:
            stale.append(
                f"{projection_id} is {(newest - as_of).days} days behind the newest record "
                f"but reports {projection.get('freshness_status')}"
            )
    if stale:
        return Finding(
            "stale_state", WARN, f"{len(stale)} stale projection(s)", tuple(sorted(stale))
        )
    return Finding("stale_state", OK, "stored projections are current")


def check_cross_scope_leak(store: BrainStore) -> Finding:
    """No object points across a scope boundary it should not cross.

    The case that matters: a claim about a client entity filed under a different
    client, or evidence attached to an entity in another scope. Either makes a
    correctly scoped query return the wrong thing.
    """
    leaks: list[str] = []

    for object_type in ("Claim", "Evidence"):
        for obj in store.all_of(object_type):
            object_id = str(obj[ID_FIELDS[object_type]])
            raw = obj.get("scope") or obj.get("entity_scope")
            try:
                own = Scope.from_mapping(raw)
            except ScopeError:
                leaks.append(f"{object_id} has no readable scope")
                continue

            for key in ("subject_entity_id", "object_entity_id"):
                entity_id = obj.get(key)
                if not entity_id:
                    continue
                entity = store.by_id("Entity", str(entity_id))
                if entity is None:
                    leaks.append(f"{object_id} references missing entity {entity_id}")
                    continue
                entity_scope = Scope.from_mapping(entity["scope"])
                # An object may sit in the entity's own scope or in the global
                # one. Anything else means the two disagree about ownership.
                if not ScopeGuard(requested=entity_scope).admits_scope(own):
                    leaks.append(
                        f"{object_id} is in {own} but {key}={entity_id} is in {entity_scope}"
                    )

    if leaks:
        return Finding(
            "cross_scope_leak", FAIL, f"{len(leaks)} cross-scope reference(s)", tuple(sorted(leaks))
        )
    return Finding("cross_scope_leak", OK, "no object crosses a scope boundary")


def check_secret_pack_risk(store: BrainStore) -> Finding:
    """SECRET objects are reachable only as SECRET.

    The risk is not a SECRET object existing — it is a SECRET object being
    referenced by a non-SECRET one, which is how it ends up quoted into a pack
    that never names it.
    """
    risks: list[str] = []
    secret_ids = {
        str(obj[ID_FIELDS[object_type]])
        for object_type in ("Claim", "Evidence", "Source", "Entity", "Decision")
        for obj in store.all_of(object_type)
        if is_secret(obj)
    }
    if not secret_ids:
        return Finding("secret_pack_risk", OK, "no SECRET objects are stored")

    for object_type in ("Claim", "Evidence"):
        for obj in store.all_of(object_type):
            if is_secret(obj):
                continue
            object_id = str(obj[ID_FIELDS[object_type]])
            referenced = {str(s) for s in obj.get("source_ids", [])}
            if obj.get("source_id"):
                referenced.add(str(obj["source_id"]))
            for entry in obj.get("provenance", []):
                if isinstance(entry, dict) and entry.get("source_id"):
                    referenced.add(str(entry["source_id"]))
            for subject in ("subject_entity_id", "object_entity_id"):
                if obj.get(subject):
                    referenced.add(str(obj[subject]))
            for leaked in sorted(referenced & secret_ids):
                risks.append(f"{object_id} is not SECRET but references SECRET {leaked}")

    if risks:
        return Finding(
            "secret_pack_risk", FAIL, f"{len(risks)} SECRET reference(s) from non-SECRET objects",
            tuple(sorted(risks)),
        )
    return Finding("secret_pack_risk", OK, f"{len(secret_ids)} SECRET object(s), none reachable")


def check_invalid_promotion(store: BrainStore) -> Finding:
    """Stored objects do not already hold a status their history forbids.

    Read-only and backward-looking: it checks a superseding claim against the
    claim it replaced. A promotion that happened before this check existed is
    still a promotion, and it should be visible rather than grandfathered.
    """
    from vorquel_brain_contract import check_epistemic_promotion

    problems: list[str] = []
    for claim in store.all_of("Claim"):
        predecessor_id = claim.get("supersedes")
        if not predecessor_id:
            continue
        predecessor = store.by_id("Claim", str(predecessor_id))
        if predecessor is None:
            problems.append(f"{claim['claim_id']} supersedes missing claim {predecessor_id}")
            continue
        violations = check_epistemic_promotion(
            predecessor.get("epistemic_status"), claim.get("epistemic_status")
        )
        for violation in violations:
            problems.append(f"{claim['claim_id']}: {violation}")

    if problems:
        return Finding(
            "invalid_promotion", FAIL, f"{len(problems)} forbidden promotion(s) already stored",
            tuple(sorted(problems)),
        )
    return Finding("invalid_promotion", OK, "no stored claim was promoted past its predecessor")


def run_doctor(
    store: BrainStore,
    *,
    repo_root: Any = None,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
) -> DoctorReport:
    """Every Brain-V1-B check, in a stable order."""
    return DoctorReport(
        findings=[
            check_enum_drift(repo_root),
            check_scope_storage_mismatch(repo_root),
            check_broken_provenance(store),
            check_stale_state(store, horizon),
            check_cross_scope_leak(store),
            check_secret_pack_risk(store),
            check_invalid_promotion(store),
        ]
    )
