"""Sensitivity, data classes and time — the rules applied to every object read.

Three things live here because every read service needs all three and none of
them should be reimplemented per call site.

**SECRET is excluded, not redacted.** A redacted SECRET is still a statement
that a secret exists at that point in the record, and the contract's rule is
absolute: ``SECRET`` never reaches a ContextPack, at any budget, in any mode.

**PII is orthogonal.** Carrying ``PII`` does not raise an object's tier and does
not lower it. It obliges minimisation, which is a different duty from exclusion,
so ``PII`` items stay retrievable and are marked rather than dropped.

**Time is read, never invented.** Nothing here calls ``now()``. Freshness and
``as_of`` are derived from the timestamps the objects themselves carry, which is
what makes every read in this package reproducible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from vorquel_brain_contract import SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK, SENSITIVITY_LEVELS

#: Least to most restricted. Used to compute a pack's tier as the maximum of
#: what it carries, never as a comparison that could let a lower tier win.
_TIER_ORDER = {level: index for index, level in enumerate(SENSITIVITY_LEVELS)}

#: How old a derived picture may be before it is reported STALE. A default, not
#: a truth: callers with a faster-moving scope should pass their own.
DEFAULT_STALENESS_HORIZON = timedelta(days=90)

#: Every timestamp field the contract objects use, in the order a reader would
#: prefer them. ``occurred_at`` beats ``recorded_at`` on purpose: when something
#: happened is the fact, when it was written down is bookkeeping.
_TIME_FIELDS = (
    "observed_at",
    "occurred_at",
    "last_updated_at",
    "effective_from",
    "created_at",
    "recorded_at",
    "captured_at",
    "ingested_at",
    "as_of",
)


def sensitivity_of(obj: dict[str, Any]) -> str:
    """An object's tier, however it spells it.

    Objects carry sensitivity two ways: ``Source`` has flat ``sensitivity_level``
    and ``data_classes`` fields, everything else nests them under
    ``sensitivity``. An object with neither is treated as ``INTERNAL``: the
    absence of a label is not a claim that something is public.
    """
    nested = obj.get("sensitivity")
    if isinstance(nested, dict) and nested.get("sensitivity_level"):
        return str(nested["sensitivity_level"])
    level = obj.get("sensitivity_level")
    return str(level) if level else "INTERNAL"


def data_classes_of(obj: dict[str, Any]) -> tuple[str, ...]:
    nested = obj.get("sensitivity")
    if isinstance(nested, dict) and isinstance(nested.get("data_classes"), list):
        return tuple(sorted(str(c) for c in nested["data_classes"]))
    flat = obj.get("data_classes")
    return tuple(sorted(str(c) for c in flat)) if isinstance(flat, list) else ()


def is_secret(obj: dict[str, Any]) -> bool:
    return sensitivity_of(obj) == SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK


def carries_pii(obj: dict[str, Any]) -> bool:
    return "PII" in data_classes_of(obj)


def max_sensitivity(levels: object) -> str:
    """The most restricted tier among several. ``PUBLIC`` when there are none."""
    known = [level for level in levels if level in _TIER_ORDER]  # type: ignore[union-attr]
    if not known:
        return "PUBLIC"
    return max(known, key=lambda level: _TIER_ORDER[level])


def parse_timestamp(raw: object) -> datetime | None:
    """Parse an RFC 3339 timestamp, returning ``None`` rather than guessing.

    A naive timestamp is read as UTC. That is an assumption, and it is made in
    exactly one place so it can be found and changed, rather than made
    differently in five.
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def latest_timestamp(objects: object) -> datetime | None:
    """The newest moment anything in a collection knows about."""
    newest: datetime | None = None
    for obj in objects:  # type: ignore[union-attr]
        for field in _TIME_FIELDS:
            moment = parse_timestamp(obj.get(field))
            if moment is not None and (newest is None or moment > newest):
                newest = moment
    return newest


def format_timestamp(moment: datetime) -> str:
    """Back to the contract's wire form: UTC, ``Z``-suffixed, second precision."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def freshness_for(
    as_of: datetime | None,
    newest_contribution: datetime | None,
    horizon: timedelta = DEFAULT_STALENESS_HORIZON,
) -> str:
    """``FRESH``, ``STALE`` or ``UNKNOWN_FRESHNESS``.

    ``UNKNOWN_FRESHNESS`` is a real answer, returned whenever there is nothing to
    measure against. Defaulting to ``FRESH`` would be a claim nobody made.
    """
    if as_of is None or newest_contribution is None:
        return "UNKNOWN_FRESHNESS"
    return "STALE" if as_of - newest_contribution > horizon else "FRESH"
