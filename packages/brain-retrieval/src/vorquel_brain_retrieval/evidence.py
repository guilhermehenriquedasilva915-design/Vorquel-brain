"""``search_evidence`` — evidence-first retrieval, relational before lexical.

The order is the design, not an optimisation:

1. **scope filter** — before anything is matched, so nothing out of scope can
   influence a score, a ranking or a result count;
2. **structured relational** — entity links, claim links and explicit filters,
   which are facts about the graph rather than guesses about text;
3. **lexical** — token overlap against the fragments an evidence item actually
   cites;
4. **semantic** — not implemented. No vector database is introduced by
   Brain-V1-B, and the pipeline reports the stage as unavailable rather than
   silently skipping it, so a caller can tell the difference between "nothing
   semantic matched" and "nothing semantic was tried".

``retrieval_score`` says how well something matched the query. ``epistemic_status``
says how it came to be known. They are separate fields because they answer
separate questions, and a strong lexical match on a HIPOTESE is still a
hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import Absence
from .policy import carries_pii, data_classes_of, is_secret, sensitivity_of
from .resolve import normalize
from .scope import Scope, ScopeGuard
from .store import BrainStore

#: Retrieval stages, in the order they run.
STAGE_SCOPE = "SCOPE_FILTER"
STAGE_RELATIONAL = "STRUCTURED_RELATIONAL"
STAGE_LEXICAL = "LEXICAL"
STAGE_SEMANTIC = "SEMANTIC"

#: Weights. A structured hit outranks a lexical one at every level, because a
#: recorded link between an evidence item and an entity is a fact and a shared
#: word is a coincidence until shown otherwise.
_RELATIONAL_WEIGHT = 0.6
_LEXICAL_WEIGHT = 0.4

_STRENGTH_ORDER = {"STRONG": 0, "MODERATE": 1, "WEAK": 2}

#: Shortest token that may count as a lexical match. Two-letter words in
#: Portuguese and English are overwhelmingly function words — *de*, *ao*, *da*,
#: *of*, *to* — and letting one carry a match means any two documents written in
#: the same language overlap. Dropping them is a deliberate loss of recall on
#: genuinely short terms, taken because a match on "de" is not a match.
MIN_TOKEN_LENGTH = 3


def query_tokens(query: str) -> set[str]:
    """The tokens of a query that are allowed to carry a lexical match."""
    return {token for token in normalize(query).split() if len(token) >= MIN_TOKEN_LENGTH}


@dataclass(frozen=True)
class EvidenceHit:
    evidence_id: str
    source_id: str
    fragment_ids: tuple[str, ...]
    direction: str
    strength: str
    evidence_type: str
    epistemic_status: str
    entity_scope: Scope
    subject_entity_id: str | None
    observed_at: str | None
    source_pointers: tuple[dict[str, Any], ...]
    #: How well it matched. **Not** an epistemic judgement.
    retrieval_score: float
    retrieval_stages: tuple[str, ...]
    sensitivity_level: str
    data_classes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "fragment_ids": list(self.fragment_ids),
            "direction": self.direction,
            "strength": self.strength,
            "evidence_type": self.evidence_type,
            "epistemic_status": self.epistemic_status,
            "entity_scope": self.entity_scope.as_mapping(),
            "subject_entity_id": self.subject_entity_id,
            "observed_at": self.observed_at,
            "source_pointers": [dict(p) for p in self.source_pointers],
            "retrieval_score": round(self.retrieval_score, 6),
            "retrieval_stages": list(self.retrieval_stages),
            "sensitivity_level": self.sensitivity_level,
            "data_classes": list(self.data_classes),
        }


@dataclass(frozen=True)
class EvidenceSearchResult:
    query: str
    scope: Scope
    hits: tuple[EvidenceHit, ...]
    stages_run: tuple[str, ...]
    stages_unavailable: tuple[str, ...]
    absence: Absence | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope.as_mapping(),
            "hits": [h.as_dict() for h in self.hits],
            "stages_run": list(self.stages_run),
            "stages_unavailable": list(self.stages_unavailable),
            "absence": self.absence.as_dict() if self.absence else None,
        }


def _source_pointers(
    store: BrainStore, evidence: dict[str, Any], guard: ScopeGuard
) -> tuple[dict[str, Any], ...]:
    """Where this evidence actually came from.

    Built from the evidence's own provenance where it has it, and otherwise from
    its source and fragments. A hit with no traceable pointer is not returned at
    all; see :func:`search_evidence`.
    """
    pointers: list[dict[str, Any]] = []
    for entry in evidence.get("provenance", []):
        if isinstance(entry, dict) and entry.get("source_id"):
            pointers.append(
                {
                    "source_id": str(entry["source_id"]),
                    "fragment_id": entry.get("fragment_id"),
                    "locator": entry.get("locator"),
                    "observed_at": entry.get("observed_at"),
                    "content_hash": entry.get("content_hash"),
                }
            )

    if not pointers and evidence.get("source_id"):
        source = store.by_id("Source", str(evidence["source_id"]))
        # A pointer into a source the caller cannot see is not a pointer, it is
        # a hint that the source exists.
        if source is not None and guard.admits(source) and not is_secret(source):
            for fragment_id in evidence.get("fragment_ids", []):
                fragment = store.by_id("SourceFragment", str(fragment_id))
                pointers.append(
                    {
                        "source_id": str(evidence["source_id"]),
                        "fragment_id": str(fragment_id),
                        "locator": (fragment or {}).get("provenance", {}).get("locator"),
                        "observed_at": evidence.get("observed_at"),
                        "content_hash": (fragment or {}).get("content_hash"),
                    }
                )
            if not evidence.get("fragment_ids"):
                pointers.append(
                    {
                        "source_id": str(evidence["source_id"]),
                        "fragment_id": None,
                        "locator": None,
                        "observed_at": evidence.get("observed_at"),
                        "content_hash": source.get("content_hash"),
                    }
                )

    return tuple(sorted(pointers, key=lambda p: (p["source_id"], p.get("fragment_id") or "")))


def _lexical_score(store: BrainStore, evidence: dict[str, Any], tokens_wanted: set[str]) -> float:
    """Fraction of the query's tokens present in the text this evidence cites.

    Deliberately searches the *fragments*, not a summary written about them. A
    match against a summary is a match against someone's paraphrase, which is
    one remove further from the source than this package is willing to rank on.
    """
    if not tokens_wanted:
        return 0.0
    text_parts: list[str] = []
    for fragment_id in evidence.get("fragment_ids", []):
        fragment = store.by_id("SourceFragment", str(fragment_id))
        if fragment:
            text_parts.append(str(fragment.get("content", "")))
    source = store.by_id("Source", str(evidence.get("source_id", "")))
    if source:
        text_parts.append(str(source.get("title", "")))
    tokens = set(normalize(" ".join(text_parts)).split())
    return len(tokens_wanted & tokens) / len(tokens_wanted) if tokens else 0.0


def _relational_score(
    evidence: dict[str, Any],
    entity_ids: frozenset[str],
    linked_evidence_ids: frozenset[str],
) -> float:
    """1.0 for a recorded link to the entity, 0.7 via a claim, 0.0 otherwise."""
    subject = evidence.get("subject_entity_id")
    if subject and str(subject) in entity_ids:
        return 1.0
    if str(evidence.get("evidence_id")) in linked_evidence_ids:
        return 0.7
    return 0.0


def search_evidence(
    store: BrainStore,
    query: str,
    scope: Scope,
    *,
    entity_ids: tuple[str, ...] = (),
    filters: dict[str, Any] | None = None,
    include_global: bool = True,
    limit: int = 25,
    min_score: float = 0.01,
) -> EvidenceSearchResult:
    """Evidence visible from *scope* matching *query*.

    An evidence item with no traceable source pointer is **dropped**, not
    returned with an empty provenance list. Handing back a finding that cannot
    be followed to its origin is how an assertion loses the thing that made it
    checkable.

    An empty result is an ``Absence`` of kind ``NO_EVIDENCE_FOUND``, never an
    empty list quietly meaning "no".
    """
    guard = ScopeGuard(requested=scope, include_global=include_global)
    filters = filters or {}
    tokens_wanted = query_tokens(query)
    wanted = frozenset(entity_ids)

    stages_run = [STAGE_SCOPE, STAGE_RELATIONAL, STAGE_LEXICAL]
    # Stated, not skipped. There is no embedding index in this repository, and a
    # pipeline that silently omits a stage cannot be told apart from one where
    # the stage found nothing.
    stages_unavailable = [STAGE_SEMANTIC]

    # Stage 2 input: which evidence the graph already links to the entities.
    linked: set[str] = set()
    if wanted:
        for claim in store.all_of("Claim"):
            if not guard.admits(claim) or is_secret(claim):
                continue
            if str(claim.get("subject_entity_id")) not in wanted:
                continue
            for key in ("supporting_evidence_ids", "counter_evidence_ids"):
                linked.update(str(e) for e in claim.get(key, []))
    linked_evidence_ids = frozenset(linked)

    hits: list[EvidenceHit] = []
    for evidence in store.all_of("Evidence"):
        # Stage 1. Before matching, so nothing out of scope can even be scored.
        if not guard.admits(evidence) or is_secret(evidence):
            continue

        if not _passes_filters(evidence, filters):
            continue

        relational = _relational_score(evidence, wanted, linked_evidence_ids)
        lexical = _lexical_score(store, evidence, tokens_wanted)

        # An entity was named and this evidence is attached to a different one:
        # a shared word is not a reason to attribute it. This is the rule that
        # keeps generic material from becoming evidence about a specific client.
        subject = evidence.get("subject_entity_id")
        if wanted and subject and str(subject) not in wanted:
            continue

        score = _RELATIONAL_WEIGHT * relational + _LEXICAL_WEIGHT * lexical
        if score < min_score:
            continue

        pointers = _source_pointers(store, evidence, guard)
        if not pointers:
            continue

        stages = tuple(
            stage
            for stage, matched in ((STAGE_RELATIONAL, relational > 0), (STAGE_LEXICAL, lexical > 0))
            if matched
        )

        hits.append(
            EvidenceHit(
                evidence_id=str(evidence["evidence_id"]),
                source_id=str(evidence["source_id"]),
                fragment_ids=tuple(str(f) for f in evidence.get("fragment_ids", [])),
                direction=str(evidence["direction"]),
                strength=str(evidence["strength"]),
                evidence_type=str(evidence["evidence_type"]),
                epistemic_status=str(evidence["epistemic_status"]),
                entity_scope=Scope.from_mapping(evidence["entity_scope"]),
                subject_entity_id=str(subject) if subject else None,
                observed_at=evidence.get("observed_at"),
                source_pointers=pointers,
                retrieval_score=score,
                retrieval_stages=stages,
                sensitivity_level=sensitivity_of(evidence),
                data_classes=data_classes_of(evidence),
            )
        )

    # Score, then strength, then id. The id is what makes the order total: two
    # items that tie on everything else must still come back the same way twice.
    hits.sort(
        key=lambda h: (
            -round(h.retrieval_score, 6),
            _STRENGTH_ORDER.get(h.strength, 9),
            h.evidence_id,
        )
    )
    hits = hits[:limit]

    absence = (
        None
        if hits
        else Absence(
            Absence.NO_EVIDENCE_FOUND,
            f"{query!r} in {guard}",
            "no evidence matched; this is not a finding that the claim is false",
        )
    )
    return EvidenceSearchResult(
        query=query,
        scope=scope,
        hits=tuple(hits),
        stages_run=tuple(stages_run),
        stages_unavailable=tuple(stages_unavailable),
        absence=absence,
    )


def _passes_filters(evidence: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key in ("direction", "strength", "evidence_type", "epistemic_status"):
        wanted = filters.get(key)
        if wanted is None:
            continue
        allowed = {wanted} if isinstance(wanted, str) else set(wanted)
        if str(evidence.get(key)) not in allowed:
            return False
    return not (filters.get("exclude_pii") and carries_pii(evidence))
