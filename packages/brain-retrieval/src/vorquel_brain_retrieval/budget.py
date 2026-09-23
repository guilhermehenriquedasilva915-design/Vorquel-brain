"""Token budgeting: what a budget may take away, and what it may never touch.

The principle is one sentence. **A budget cuts content; it never cuts
traceability.**

Everything in :data:`NON_DROPPABLE` stays in the pack at any budget, because
without it the pack stops being checkable: you cannot tell which pack you are
holding, what it was for, whose it is, what constrains it, what contradicts it,
or where any surviving statement came from. A pack that has been trimmed down to
plausible-looking prose with the pointers removed is worse than no pack, because
it still looks complete.

Everything in :data:`DROP_ORDER` goes, in that order, cheapest first. And when
even the non-droppable core will not fit, the answer is
:class:`~.errors.BudgetTooSmallError` rather than a smaller pack. There is no
safe mutilated ContextPack, so none is offered.

Token counts here are a deterministic **estimate**, not a tokenizer. A real
tokenizer would tie the Brain to one model's vocabulary and make the same pack
count differently against a different runtime, which is the coupling this whole
project is arranged to avoid. The estimate is intentionally slightly
pessimistic; ``TOKENS_PER_CHAR`` documents the ratio in one place.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

#: Characters per token. Four is the usual rough figure for English and
#: Portuguese prose alike. Being wrong here makes packs smaller than necessary,
#: never larger than allowed.
TOKENS_PER_CHAR = 4

#: Flat cost charged per structural element, so a list of a hundred short ids is
#: not counted as nearly free.
STRUCTURE_COST = 2

#: Parts of a pack a budget may never remove. Each is here because losing it
#: breaks a different kind of checking.
NON_DROPPABLE: tuple[str, ...] = (
    "context_pack_id",
    "version",
    "contract_version",
    "object_type",
    "objective",
    "mode",
    "scope",
    "entity_ids",
    "generated_at",
    "token_budget",
    "sensitivity_level",
    "data_classes",
    "constraints",
    "provenance_summary",
    "gaps",
    "state_projection_ids",
    "freshness_status",
)

#: What gets dropped, and in what order. Cheapest loss first: a verbose summary
#: is a convenience, a weak piece of evidence is a data point, and by the time
#: the list is exhausted only the core is left.
DROP_ORDER: tuple[str, ...] = (
    "VERBOSE_SUMMARY",
    "LOW_RELEVANCE_ARTIFACTS",
    "OLDER_EVENTS",
    "WEAKER_EVIDENCE",
    "SECONDARY_PROCEDURAL_REFS",
)


def estimate_tokens(payload: Any) -> int:
    """A deterministic size estimate for any JSON-serialisable value.

    Deterministic matters more than accurate. The same pack must cost the same
    number twice, or reproducibility tests measure noise.
    """
    if payload is None:
        return 0
    if isinstance(payload, str):
        return math.ceil(len(payload) / TOKENS_PER_CHAR)
    if isinstance(payload, bool):
        return 1
    if isinstance(payload, (int, float)):
        return 1
    if isinstance(payload, (list, tuple)):
        return STRUCTURE_COST + sum(estimate_tokens(item) for item in payload)
    if isinstance(payload, dict):
        return STRUCTURE_COST + sum(
            estimate_tokens(key) + estimate_tokens(value) for key, value in payload.items()
        )
    return estimate_tokens(json.dumps(payload, sort_keys=True, ensure_ascii=False))


@dataclass
class TrimLog:
    """What the budget took, said plainly enough to put in the pack's ``gaps``."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, step: str, removed: list[str], field_name: str) -> None:
        if removed:
            self.entries.append(
                {"step": step, "field": field_name, "removed": sorted(removed)}
            )

    def as_gap_lines(self) -> list[str]:
        return [
            f"trimmed for token budget ({entry['step']}): "
            f"{len(entry['removed'])} item(s) removed from {entry['field']} "
            f"[{', '.join(entry['removed'])}]"
            for entry in self.entries
        ]

    def removed_ids(self) -> set[str]:
        return {item for entry in self.entries for item in entry["removed"]}

    def __bool__(self) -> bool:
        return bool(self.entries)


def core_of(pack: dict[str, Any]) -> dict[str, Any]:
    """The part of a pack that survives any budget."""
    return {key: value for key, value in pack.items() if key in NON_DROPPABLE}


def minimum_tokens(pack: dict[str, Any]) -> int:
    """What the non-droppable core costs. Below this, no pack is issued."""
    return estimate_tokens(core_of(pack))
