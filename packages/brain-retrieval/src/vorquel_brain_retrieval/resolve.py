"""``resolve_entity`` — which entity is this string?

Deterministic and structured. Canonical names, aliases and ids are matched by
normalised equality and by containment; there is no edit-distance scoring and no
embedding. That is not a placeholder for something cleverer later. Fuzzy
matching across a scope boundary is precisely how one client's entity list leaks
out of a near-miss, so the scope guard runs *first* and only entities already
visible are matched at all.

Two things this function will not do:

* **Return details of an entity the caller cannot see.** Out-of-scope entities
  are filtered before matching, so they cannot appear as candidates, cannot
  influence ambiguity and cannot be confirmed to exist.
* **Choose.** When two entities match equally well, both come back with
  ``ambiguity=True`` and ``resolved_entity_id`` is ``None``. Picking the first
  one would be the same bug as picking at random, only harder to notice.

``match_score`` is a **retrieval** number: how well a string matched a name. It
is not confidence that anything is true. Epistemic status lives on claims and
evidence and never on a match.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .errors import AmbiguousEntityError
from .policy import is_secret
from .scope import Scope, ScopeGuard
from .store import BrainStore

#: Match kinds, strongest first. The score is a property of *how* a string
#: matched, not of the entity, so the same kind always scores the same and two
#: runs cannot order candidates differently.
MATCH_KINDS: tuple[tuple[str, float], ...] = (
    ("EXACT_ID", 1.0),
    ("EXACT_CANONICAL_NAME", 0.98),
    ("EXACT_ALIAS", 0.92),
    ("NORMALIZED_CANONICAL_NAME", 0.88),
    ("NORMALIZED_ALIAS", 0.82),
    ("CANONICAL_NAME_PREFIX", 0.60),
    ("ALIAS_PREFIX", 0.55),
    ("CANONICAL_NAME_CONTAINS", 0.40),
)

_SCORES = dict(MATCH_KINDS)
_RANK = {kind: index for index, (kind, _) in enumerate(MATCH_KINDS)}

#: Below this, a match is too weak to be offered at all. A long list of weak
#: candidates is not disambiguation, it is a directory listing of the scope.
MIN_SCORE = 0.40

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Casefold, strip accents, collapse punctuation to single spaces.

    ``"Chaves & Hugo"``, ``"chaves e hugo"`` and ``"CHAVES-HUGO"`` are the same
    string for matching purposes and different strings everywhere else.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", stripped.casefold()).strip()


@dataclass(frozen=True)
class EntityMatch:
    """One candidate. Carries only what disambiguation needs."""

    entity_id: str
    canonical_name: str
    entity_type: str
    scope: Scope
    match_kind: str
    #: Technical resolution score in [0, 1]. **Not** epistemic confidence.
    match_score: float
    matched_on: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "scope": self.scope.as_mapping(),
            "match_kind": self.match_kind,
            "match_score": self.match_score,
            "matched_on": self.matched_on,
        }


@dataclass(frozen=True)
class EntityResolution:
    query: str
    scope: Scope
    matches: tuple[EntityMatch, ...]
    ambiguity: bool
    resolved_entity_id: str | None

    def require_one(self) -> str:
        """The single resolved entity, or a refusal.

        For callers that genuinely cannot proceed without one entity. It raises
        instead of choosing, which is the only honest option left at that point.
        """
        if self.resolved_entity_id is not None:
            return self.resolved_entity_id
        raise AmbiguousEntityError(self.query, tuple(m.entity_id for m in self.matches))

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope.as_mapping(),
            "matches": [m.as_dict() for m in self.matches],
            "ambiguity": self.ambiguity,
            "resolved_entity_id": self.resolved_entity_id,
        }


def _best_match(
    entity: dict[str, Any], query: str, normalized_query: str
) -> tuple[str, str] | None:
    """The strongest ``(match_kind, matched_on)`` for one entity, or ``None``."""
    canonical = str(entity.get("canonical_name", ""))
    aliases = [str(a) for a in entity.get("aliases", [])]
    entity_id = str(entity.get("entity_id", ""))

    if entity_id == query:
        return ("EXACT_ID", entity_id)
    if canonical == query:
        return ("EXACT_CANONICAL_NAME", canonical)
    for alias in sorted(aliases):
        if alias == query:
            return ("EXACT_ALIAS", alias)

    if not normalized_query:
        return None

    if normalize(canonical) == normalized_query:
        return ("NORMALIZED_CANONICAL_NAME", canonical)
    for alias in sorted(aliases):
        if normalize(alias) == normalized_query:
            return ("NORMALIZED_ALIAS", alias)

    normalized_canonical = normalize(canonical)
    if normalized_canonical.startswith(normalized_query):
        return ("CANONICAL_NAME_PREFIX", canonical)
    for alias in sorted(aliases):
        if normalize(alias).startswith(normalized_query):
            return ("ALIAS_PREFIX", alias)

    # Containment is the weakest thing offered, and only whole-token
    # containment. Substring matching would make "a" a candidate for everything.
    query_tokens = normalized_query.split()
    if query_tokens and set(query_tokens) <= set(normalized_canonical.split()):
        return ("CANONICAL_NAME_CONTAINS", canonical)
    return None


def resolve_entity(
    store: BrainStore,
    query: str,
    scope: Scope,
    *,
    include_global: bool = True,
    limit: int = 10,
) -> EntityResolution:
    """Resolve *query* to entities visible from *scope*.

    Ambiguity is decided on the strongest tier only. An exact canonical-name hit
    alongside a weak prefix hit is not ambiguous — one answer is plainly better.
    Two exact alias hits are ambiguous, and stay that way.
    """
    guard = ScopeGuard(requested=scope, include_global=include_global)
    normalized_query = normalize(query)

    matches: list[EntityMatch] = []
    for entity in store.all_of("Entity"):
        if not guard.admits(entity):
            continue
        # A SECRET entity is not describable to a caller, so it is not a
        # candidate. It is skipped silently: reporting "there is one more match
        # you may not see" is itself the disclosure.
        if is_secret(entity):
            continue
        found = _best_match(entity, query, normalized_query)
        if found is None:
            continue
        kind, matched_on = found
        score = _SCORES[kind]
        if score < MIN_SCORE:
            continue
        matches.append(
            EntityMatch(
                entity_id=str(entity["entity_id"]),
                canonical_name=str(entity["canonical_name"]),
                entity_type=str(entity["entity_type"]),
                scope=Scope.from_mapping(entity["scope"]),
                match_kind=kind,
                match_score=score,
                matched_on=matched_on,
            )
        )

    # Strongest kind first, then by id. The id tie-break exists so two entities
    # matching identically come back in the same order on every run, which is
    # what lets a ContextPack built on top of this be reproducible.
    matches.sort(key=lambda m: (_RANK[m.match_kind], m.entity_id))
    matches = matches[:limit]

    if not matches:
        return EntityResolution(query, scope, (), ambiguity=False, resolved_entity_id=None)

    best_kind = matches[0].match_kind
    top = [m for m in matches if m.match_kind == best_kind]
    ambiguity = len(top) > 1

    return EntityResolution(
        query=query,
        scope=scope,
        matches=tuple(matches),
        ambiguity=ambiguity,
        resolved_entity_id=None if ambiguity else top[0].entity_id,
    )
