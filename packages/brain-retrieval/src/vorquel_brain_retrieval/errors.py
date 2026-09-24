"""Failures that must not be silent, and absences that must not be invented.

Two distinct things live here and they are deliberately not the same type.

An **error** is a refusal: the read cannot be served under the rules, and the
caller has to know rather than receive something plausible. It is raised.

An **absence** is an answer: the read ran, the rules held, and there was nothing
there. It is returned. ``NO_EVIDENCE_FOUND`` is an absence, and the single most
important rule in this package is that it never becomes ``False`` — a gap in the
record is not a negative fact about the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vorquel_brain_contract import NO_EVIDENCE_FOUND

__all__ = [
    "NO_EVIDENCE_FOUND",
    "Absence",
    "AmbiguousEntityError",
    "BudgetTooSmallError",
    "BrainRetrievalError",
    "StoreIntegrityError",
]


class BrainRetrievalError(Exception):
    """Base class. Every subclass carries a stable ``code`` a caller can branch on."""

    code = "BRAIN_RETRIEVAL_ERROR"


class StoreIntegrityError(BrainRetrievalError):
    """The store handed back something the contract says cannot exist.

    Raised at load time rather than at read time. A store that holds an invalid
    object will eventually serve it, and finding out then means the bad data has
    already reached a caller.
    """

    code = "STORE_INTEGRITY"


class AmbiguousEntityError(BrainRetrievalError):
    """A query matched more than one entity equally well.

    Raised by callers that require a single entity. ``resolve_entity`` itself
    does not raise: it returns every candidate with ``ambiguity=True``, because
    reporting the ambiguity is more useful than hiding it. What is forbidden is
    picking one silently.
    """

    code = "AMBIGUOUS_ENTITY"

    def __init__(self, query: str, entity_ids: tuple[str, ...]) -> None:
        super().__init__(
            f"{query!r} matched {len(entity_ids)} entities equally well: "
            f"{', '.join(entity_ids)}. Disambiguate before reading."
        )
        self.query = query
        self.entity_ids = entity_ids


class BudgetTooSmallError(BrainRetrievalError):
    """The budget cannot hold even the pack's non-droppable core.

    The alternative — returning a pack with the traceability trimmed out of it —
    would hand the caller something that looks complete and is not. There is no
    safe degraded ContextPack, so there is no degraded return value.
    """

    code = "BUDGET_TOO_SMALL"

    def __init__(self, requested: int, minimum_required: int, missing: tuple[str, ...]) -> None:
        super().__init__(
            f"BUDGET_TOO_SMALL: {requested} tokens requested, at least "
            f"{minimum_required} needed for a pack that keeps "
            f"{', '.join(missing)}. No pack was generated."
        )
        self.requested = requested
        self.minimum_required = minimum_required
        self.missing = missing


@dataclass(frozen=True)
class Absence:
    """A recorded nothing.

    ``kind`` says which nothing it is, because "this entity does not exist",
    "this entity is not yours to see" and "this entity exists and has no state
    yet" are three different answers and collapsing them loses the difference.

    Note that ``NOT_FOUND`` covers both a genuine miss and an object the guard
    refused. That is intentional: a distinguishable "exists but denied" tells a
    caller that an id it guessed is real, which is itself a leak.
    """

    kind: str
    subject: str
    note: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    NOT_FOUND = "NOT_FOUND"
    NO_STATE_RECORDED = "NO_STATE_RECORDED"
    NO_EVIDENCE_FOUND = NO_EVIDENCE_FOUND
    NO_CHANGES_RECORDED = "NO_CHANGES_RECORDED"

    def __bool__(self) -> bool:
        """An absence is falsy so ``if result:`` reads naturally.

        It is emphatically **not** ``False``: ``bool(absence)`` is a control-flow
        convenience, and anything serialising an absence must serialise the
        object, never the boolean. ``check_no_evidence_not_false`` in the
        contract is what catches the mistake if it is made anyway.
        """
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "absence": self.kind,
            "subject": self.subject,
            "note": self.note,
            **({"details": self.details} if self.details else {}),
        }

    def __str__(self) -> str:
        return f"{self.kind}({self.subject}){': ' + self.note if self.note else ''}"
