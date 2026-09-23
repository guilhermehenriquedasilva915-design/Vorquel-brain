"""``get_entity``, ``get_state`` and ``get_delta``.

Three reads that answer three different questions, kept apart on purpose:

* ``get_entity`` — the canonical record. Exact, not trimmed, not mode-dependent.
* ``get_state`` — the derived picture. A read model, rebuildable, staleness-bearing.
* ``get_delta`` — what changed. Temporal, and honest about what it cannot cover.

None of them assembles a ContextPack and none of them is a source of truth for
the others. Routing canonical identity through the derived channel, or answering
"what is this entity" with a budget-trimmed pack, is the collapse DIV-1 refused.

Every timestamp used here comes from the objects themselves. Nothing calls
``now()``, which is what makes all three reproducible for a fixed store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from vorquel_brain_contract import CONTRACT_VERSION

from .errors import Absence
from .policy import (
    DEFAULT_STALENESS_HORIZON,
    carries_pii,
    data_classes_of,
    format_timestamp,
    freshness_for,
    is_secret,
    latest_timestamp,
    parse_timestamp,
    sensitivity_of,
)
from .scope import Scope, ScopeGuard
from .store import BrainStore

#: Hypothesis statuses that count as a live question.
OPEN_HYPOTHESIS_STATUSES = ("OPEN", "PARTIALLY_SUPPORTED", "CONFLICTING")
#: Unknown statuses that count as still open.
OPEN_UNKNOWN_STATUSES = ("OPEN", "PARTIALLY_RESOLVED")


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityRelation:
    """A relation, derived from a claim rather than stored as its own object.

    The V1 contract names ``RELATION`` as a candidate type but publishes no
    relation schema, and ``entity.schema.json`` is closed with no relations
    field. Rather than invent a thirteenth canonical object, a relation is read
    off a Claim that points from one entity to another. It therefore carries the
    claim's epistemic status, which is the honest answer: a relation is exactly
    as well-known as the claim asserting it.
    """

    predicate: str
    object_entity_id: str
    claim_id: str
    epistemic_status: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "object_entity_id": self.object_entity_id,
            "claim_id": self.claim_id,
            "epistemic_status": self.epistemic_status,
            "status": self.status,
        }


@dataclass(frozen=True)
class EntityView:
    """The canonical entity record plus its relations. A read model over one object."""

    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: tuple[str, ...]
    scope: Scope
    status: str
    sensitivity_level: str
    data_classes: tuple[str, ...]
    relations: tuple[EntityRelation, ...]
    created_at: str
    last_updated_at: str
    freshness_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "scope": self.scope.as_mapping(),
            "status": self.status,
            "sensitivity_level": self.sensitivity_level,
            "data_classes": list(self.data_classes),
            "relations": [r.as_dict() for r in self.relations],
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "freshness_status": self.freshness_status,
        }


def get_entity(
    store: BrainStore,
    entity_id: str,
    scope: Scope,
    *,
    include_global: bool = True,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
) -> EntityView | Absence:
    """The canonical record for one entity, or an explicit absence.

    An entity that does not exist, one outside the caller's scope and one marked
    ``SECRET`` all return the same ``NOT_FOUND``. Distinguishing them would tell
    a caller that an id it guessed is real, which is the leak the scope rule
    exists to prevent.
    """
    guard = ScopeGuard(requested=scope, include_global=include_global)
    entity = store.by_id("Entity", entity_id)

    if entity is None or not guard.admits(entity) or is_secret(entity):
        return Absence(
            Absence.NOT_FOUND,
            entity_id,
            f"no entity {entity_id!r} is visible from {guard}",
        )

    relations = tuple(
        EntityRelation(
            predicate=str(claim["predicate"]),
            object_entity_id=str(claim["object_entity_id"]),
            claim_id=str(claim["claim_id"]),
            epistemic_status=str(claim["epistemic_status"]),
            status=str(claim["status"]),
        )
        for claim in store.all_of("Claim")
        if claim.get("subject_entity_id") == entity_id
        and claim.get("object_entity_id")
        and guard.admits(claim)
        and not is_secret(claim)
        # A relation whose other end is invisible is not shown. Naming the
        # target id would disclose an entity the caller may not read.
        and _target_visible(store, guard, str(claim["object_entity_id"]))
    )

    as_of = latest_timestamp(store.all_of("Entity") + store.all_of("Claim"))
    return EntityView(
        entity_id=entity_id,
        entity_type=str(entity["entity_type"]),
        canonical_name=str(entity["canonical_name"]),
        aliases=tuple(str(a) for a in entity.get("aliases", [])),
        scope=Scope.from_mapping(entity["scope"]),
        status=str(entity["status"]),
        sensitivity_level=sensitivity_of(entity),
        data_classes=data_classes_of(entity),
        relations=tuple(sorted(relations, key=lambda r: (r.predicate, r.object_entity_id))),
        created_at=str(entity["created_at"]),
        last_updated_at=str(entity["last_updated_at"]),
        freshness_status=freshness_for(as_of, parse_timestamp(entity["last_updated_at"]), horizon),
    )


def _target_visible(store: BrainStore, guard: ScopeGuard, entity_id: str) -> bool:
    target = store.by_id("Entity", entity_id)
    return target is not None and guard.admits(target) and not is_secret(target)


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


def _in_scope(store: BrainStore, guard: ScopeGuard, object_type: str) -> list[dict[str, Any]]:
    """Everything of one type the guard admits, SECRET already removed."""
    return [
        obj for obj in store.all_of(object_type) if guard.admits(obj) and not is_secret(obj)
    ]


def _about_entity(objects: list[dict[str, Any]], entity_id: str | None) -> list[dict[str, Any]]:
    """Narrow to one entity, when one was asked for.

    Two things survive the narrowing, and both are deliberate.

    An object with no subject entity — a scope-level decision, a scope-level
    unknown — stays in. It applies to the entity by applying to everything
    around it, and dropping it would hide a constraint that is genuinely in
    force.

    A ``GLOBAL_VORQUEL`` object stays in whatever it is about. Global knowledge
    is Vorquel's own methodology and standing rules; it is global precisely
    because it applies everywhere, and filtering it out by subject would make
    the methodology unreachable from the packs that most need it.
    """
    if entity_id is None:
        return objects
    return [
        obj
        for obj in objects
        if _is_global(obj)
        or obj.get("subject_entity_id") in (None, entity_id)
        or obj.get("object_entity_id") == entity_id
    ]


def _is_global(obj: dict[str, Any]) -> bool:
    raw = obj.get("scope") or obj.get("entity_scope") or {}
    return isinstance(raw, dict) and raw.get("scope_type") == "GLOBAL_VORQUEL"


def _conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Contradictions left standing, never resolved here.

    Three kinds are reported, and a projection reports all of them rather than
    adjudicating: a claim that says it is in conflict, a claim carrying counter
    evidence, and two active claims asserting different values for the same
    subject and predicate.
    """
    found: list[dict[str, Any]] = []

    for claim in claims:
        if claim.get("status") == "DISPUTED" or claim.get("epistemic_status") == "CONFLITANTE":
            found.append(
                {
                    "description": (
                        f"claim {claim['claim_id']} is recorded as being in conflict "
                        f"({claim.get('epistemic_status')}/{claim.get('status')})"
                    ),
                    "claim_ids": [str(claim["claim_id"])],
                    "evidence_ids": sorted(str(e) for e in claim.get("counter_evidence_ids", [])),
                }
            )
        elif claim.get("counter_evidence_ids"):
            found.append(
                {
                    "description": (
                        f"claim {claim['claim_id']} has evidence against it that has not "
                        "been reconciled"
                    ),
                    "claim_ids": [str(claim["claim_id"])],
                    "evidence_ids": sorted(str(e) for e in claim["counter_evidence_ids"]),
                }
            )

    by_predicate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for claim in claims:
        if claim.get("status") != "ACTIVE":
            continue
        key = (str(claim.get("subject_entity_id")), str(claim.get("predicate")))
        by_predicate.setdefault(key, []).append(claim)

    for (subject, predicate), group in sorted(by_predicate.items()):
        values = {repr(c.get("object_value")) for c in group}
        if len(group) > 1 and len(values) > 1:
            found.append(
                {
                    "description": (
                        f"{len(group)} active claims disagree about {predicate!r} for {subject}"
                    ),
                    "claim_ids": sorted(str(c["claim_id"]) for c in group),
                    "evidence_ids": [],
                }
            )

    return sorted(found, key=lambda c: (c["description"], c["claim_ids"]))


