"""The single path every adapter's output takes before it can be a candidate.

Adapters differ in how they open a thing and how they address a position inside
it. They must not differ in whether a secret gets stored, whether PII is
minimised, or whether source text is treated as a command. Those three
decisions happen here, once, for every source kind.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .model import Candidate, LearnBatch, Refusal, SourceRef
from .policy import SecretDetected, minimise
from .untrusted import detect_instruction_attempts

# Below this, an "excerpt" is a fragment with no standalone meaning: a page
# number, a heading with an empty body, a blank cell.
MIN_UNIT_CHARS = 40


@dataclass(frozen=True)
class RawUnit:
    """What an adapter produces: text plus where inside the source it lives."""

    title: str
    text: str
    locator_kind: str
    locator: dict[str, Any] = field(default_factory=dict)
    knowledge_type: str = "CONCEPT"
    epistemic_status: str = "DECLARADO"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def to_batch(
    source: SourceRef,
    units: Iterable[RawUnit],
    declared_classification: str | None = None,
) -> LearnBatch:
    """Apply data policy and the untrusted boundary to every extracted unit.

    A unit carrying a credential is refused and recorded in `refused`; it does
    not silently vanish, and its value is never copied into the refusal. A unit
    carrying PII is minimised and kept, with the batch's classification widened
    accordingly.
    """
    classification = declared_classification or source.data_classification
    candidates: list[Candidate] = []
    refused: list[Refusal] = []
    seen: set[str] = set()

    for unit in units:
        text = unit.text.strip()
        if len(text) < MIN_UNIT_CHARS:
            continue

        try:
            sanitised = minimise(text, classification)
        except SecretDetected as exc:
            refused.append(
                Refusal(
                    reason=(
                        "trecho descartado: continha material de credencial, "
                        "que nunca vira conhecimento"
                    ),
                    rule=exc.rule,
                    locator_kind=unit.locator_kind,
                    locator=dict(unit.locator),
                )
            )
            continue

        candidate = Candidate(
            title=_truncate(unit.title.strip() or "(sem titulo)", 300),
            summary=_truncate(sanitised.text, 12000),
            knowledge_type=unit.knowledge_type,
            epistemic_status=unit.epistemic_status,
            locator_kind=unit.locator_kind,
            locator=dict(unit.locator),
            data_classification=sanitised.data_classification,
            instruction_attempts=detect_instruction_attempts(text),
            redactions=sanitised.redactions,
        )

        # The same excerpt cited twice from the same place is one candidate.
        if candidate.content_hash in seen:
            continue
        seen.add(candidate.content_hash)
        candidates.append(candidate)

    return LearnBatch(source=source, candidates=tuple(candidates), refused=tuple(refused))
