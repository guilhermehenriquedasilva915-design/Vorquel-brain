"""Enum parity across the three layers that can disagree.

A closed vocabulary is defined in three places, and they drift silently:

* **Python** — ``vorquel_brain_contract.enums``;
* **JSON Schema** — the published ``*.schema.json`` files;
* **storage** — ``CHECK`` constraints in ``supabase/migrations``.

Brain-V1-A found this by hand — a 27-check scratch audit that lived in a chat
session and would have been gone by the next one. This module is that audit
turned into something CI runs, so a fourth divergence cannot be discovered the
same way the first four were.

One rule about storage comparisons: **only compare what storage actually
defines.** Storage constrains ``scope_type`` and ``epistemic_status`` and knows
nothing about freshness, sensitivity or hypothesis status. Asserting parity for
a vocabulary storage has never heard of would fail permanently and teach
everyone to ignore the test.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vorquel_brain_contract import (
    CLAIM_STATUSES,
    CONTEXT_PACK_MODES,
    DATA_CLASSES,
    DECISION_STATUSES,
    ENTITY_TYPES,
    EPISTEMIC_STATUSES,
    EVIDENCE_DIRECTIONS,
    FRESHNESS_STATUSES,
    HYPOTHESIS_STATUSES,
    SCOPE_TYPES,
    SENSITIVITY_LEVELS,
    UNKNOWN_STATUSES,
    VERIFICATION_STATES,
    load_all_schemas,
)


class ParityError(AssertionError):
    """A vocabulary disagrees between layers. Always fatal in CI."""


@dataclass(frozen=True)
class Divergence:
    vocabulary: str
    left: str
    right: str
    only_in_left: tuple[str, ...]
    only_in_right: tuple[str, ...]

    def __str__(self) -> str:
        parts = [f"{self.vocabulary}: {self.left} vs {self.right}"]
        if self.only_in_left:
            parts.append(f"only in {self.left}: {', '.join(self.only_in_left)}")
        if self.only_in_right:
            parts.append(f"only in {self.right}: {', '.join(self.only_in_right)}")
        return " | ".join(parts)


#: Python vocabulary -> where it appears in the schemas, as
#: ``(schema stem, JSON pointer-ish path to the enum)``. Only vocabularies with
#: a schema home are listed; the rest are Python-only by design.
SCHEMA_LOCATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "SCOPE_TYPES": ("shared/scope", ("properties", "scope_type", "enum")),
    "SENSITIVITY_LEVELS": ("shared/sensitivity", ("properties", "sensitivity_level", "enum")),
    "DATA_CLASSES": ("shared/sensitivity", ("properties", "data_classes", "items", "enum")),
    "EPISTEMIC_STATUSES": ("v1/claim", ("properties", "epistemic_status", "enum")),
    "VERIFICATION_STATES": ("v1/claim", ("properties", "verification_state", "enum")),
    "CLAIM_STATUSES": ("v1/claim", ("properties", "status", "enum")),
    "ENTITY_TYPES": ("v1/entity", ("properties", "entity_type", "enum")),
    "EVIDENCE_DIRECTIONS": ("v1/evidence", ("properties", "direction", "enum")),
    "HYPOTHESIS_STATUSES": ("v1/hypothesis", ("properties", "status", "enum")),
    "UNKNOWN_STATUSES": ("v1/unknown", ("properties", "status", "enum")),
    "DECISION_STATUSES": ("v1/decision", ("properties", "status", "enum")),
    "CONTEXT_PACK_MODES": ("v1/context_pack", ("properties", "mode", "enum")),
    "FRESHNESS_STATUSES": (
        "v1/state_projection",
        ("properties", "freshness_status", "enum"),
    ),
}

PYTHON_VOCABULARIES: dict[str, tuple[str, ...]] = {
    "SCOPE_TYPES": SCOPE_TYPES,
    "SENSITIVITY_LEVELS": SENSITIVITY_LEVELS,
    "DATA_CLASSES": DATA_CLASSES,
    "EPISTEMIC_STATUSES": EPISTEMIC_STATUSES,
    "VERIFICATION_STATES": VERIFICATION_STATES,
    "CLAIM_STATUSES": CLAIM_STATUSES,
    "ENTITY_TYPES": ENTITY_TYPES,
    "EVIDENCE_DIRECTIONS": EVIDENCE_DIRECTIONS,
    "HYPOTHESIS_STATUSES": HYPOTHESIS_STATUSES,
    "UNKNOWN_STATUSES": UNKNOWN_STATUSES,
    "DECISION_STATUSES": DECISION_STATUSES,
    "CONTEXT_PACK_MODES": CONTEXT_PACK_MODES,
    "FRESHNESS_STATUSES": FRESHNESS_STATUSES,
}

#: Vocabulary -> the storage column that constrains it. Two entries, and two is
#: the correct number: these are the only closed vocabularies the live schema
#: has an opinion about.
STORAGE_COLUMNS: dict[str, str] = {
    "SCOPE_TYPES": "scope_type",
    "EPISTEMIC_STATUSES": "epistemic_status",
}

_BASE_URI = "https://schemas.vorquel/brain"


def schema_enum(stem: str, path: tuple[str, ...]) -> tuple[str, ...]:
    schema: Any = load_all_schemas()[f"{_BASE_URI}/{stem}.schema.json"]
    for key in path:
        schema = schema[key]
    return tuple(schema)


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up for the directory that holds ``supabase/migrations``.

    Fails loudly rather than skipping. A parity test that silently passes when
    it cannot find the migrations is a test that passes on a broken checkout.
    """
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "supabase" / "migrations").is_dir():
            return candidate
    raise ParityError(
        f"could not find supabase/migrations above {current}; "
        "storage parity cannot be checked from here"
    )