def _active_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decisions currently in force.

    A decision that has been superseded is not current, whatever its own
    ``status`` field still says. Both conditions are checked because a stale
    ``ACTIVE`` beside a filled ``superseded_by`` is exactly the record shape
    that lets an old decision beat a new one.
    """
    superseded = {
        str(d["supersedes"]) for d in decisions if d.get("supersedes")
    }
    return [
        d
        for d in decisions
        if d.get("status") == "ACTIVE"
        and not d.get("superseded_by")
        and str(d["decision_id"]) not in superseded
    ]


def get_state(
    store: BrainStore,
    scope: Scope,
    *,
    entity_id: str | None = None,
    include_global: bool = True,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
) -> dict[str, Any] | Absence:
    """A ``StateProjection`` for *scope*, derived and schema-valid, or an absence.

    Derived, not stored: the projection is rebuilt from claims, decisions,
    hypotheses and unknowns on every call, so it cannot drift from what it
    summarises. When the scope holds none of those, the answer is an explicit
    absence — a projection over an empty world would be an invention.
    """
    guard = ScopeGuard(requested=scope, include_global=include_global)

    claims = _about_entity(_in_scope(store, guard, "Claim"), entity_id)
    decisions = _in_scope(store, guard, "Decision")
    hypotheses = _about_entity(_in_scope(store, guard, "Hypothesis"), entity_id)
    unknowns = _about_entity(_in_scope(store, guard, "Unknown"), entity_id)

    contributing = claims + decisions + hypotheses + unknowns
    if not contributing:
        return Absence(
            Absence.NO_STATE_RECORDED,
            f"{scope}" + (f"/{entity_id}" if entity_id else ""),
            "nothing is recorded in this scope, so no state can be derived",
        )

    as_of = latest_timestamp(contributing)
    current_claims = [c for c in claims if c.get("status") == "ACTIVE"]
    open_hypotheses = [h for h in hypotheses if h.get("status") in OPEN_HYPOTHESIS_STATUSES]
    open_unknowns = [u for u in unknowns if u.get("status") in OPEN_UNKNOWN_STATUSES]
    active = _active_decisions(decisions)

    projection_id = "sp_" + _stable_suffix(
        store.fingerprint(), str(scope), entity_id or "", "state"
    )

    summary = (
        f"{len(current_claims)} current claims, {len(active)} active decisions, "
        f"{len(open_hypotheses)} open hypotheses, {len(open_unknowns)} open unknowns "
        f"in {scope}"
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "object_type": "StateProjection",
        "state_projection_id": projection_id,
        "entity_scope": scope.as_mapping(),
        "as_of": format_timestamp(as_of) if as_of else "1970-01-01T00:00:00Z",
        "summary": summary,
        "active_decision_ids": sorted(str(d["decision_id"]) for d in active),
        "current_claim_ids": sorted(str(c["claim_id"]) for c in current_claims),
        "open_hypothesis_ids": sorted(str(h["hypothesis_id"]) for h in open_hypotheses),
        "open_unknown_ids": sorted(str(u["unknown_id"]) for u in open_unknowns),
        "conflicts": _conflicts(claims),
        "next_best_learning": _next_best_learning(open_hypotheses, open_unknowns),
        "derived_from_ids": sorted(_ids_of(contributing)),
        "freshness_status": freshness_for(as_of, latest_timestamp(contributing), horizon),
    }


def _next_best_learning(
    hypotheses: list[dict[str, Any]], unknowns: list[dict[str, Any]]
) -> str | None:
    """The single most useful next thing to find out, or ``None``.

    Hypotheses win over unknowns because a hypothesis already states what would
    settle it. Among unknowns, priority decides and the id breaks ties, so the
    answer does not depend on iteration order.
    """
    stated = sorted(
        (h for h in hypotheses if h.get("next_best_learning")),
        key=lambda h: str(h["hypothesis_id"]),
    )
    if stated:
        return str(stated[0]["next_best_learning"])

    priority_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    ranked = sorted(
        unknowns,
        key=lambda u: (priority_rank.get(str(u.get("priority")), 9), str(u["unknown_id"])),
    )
    return f"resolve: {ranked[0]['statement']}" if ranked else None


def _ids_of(objects: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for obj in objects:
        for key, value in obj.items():
            if key.endswith("_id") and isinstance(value, str) and key != "source_id":
                ids.append(value)
                break
    return ids


def _stable_suffix(*parts: str) -> str:
    import hashlib

    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# get_delta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Delta:
    """What changed in a scope since a point in time.

    ``coverage`` is the field that matters most. "I found no changes" and "I
    cannot see far enough back to answer" are different statements, and a delta
    that reports the second as the first turns a blind spot into a reassurance.
    """

    scope: Scope
    since: str | None
    as_of: str | None
    coverage: str
    new_claim_ids: tuple[str, ...] = ()
    superseded_claim_ids: tuple[str, ...] = ()
    decision_changes: tuple[dict[str, Any], ...] = ()
    hypothesis_changes: tuple[dict[str, Any], ...] = ()
    resolved_unknown_ids: tuple[str, ...] = ()
    recent_events: tuple[dict[str, Any], ...] = ()
    state_transition_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    #: Every change in the window is accounted for.
    COVERED = "COVERED"
    #: The window starts before anything on record, so "nothing changed" cannot
    #: be concluded from an empty result.
    PARTIAL_NO_RECORD_BEFORE = "PARTIAL_NO_RECORD_BEFORE"
    #: Nothing is recorded in this scope at all.
    NO_RECORD = "NO_RECORD"

    def is_empty(self) -> bool:
        return not (
            self.new_claim_ids
            or self.superseded_claim_ids
            or self.decision_changes
            or self.hypothesis_changes
            or self.resolved_unknown_ids
            or self.recent_events
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.as_mapping(),
            "since": self.since,
            "as_of": self.as_of,
            "coverage": self.coverage,
            "new_claim_ids": list(self.new_claim_ids),
            "superseded_claim_ids": list(self.superseded_claim_ids),
            "decision_changes": list(self.decision_changes),
            "hypothesis_changes": list(self.hypothesis_changes),
            "resolved_unknown_ids": list(self.resolved_unknown_ids),
            "recent_events": list(self.recent_events),
            "state_transition_refs": list(self.state_transition_refs),
            "notes": list(self.notes),
        }


def _changed_since(obj: dict[str, Any], since: datetime | None, *fields: str) -> bool:
    if since is None:
        return True
    for name in fields:
        moment = parse_timestamp(obj.get(name))
        if moment is not None and moment > since:
            return True
    return False


def get_delta(
    store: BrainStore,
    scope: Scope,
    *,
    since: str | datetime | None = None,
    entity_id: str | None = None,
    include_global: bool = True,
) -> Delta:
    """What changed in *scope* after *since*.

    ``occurred_at`` and ``recorded_at`` are both carried on every event rather
    than reconciled into one timestamp. The gap between them is information: a
    thing that happened in March and was written down in September is a
    different situation from one that happened and was recorded the same day,
    and a delta that flattens the two cannot tell them apart.
    """
    guard = ScopeGuard(requested=scope, include_global=include_global)
    since_at = since if isinstance(since, datetime) else parse_timestamp(since)

    claims = _about_entity(_in_scope(store, guard, "Claim"), entity_id)
    decisions = _in_scope(store, guard, "Decision")
    hypotheses = _about_entity(_in_scope(store, guard, "Hypothesis"), entity_id)
    unknowns = _about_entity(_in_scope(store, guard, "Unknown"), entity_id)
    events = _in_scope(store, guard, "Event")

    everything = claims + decisions + hypotheses + unknowns + events
    if not everything:
        return Delta(
            scope=scope,
            since=_iso(since_at),
            as_of=None,
            coverage=Delta.NO_RECORD,
            notes=("nothing is recorded in this scope; this is not a statement that "
                   "nothing happened",),
        )

    earliest = min(
        (m for m in (_earliest_of(obj) for obj in everything) if m is not None),
        default=None,
    )
    coverage = Delta.COVERED
    notes: list[str] = []
    if since_at is not None and earliest is not None and since_at < earliest:
        coverage = Delta.PARTIAL_NO_RECORD_BEFORE
        notes.append(
            f"the record starts at {format_timestamp(earliest)}, after the requested "
            f"since={_iso(since_at)}; an empty result for the earlier part of the "
            "window means nothing was recorded, not that nothing happened"
        )

    new_claims = [
        c
        for c in claims
        if _changed_since(c, since_at, "created_at") and c.get("status") == "ACTIVE"
    ]
    superseded_claims = [
        c
        for c in claims
        if c.get("status") in ("SUPERSEDED", "RETRACTED")
        and _changed_since(c, since_at, "last_updated_at")
    ]

    decision_changes = [
        {
            "decision_id": str(d["decision_id"]),
            "status": str(d["status"]),
            "effective_from": d.get("effective_from"),
            "supersedes": d.get("supersedes"),
            "superseded_by": d.get("superseded_by"),
        }
        for d in decisions
        if _changed_since(d, since_at, "effective_from", "created_at")
    ]

    hypothesis_changes = [
        {
            "hypothesis_id": str(h["hypothesis_id"]),
            "status": str(h["status"]),
            "last_updated_at": h.get("last_updated_at"),
        }
        for h in hypotheses
        if _changed_since(h, since_at, "last_updated_at")
    ]

    resolved_unknowns = [
        u
        for u in unknowns
        if u.get("status") in ("RESOLVED", "NO_LONGER_RELEVANT")
        and _changed_since(u, since_at, "last_updated_at")
    ]

    recent_events = [
        {
            "event_id": str(e["event_id"]),
            "event_type": str(e["event_type"]),
            "occurred_at": e.get("occurred_at"),
            "recorded_at": e.get("recorded_at"),
            "actor": e.get("actor"),
        }
        for e in events
        if _changed_since(e, since_at, "occurred_at", "recorded_at")
    ]

    # An event recorded long after it occurred is worth saying out loud rather
    # than leaving for a reader to notice by comparing two fields.
    for event in recent_events:
        occurred = parse_timestamp(event.get("occurred_at"))
        recorded = parse_timestamp(event.get("recorded_at"))
        if occurred and recorded and recorded - occurred > timedelta(days=30):
            notes.append(
                f"event {event['event_id']} occurred {(recorded - occurred).days} days "
                "before it was recorded"
            )

    return Delta(
        scope=scope,
        since=_iso(since_at),
        as_of=_iso(latest_timestamp(everything)),
        coverage=coverage,
        new_claim_ids=tuple(sorted(str(c["claim_id"]) for c in new_claims)),
        superseded_claim_ids=tuple(sorted(str(c["claim_id"]) for c in superseded_claims)),
        decision_changes=tuple(sorted(decision_changes, key=lambda d: d["decision_id"])),
        hypothesis_changes=tuple(sorted(hypothesis_changes, key=lambda h: h["hypothesis_id"])),
        resolved_unknown_ids=tuple(sorted(str(u["unknown_id"]) for u in resolved_unknowns)),
        recent_events=tuple(sorted(recent_events, key=lambda e: (e["occurred_at"], e["event_id"]))),
        state_transition_refs=tuple(
            sorted(
                str(s["state_projection_id"])
                for s in _in_scope(store, guard, "StateProjection")
            )
        ),
        notes=tuple(notes),
    )


def _earliest_of(obj: dict[str, Any]) -> datetime | None:
    moments = [
        parse_timestamp(obj.get(name))
        for name in ("occurred_at", "created_at", "effective_from", "recorded_at")
    ]
    present = [m for m in moments if m is not None]
    return min(present) if present else None


def _iso(moment: datetime | None) -> str | None:
    return format_timestamp(moment) if moment is not None else None


__all__ = [
    "Delta",
    "EntityRelation",
    "EntityView",
    "carries_pii",
    "get_delta",
    "get_entity",
    "get_state",
]
