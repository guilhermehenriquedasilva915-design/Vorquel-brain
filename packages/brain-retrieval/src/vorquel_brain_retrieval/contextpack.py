"""``get_context_pack`` — the deterministic read model.

A ContextPack is what an AI is given for one objective. It is a **read model**:
assembled for a purpose, pointing at everything it includes, and never a source
of truth for any of it.

Determinism is a property this module owes, not one it hopes for. For the same
store, the same inputs and the same generator version, the pack must come out
byte-identical. That is achieved by four rules, each of which has a test:

* **Ordering is total.** Every list is sorted, and every sort has an id-based
  tie-break, so two items that compare equal on everything else still cannot
  swap places between runs.
* **Nothing reads the clock.** ``generated_at`` defaults to the newest timestamp
  in the store, not to ``now()``. A caller may override it, which is why the
  next rule exists.
* **Identity excludes ``generated_at``.** ``context_pack_id`` is a hash of the
  pack's *logical* identity — inputs plus a fingerprint of the world plus the
  ids included. Two packs generated at different moments from the same facts are
  the same pack, and say so.
* **Identity includes the store fingerprint.** The same question asked of a
  different world is a different pack, rather than two different packs quietly
  sharing an id.

The emitted pack validates against ``context_pack.schema.json``, which is
closed. Anything that is not a field of that schema is not smuggled in beside
it: the resolved ``StateProjection`` and the ``Delta`` are returned next to the
pack, as the contract objects they already are.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from vorquel_brain_contract import (
    CONTEXT_PACK_MODES,
    CONTRACT_VERSION,
    NO_EVIDENCE_FOUND,
    SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK,
)

from .budget import (
    DROP_ORDER,
    TrimLog,
    estimate_tokens,
)
from .errors import Absence, BudgetTooSmallError
from .pipeline import RetrievalResult, retrieve
from .policy import DEFAULT_STALENESS_HORIZON, data_classes_of, is_secret, max_sensitivity
from .reads import Delta
from .scope import Scope
from .store import BrainStore

#: Version of the ContextPack *generator*. Bumped when the assembled shape or
#: the assembly rules change, because a pack id is only meaningful relative to
#: the rules that produced it.
CONTEXT_PACK_VERSION = "1.0.0"

#: Length of a pack id: ``cp_`` plus 32 hex characters. The placeholder used
#: while assembling is exactly this long so that budgeting measures the pack that
#: is actually issued.
_ID_HEX_LENGTH = 32
_ID_PLACEHOLDER = "cp_" + "0" * _ID_HEX_LENGTH

#: What each mode is for. Modes change emphasis and budget priorities; none of
#: them changes what the scope guard admits or what SECRET means.
MODE_PROFILES: dict[str, dict[str, Any]] = {
    "OPERATIONAL": {"events": 5, "evidence": 10, "prefer": "current"},
    "RESEARCH": {"events": 3, "evidence": 25, "prefer": "evidence"},
    "BUILD": {"events": 5, "evidence": 12, "prefer": "procedural"},
    "AUDIT": {"events": 25, "evidence": 25, "prefer": "provenance"},
    "STRATEGY": {"events": 3, "evidence": 12, "prefer": "decisions"},
}


@dataclass(frozen=True)
class ContextPackResult:
    """The pack, plus the contract objects it points at.

    The pack itself is pointer-based, as its schema requires. Returning the
    resolved ``StateProjection`` and ``Delta`` alongside it saves every consumer
    a second round trip without inventing a richer pack shape that would then
    compete with the published one.
    """

    pack: dict[str, Any]
    state_projection: dict[str, Any] | None
    delta: Delta
    retrieval: RetrievalResult
    trim_log: TrimLog

    @property
    def context_pack_id(self) -> str:
        return str(self.pack["context_pack_id"])

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.pack)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _pack_identity(pack: dict[str, Any], store_fingerprint: str, requirements: Any) -> str:
    """The pack's logical identity: everything but when it was assembled.

    ``generated_at`` is excluded on purpose. Two packs built from the same facts
    for the same objective are the same pack; if the timestamp were part of the
    identity, reproducibility would be untestable and every regeneration would
    look like a new context.
    """
    identity = {
        "version": CONTEXT_PACK_VERSION,
        "contract_version": pack["contract_version"],
        "objective": pack["objective"],
        "mode": pack["mode"],
        "scope": pack["scope"],
        "entity_ids": pack["entity_ids"],
        "token_budget": pack["token_budget"],
        "requirements": requirements,
        "store": store_fingerprint,
        "included": {
            key: pack[key]
            for key in (
                "state_projection_ids",
                "decision_ids",
                "claim_ids",
                "evidence_ids",
                "hypothesis_ids",
                "unknown_ids",
                "recent_event_ids",
                "procedural_refs",
                "artifact_refs",
                "constraints",
                "gaps",
                "provenance_summary",
            )
        },
    }
    return "cp_" + hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()[:_ID_HEX_LENGTH]


def _provenance_entries(
    store: BrainStore, claim_ids: list[str], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    """One entry per included object that asserts something.

    Claims and evidence assert; decisions, hypotheses and unknowns do not assert
    facts about the world in the same way, so they are not required to carry a
    pointer here. Anything that does assert and cannot produce a pointer is not
    in the pack at all — see :func:`get_context_pack`.
    """
    entries: list[dict[str, Any]] = []

    for claim_id in claim_ids:
        claim = store.by_id("Claim", claim_id)
        if claim is None:
            continue
        provenance = [dict(p) for p in claim.get("provenance", []) if isinstance(p, dict)]
        if not provenance:
            provenance = [
                {"source_id": str(source_id)} for source_id in sorted(claim.get("source_ids", []))
            ]
        entries.append(
            {"object_id": claim_id, "object_type": "Claim", "provenance": provenance}
        )

    for evidence_id in evidence_ids:
        evidence = store.by_id("Evidence", evidence_id)
        if evidence is None:
            continue
        provenance = [dict(p) for p in evidence.get("provenance", []) if isinstance(p, dict)]
        if not provenance and evidence.get("source_id"):
            provenance = [{"source_id": str(evidence["source_id"])}]
        entries.append(
            {"object_id": evidence_id, "object_type": "Evidence", "provenance": provenance}
        )

    return sorted(entries, key=lambda e: (e["object_type"], e["object_id"]))


def _asserts_without_provenance(entries: list[dict[str, Any]]) -> list[str]:
    return sorted(e["object_id"] for e in entries if not e["provenance"])


def get_context_pack(
    store: BrainStore,
    objective: str,
    scope: Scope,
    *,
    mode: str = "OPERATIONAL",
    token_budget: int = 8000,
    entity_query: str | None = None,
    entity_ids: tuple[str, ...] = (),
    requirements: tuple[str, ...] = (),
    since: str | None = None,
    include_global: bool = True,
    generated_at: str | None = None,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
) -> ContextPackResult:
    """Assemble a ContextPack for one objective.

    Raises :class:`~.errors.BudgetTooSmallError` when the budget cannot hold the
    non-droppable core. It does not return a reduced pack, because a pack that
    has lost its provenance is indistinguishable from one that never had any.
    """
    if mode not in CONTEXT_PACK_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {', '.join(CONTEXT_PACK_MODES)}")
    if token_budget < 1:
        raise ValueError("token_budget must be at least 1")

    profile = MODE_PROFILES[mode]
    result = retrieve(
        store,
        objective,
        scope,
        entity_query=entity_query,
        entity_ids=entity_ids,
        since=since,
        include_global=include_global,
        horizon=horizon,
        evidence_limit=int(profile["evidence"]),
    )

    state = None if isinstance(result.state, Absence) else result.state
    gaps: list[str] = []

    if state is None:
        gaps.append(
            f"no state is recorded for {scope}; this is an absence in the record, "
            "not a finding that the scope is empty of activity"
        )
    if result.resolution is not None and result.resolution.ambiguity:
        gaps.append(
            f"entity query {result.resolution.query!r} is ambiguous between "
            f"{', '.join(m.entity_id for m in result.resolution.matches)}; "
            "no entity was chosen"
        )
    if result.evidence.absence is not None:
        gaps.append(
            f"{NO_EVIDENCE_FOUND}: nothing matched {objective!r} in {scope}. "
            "This is not evidence that any claim is false."
        )
    for stage in result.evidence.stages_unavailable:
        gaps.append(f"retrieval stage {stage} is not available in this deployment")
    if result.delta.coverage != Delta.COVERED:
        gaps.append(f"delta coverage is {result.delta.coverage}: " + "; ".join(result.delta.notes))

    # ---- what goes in -----------------------------------------------------

    claim_ids = sorted(state["current_claim_ids"]) if state else []
    decision_ids = sorted(state["active_decision_ids"]) if state else []
    hypothesis_ids = sorted(state["open_hypothesis_ids"]) if state else []
    unknown_ids = sorted(state["open_unknown_ids"]) if state else []
    evidence_ids = sorted(hit.evidence_id for hit in result.evidence.hits)
    event_ids = sorted(e["event_id"] for e in result.delta.recent_events)[: int(profile["events"])]

    # ---- SECRET is excluded, and its exclusion is recorded -----------------
    #
    # A SECRET item never enters a pack. That it was withheld *is* recorded, as
    # a gap, because a silent omission and an empty record look the same to a
    # reader and only one of them should.

    withheld = _withheld_secrets(store, scope, include_global=include_global)
    if withheld:
        gaps.append(
            f"{len(withheld)} object(s) in scope are {SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK} "
            "and are excluded from this pack by contract; they are not summarised, "
            "redacted or counted in any list above"
        )

    provenance_summary = _provenance_entries(store, claim_ids, evidence_ids)

    # An asserting object that cannot produce a pointer is dropped, not carried
    # with an empty provenance list. MEDIDO without a source is the canonical
    # case and it must fail closed here rather than be reported as a finding.
    unprovenanced = set(_asserts_without_provenance(provenance_summary))
    if unprovenanced:
        gaps.append(
            f"{len(unprovenanced)} asserting object(s) were excluded for having no "
            f"traceable source: {', '.join(sorted(unprovenanced))}"
        )
        claim_ids = [c for c in claim_ids if c not in unprovenanced]
        evidence_ids = [e for e in evidence_ids if e not in unprovenanced]
        provenance_summary = [p for p in provenance_summary if p["object_id"] not in unprovenanced]

    constraints = _constraints_from(store, decision_ids)
    procedural_refs = sorted(requirements)

    included = _included_objects(
        store, claim_ids, evidence_ids, decision_ids, hypothesis_ids, unknown_ids
    )
    sensitivity_level = max_sensitivity([_tier(obj) for obj in included])
    data_classes = sorted({cls for obj in included for cls in data_classes_of(obj)})

    pack: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "ContextPack",
        # A placeholder of exactly the length the real id will have. The id is
        # assigned last, over the final contents, but it still costs tokens —
        # measuring a pack with an empty id and then writing 35 characters into
        # it is how a pack ends up over the budget it reports.
        "context_pack_id": _ID_PLACEHOLDER,
        "version": CONTEXT_PACK_VERSION,
        "objective": objective,
        "mode": mode,
        "scope": scope.as_mapping(),
        "entity_ids": sorted(set(result.entity_ids) | set(result.expanded_entity_ids)),
        "generated_at": generated_at or _default_generated_at(result, store),
        "state_projection_ids": [state["state_projection_id"]] if state else [],
        "decision_ids": decision_ids,
        "claim_ids": claim_ids,
        "evidence_ids": evidence_ids,
        "hypothesis_ids": hypothesis_ids,
        "unknown_ids": unknown_ids,
        "recent_event_ids": event_ids,
        "artifact_refs": [],
        "gaps": sorted(gaps),
        "constraints": constraints,
        "procedural_refs": procedural_refs,
        "token_budget": token_budget,
        "sensitivity_level": sensitivity_level,
        "data_classes": data_classes,
        "provenance_summary": provenance_summary,
        "freshness_status": state["freshness_status"] if state else "UNKNOWN_FRESHNESS",
    }

    trim_log = _fit_to_budget(store, pack, token_budget, sorted(gaps))

    # Identity last, over the final contents: a pack id assigned before trimming
    # would name a pack that was never issued. It replaces a placeholder of the
    # same length, so the size the budget was checked against is the size that
    # ships.
    identity = _pack_identity(pack, store.fingerprint(), list(requirements))
    assert len(identity) == len(_ID_PLACEHOLDER)
    pack["context_pack_id"] = identity

    return ContextPackResult(
        pack=pack,
        state_projection=state,
        delta=result.delta,
        retrieval=result,
        trim_log=trim_log,
    )


def _default_generated_at(result: RetrievalResult, store: BrainStore) -> str:
    """The newest moment the world knows about, not the wall clock.

    Reading the clock here would make every pack differ from every other pack,
    which would make reproducibility a thing that can only be asserted.
    """
    if not isinstance(result.state, Absence):
        return str(result.state["as_of"])
    if result.delta.as_of:
        return result.delta.as_of
    from .policy import format_timestamp, latest_timestamp

    newest = latest_timestamp(
        [obj for object_type in ("Event", "Claim", "Evidence") for obj in store.all_of(object_type)]
    )
    return format_timestamp(newest) if newest else "1970-01-01T00:00:00Z"


def _withheld_secrets(store: BrainStore, scope: Scope, *, include_global: bool) -> list[str]:
    from .scope import ScopeGuard

    guard = ScopeGuard(requested=scope, include_global=include_global)
    withheld: list[str] = []
    for object_type in ("Claim", "Evidence", "Source", "Entity", "Decision"):
        for obj in store.all_of(object_type):
            if guard.admits(obj) and is_secret(obj):
                withheld.append(object_type)
    return withheld


def _tier(obj: dict[str, Any]) -> str:
    from .policy import sensitivity_of

    return sensitivity_of(obj)


def _included_objects(
    store: BrainStore,
    claim_ids: list[str],
    evidence_ids: list[str],
    decision_ids: list[str],
    hypothesis_ids: list[str],
    unknown_ids: list[str],
) -> list[dict[str, Any]]:
    pairs = (
        [("Claim", i) for i in claim_ids]
        + [("Evidence", i) for i in evidence_ids]
        + [("Decision", i) for i in decision_ids]
        + [("Hypothesis", i) for i in hypothesis_ids]
        + [("Unknown", i) for i in unknown_ids]
    )
    found = [store.by_id(object_type, object_id) for object_type, object_id in pairs]
    return [obj for obj in found if obj is not None]


def _constraints_from(store: BrainStore, decision_ids: list[str]) -> list[str]:
    """Active decisions restated as constraints.

    Non-droppable under budget pressure: a pack that keeps the evidence and
    drops the decision that forbids acting on it is worse than one that keeps
    neither.
    """
    constraints: list[str] = []
    for decision_id in decision_ids:
        decision = store.by_id("Decision", decision_id)
        if decision is not None:
            constraints.append(f"{decision_id}: {decision['decision']}")
    return sorted(constraints)


# ---------------------------------------------------------------------------
# Trimming
# ---------------------------------------------------------------------------


def _fit_to_budget(
    store: BrainStore, pack: dict[str, Any], budget: int, base_gaps: list[str]
) -> TrimLog:
    """Drop content until the pack fits, or refuse.

    Each step removes one class of thing and stops as soon as the pack fits, so
    a pack that only needs a small trim keeps everything the next step would
    have taken.

    Recording a trim *costs tokens*, because saying what was removed is itself
    content. The gap lines are therefore written into the pack before each
    measurement rather than appended afterwards; measuring the pack and then
    growing it is how a pack ends up over the budget it reports.

    When the ordered list is exhausted and the pack is still too big, the
    smallest permitted pack is still too big. That is a refusal, not a smaller
    pack: what remains at that point is the non-droppable core plus the
    pointers whose provenance the pack still carries, and there is no honest way
    to shrink it further.
    """
    log = TrimLog()

    def commit() -> int:
        pack["gaps"] = sorted(set(base_gaps) | set(log.as_gap_lines()))
        return estimate_tokens(pack)

    size = commit()
    if size <= budget:
        return log

    smallest = size
    for step in DROP_ORDER:
        # A trim that costs more than it saves is not a trim. Recording a
        # removal takes tokens, and for a handful of short items the sentence
        # explaining the drop is longer than what it dropped. Such a step is
        # rolled back rather than applied, so trimming is monotone and the
        # budget cannot be exceeded by the act of being honest about trimming.
        before_pack = deepcopy(pack)
        before_entries = list(log.entries)

        _apply_drop_step(store, pack, step, log)
        size = commit()

        if size >= smallest:
            pack.clear()
            pack.update(before_pack)
            log.entries[:] = before_entries
            continue

        smallest = size
        if size <= budget:
            return log

    raise BudgetTooSmallError(
        requested=budget,
        # The smallest pack actually reachable, measured rather than estimated.
        # Not the bare core: claim, decision, hypothesis and unknown pointers
        # are not droppable, and quoting the core alone would promise a pack
        # that cannot be built.
        minimum_required=smallest,
        missing=(
            f"the pack identity, objective, scope, {len(pack['constraints'])} constraint(s), "
            f"{len(pack['gaps'])} gap(s) and the provenance of "
            f"{len(pack['provenance_summary'])} retained object(s)",
        ),
    )


def _apply_drop_step(
    store: BrainStore, pack: dict[str, Any], step: str, log: TrimLog
) -> None:
    if step == "VERBOSE_SUMMARY":
        # Gap lines are kept; they are the record of what is missing. What goes
        # is the long-form restatement of constraints, which is recoverable from
        # decision_ids.
        removed = [c.split(":", 1)[0] for c in pack["constraints"] if len(c) > 160]
        pack["constraints"] = sorted(
            c if len(c) <= 160 else c[:157] + "..." for c in pack["constraints"]
        )
        log.record(step, removed, "constraints (shortened)")

    elif step == "LOW_RELEVANCE_ARTIFACTS":
        removed = [a["artifact_id"] for a in pack["artifact_refs"]]
        pack["artifact_refs"] = []
        log.record(step, removed, "artifact_refs")

    elif step == "OLDER_EVENTS":
        keep = pack["recent_event_ids"][-2:] if len(pack["recent_event_ids"]) > 2 else []
        removed = [e for e in pack["recent_event_ids"] if e not in keep]
        pack["recent_event_ids"] = keep
        log.record(step, removed, "recent_event_ids")

    elif step == "WEAKER_EVIDENCE":
        removed = _drop_weaker_evidence(store, pack)
        log.record(step, removed, "evidence_ids")

    elif step == "SECONDARY_PROCEDURAL_REFS":
        keep = pack["procedural_refs"][:1]
        removed = [r for r in pack["procedural_refs"] if r not in keep]
        pack["procedural_refs"] = keep
        log.record(step, removed, "procedural_refs")


def _drop_weaker_evidence(store: BrainStore, pack: dict[str, Any]) -> list[str]:
    """Remove WEAK then MODERATE evidence, and its provenance with it.

    The provenance entry for a dropped item goes too. Leaving it behind would
    make the pack claim traceability for something it no longer contains, which
    is the mirror image of the rule this module exists to enforce: nothing
    stays without its provenance, and no provenance stays without its item.
    """
    order = {"WEAK": 0, "MODERATE": 1, "STRONG": 2}
    ranked = sorted(
        pack["evidence_ids"],
        key=lambda e: (order.get(str((store.by_id("Evidence", e) or {}).get("strength")), 3), e),
    )
    # Keep the strongest quarter, at least one item, so a trimmed pack still has
    # something to stand on rather than becoming an assertion with no support.
    keep_count = max(1, len(ranked) // 4)
    removed = ranked[:-keep_count] if keep_count < len(ranked) else []

    pack["evidence_ids"] = sorted(set(pack["evidence_ids"]) - set(removed))
    pack["provenance_summary"] = [
        entry for entry in pack["provenance_summary"] if entry["object_id"] not in set(removed)
    ]
    return removed