def storage_enum(column: str, repo_root: Path | None = None) -> tuple[str, ...]:
    """The values a column's latest ``CHECK`` constraint admits.

    Migrations are read in filename order and the last definition wins, which is
    how the database itself ends up: a later migration that widens a constraint
    replaces the earlier one.
    """
    root = repo_root or find_repo_root()
    pattern = re.compile(
        rf"check\s*\(\s*{re.escape(column)}\s+in\s*\((?P<values>[^)]*)\)",
        re.IGNORECASE | re.DOTALL,
    )
    latest: tuple[str, ...] | None = None
    for path in sorted((root / "supabase" / "migrations").glob("*.sql")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            latest = tuple(
                value.strip().strip("'") for value in match.group("values").split(",")
            )
    if latest is None:
        raise ParityError(f"no CHECK constraint for {column!r} found in any migration")
    return latest


def check_parity(repo_root: Path | None = None) -> list[Divergence]:
    """Every divergence between Python, the schemas and storage. Empty is passing."""
    divergences: list[Divergence] = []

    for name, values in PYTHON_VOCABULARIES.items():
        location = SCHEMA_LOCATIONS.get(name)
        if location is None:  # pragma: no cover - every vocabulary has one today
            continue
        stem, path = location
        in_schema = schema_enum(stem, path)
        divergences.extend(_compare(name, "python", values, f"schema:{stem}", in_schema))

    for name, column in STORAGE_COLUMNS.items():
        in_storage = storage_enum(column, repo_root)
        divergences.extend(
            _compare(name, "python", PYTHON_VOCABULARIES[name], f"storage:{column}", in_storage)
        )

    return divergences


def _compare(
    vocabulary: str,
    left_name: str,
    left: tuple[str, ...],
    right_name: str,
    right: tuple[str, ...],
) -> list[Divergence]:
    only_left = tuple(sorted(set(left) - set(right)))
    only_right = tuple(sorted(set(right) - set(left)))
    if not only_left and not only_right:
        return []
    return [Divergence(vocabulary, left_name, right_name, only_left, only_right)]


def assert_parity(repo_root: Path | None = None) -> None:
    divergences = check_parity(repo_root)
    if divergences:
        raise ParityError(
            "enum parity broken across layers:\n  " + "\n  ".join(str(d) for d in divergences)
        )


def parity_report(repo_root: Path | None = None) -> dict[str, Any]:
    """A machine-readable summary, for the doctor and for CI output."""
    divergences = check_parity(repo_root)
    return {
        "checked_python_vs_schema": sorted(SCHEMA_LOCATIONS),
        "checked_python_vs_storage": sorted(STORAGE_COLUMNS),
        "divergences": [
            {
                "vocabulary": d.vocabulary,
                "left": d.left,
                "right": d.right,
                "only_in_left": list(d.only_in_left),
                "only_in_right": list(d.only_in_right),
            }
            for d in divergences
        ],
        "status": "OK" if not divergences else "DRIFT",
    }


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(parity_report(), indent=2, sort_keys=True))
