"""The retrieval pipeline, in the order the contract requires.

    entity resolution
      -> scope guard
      -> current state
      -> structured relational retrieval
      -> lexical / FTS
      -> controlled relation expansion
      -> raw source pointer

Semantic retrieval is not in that list because it does not exist here. It is
reported as an unavailable stage rather than omitted, so nothing downstream can
come to depend on it having run.

The pipeline returns a :class:`RetrievalTrace` alongside its results. The trace
is not debug output: it is the evidence that retrieval ran relational-first, and
``tests/test_retrieval_pipeline.py`` asserts against it. A pipeline that claims
an order in a docstring and does something else in the code is the exact failure
this makes visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .errors import Absence
from .evidence import STAGE_SEMANTIC, EvidenceSearchResult, search_evidence
from .policy import DEFAULT_STALENESS_HORIZON, is_secret
from .reads import Delta, get_delta, get_state
from .resolve import EntityResolution, resolve_entity
from .scope import Scope, ScopeGuard
from .store import BrainStore

#: The stages, in order. Named so a test can assert the sequence rather than
#: trusting that the calls below stay in the order they were written in.
PIPELINE_STAGES: tuple[str, ...] = (
    "ENTITY_RESOLUTION",
    "SCOPE_GUARD",
    "CURRENT_STATE",
    "STRUCTURED_RELATIONAL",
    "LEXICAL",
    "RELATION_EXPANSION",
    "RAW_SOURCE_POINTER",
)


@dataclass(frozen=True)
class StageRecord:
    stage: str
    ran: bool
    produced: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ran": self.ran,
            "produced": self.produced,
            "note": self.note,
        }


@dataclass
class RetrievalTrace:
    stages: list[StageRecord] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)

    def record(self, stage: str, *, ran: bool, produced: int, note: str = "") -> None:
        self.stages.append(StageRecord(stage, ran, produced, note))

    def order(self) -> tuple[str, ...]:
        return tuple(s.stage for s in self.stages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stages": [s.as_dict() for s in self.stages],
            "unavailable": list(self.unavailable),
        }


@dataclass(frozen=True)
class RetrievalResult:
    scope: Scope
    resolution: EntityResolution | None
    entity_ids: tuple[str, ...]
    state: dict[str, Any] | Absence
    delta: Delta
    evidence: EvidenceSearchResult
    expanded_entity_ids: tuple[str, ...]
    source_pointers: tuple[dict[str, Any], ...]
    trace: RetrievalTrace


def expand_relations(
    store: BrainStore,
    entity_ids: tuple[str, ...],
    guard: ScopeGuard,
    *,
    max_depth: int = 1,
) -> tuple[str, ...]:
    """Entities reachable from *entity_ids* through in-scope claims.

    Controlled in three ways at once, because expansion is the feature most
    likely to turn into a leak: it only traverses claims the guard already
    admits, it only reaches entities the guard also admits, and it stops at
    ``max_depth`` (one hop by default). Unbounded expansion from a client entity
    would eventually walk into whatever the graph happens to connect to.
    """
    reached: set[str] = set()
    frontier = set(entity_ids)

    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for claim in store.all_of("Claim"):
            if not guard.admits(claim) or is_secret(claim):
                continue
            subject = str(claim.get("subject_entity_id") or "")
            target = str(claim.get("object_entity_id") or "")
            if not target or subject not in frontier:
                continue
            entity = store.by_id("Entity", target)
            if entity is None or not guard.admits(entity) or is_secret(entity):
                continue
            if target not in entity_ids and target not in reached:
                reached.add(target)
                next_frontier.add(target)
        frontier = next_frontier
        if not frontier:
            break

    return tuple(sorted(reached))


def retrieve(
    store: BrainStore,
    objective: str,
    scope: Scope,
    *,
    entity_query: str | None = None,
    entity_ids: tuple[str, ...] = (),
    since: str | None = None,
    include_global: bool = True,
    expand: bool = True,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
    evidence_limit: int = 25,
) -> RetrievalResult:
    """Run the full read path for one objective."""
    trace = RetrievalTrace(unavailable=[STAGE_SEMANTIC])

    # 1. Entity resolution.
    resolution: EntityResolution | None = None
    resolved: list[str] = list(entity_ids)
    if entity_query:
        resolution = resolve_entity(store, entity_query, scope, include_global=include_global)
        # An ambiguous query does not silently pick. Every candidate is carried
        # forward and the ambiguity travels with the result, so a caller decides
        # rather than discovering later that something decided for it.
        resolved.extend(m.entity_id for m in resolution.matches)
    resolved_ids = tuple(sorted(set(resolved)))
    trace.record(
        "ENTITY_RESOLUTION",
        ran=entity_query is not None,
        produced=len(resolved_ids),
        note="ambiguous" if resolution and resolution.ambiguity else "",
    )

    # 2. Scope guard. Constructed once and threaded through everything after it.
    guard = ScopeGuard(requested=scope, include_global=include_global)
    trace.record("SCOPE_GUARD", ran=True, produced=len(guard.visible_scopes()), note=str(guard))

    # 3. Current state.
    state = get_state(
        store,
        scope,
        entity_id=resolved_ids[0] if len(resolved_ids) == 1 else None,
        include_global=include_global,
        horizon=horizon,
    )
    trace.record(
        "CURRENT_STATE",
        ran=True,
        produced=0 if isinstance(state, Absence) else len(state["current_claim_ids"]),
        note=state.kind if isinstance(state, Absence) else state["freshness_status"],
    )

    delta = get_delta(store, scope, since=since, include_global=include_global)

    # 4 + 5. Structured relational, then lexical. Both inside search_evidence,
    # which applies them in that order and reports which one produced each hit.
    found = search_evidence(
        store,
        objective,
        scope,
        entity_ids=resolved_ids,
        include_global=include_global,
        limit=evidence_limit,
    )
    relational_hits = sum(1 for h in found.hits if "STRUCTURED_RELATIONAL" in h.retrieval_stages)
    trace.record("STRUCTURED_RELATIONAL", ran=True, produced=relational_hits)
    trace.record(
        "LEXICAL",
        ran=True,
        produced=sum(1 for h in found.hits if "LEXICAL" in h.retrieval_stages),
    )

    # 6. Relation expansion, bounded.
    expanded = expand_relations(store, resolved_ids, guard) if expand and resolved_ids else ()
    trace.record("RELATION_EXPANSION", ran=expand and bool(resolved_ids), produced=len(expanded))

    # 7. Raw source pointers, deduplicated and ordered.
    pointers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for hit in found.hits:
        for pointer in hit.source_pointers:
            key = (pointer["source_id"], pointer.get("fragment_id") or "")
            if key not in seen:
                seen.add(key)
                pointers.append(pointer)
    trace.record("RAW_SOURCE_POINTER", ran=True, produced=len(pointers))

    return RetrievalResult(
        scope=scope,
        resolution=resolution,
        entity_ids=resolved_ids,
        state=state,
        delta=delta,
        evidence=found,
        expanded_entity_ids=expanded,
        source_pointers=tuple(pointers),
        trace=trace,
    )
