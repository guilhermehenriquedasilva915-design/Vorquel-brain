"""The storage port, and the one adapter Brain-V1-B ships.

Brain-V1-B deliberately does **not** create storage for the twelve V1 objects.
An audit of this repository found:

* ``n8n_brain`` — owned here, but it holds n8n *operational* memory
  (experiences, build runs, compiled workflow knowledge). None of it is an
  Entity, Claim, Evidence, Decision, Hypothesis, Unknown or Event in the
  contract's sense.
* ``vorquel_knowledge`` — human-reviewed semantic knowledge, but its migrations
  live in the **Vorquel-watch** repository. This repo cannot migrate it.

So there is no existing table that is semantically the right home, and creating
one here would be exactly the third parallel knowledge store the project rules
forbid without a prior proposal. Rather than invent one, retrieval is written
against the port below. Every read service in this package depends on
:class:`BrainStore` and on nothing else, so the decision about where the Brain's
own objects finally live stays open and costs one adapter when it is made.

:class:`InMemoryBrainStore` is the adapter Brain-V1-B ships. It is not a stub:
it is what the negative evals run against, and it validates everything it is
given against the published contract schemas at load time, so a fixture cannot
prove a rule by being malformed in a convenient way.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from vorquel_brain_contract import V1_OBJECTS, structural_errors

from .errors import StoreIntegrityError

#: Contract object type -> the key it is stored and fixtured under. Plural keys,
#: so a fixture file reads as a description of a world rather than of a schema.
COLLECTIONS: dict[str, str] = {
    "Entity": "entities",
    "Source": "sources",
    "SourceFragment": "fragments",
    "Claim": "claims",
    "Evidence": "evidence",
    "Hypothesis": "hypotheses",
    "Unknown": "unknowns",
    "Decision": "decisions",
    "Event": "events",
    "StateProjection": "state_projections",
}

#: Which field identifies each object. Needed because the contract names every
#: id after its own type rather than using a uniform ``id``, which is better for
#: reading a payload and worse for iterating over one.
ID_FIELDS: dict[str, str] = {
    "Entity": "entity_id",
    "Source": "source_id",
    "SourceFragment": "fragment_id",
    "Claim": "claim_id",
    "Evidence": "evidence_id",
    "Hypothesis": "hypothesis_id",
    "Unknown": "unknown_id",
    "Decision": "decision_id",
    "Event": "event_id",
    "StateProjection": "state_projection_id",
}


@runtime_checkable
class BrainStore(Protocol):
    """Read-only access to Brain objects.

    Read-only is the whole point. Brain-V1-B is a read path, and a port with no
    write method cannot grow one by accident. Canonical mutation, candidates and
    events are Brain-V1-C's problem and need their own reviewed interface.
    """

    def all_of(self, object_type: str) -> tuple[dict[str, Any], ...]:
        """Every object of one type, in a stable order."""

    def by_id(self, object_type: str, object_id: str) -> dict[str, Any] | None:
        """One object, or ``None``. No scope filtering happens here."""

    def fingerprint(self) -> str:
        """A stable hash of everything the store holds.

        ContextPack identity includes this, so the same inputs against a
        *different* world produce a different pack id instead of two different
        packs quietly sharing one.
        """


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class InMemoryBrainStore:
    """A store built from plain dicts, validated against the contract on the way in."""

    _objects: dict[str, tuple[dict[str, Any], ...]]
    _index: dict[tuple[str, str], dict[str, Any]]
    _fingerprint: str

    # -- construction -------------------------------------------------------

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, validate: bool = True) -> InMemoryBrainStore:
        """Build from ``{"entities": [...], "claims": [...], ...}``.

        Unknown top-level keys are rejected rather than ignored. A fixture with
        ``"evidences"`` in it would otherwise load cleanly, contribute nothing,
        and make a negative eval pass for the wrong reason.
        """
        known = set(COLLECTIONS.values()) | {"_comment"}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise StoreIntegrityError(
                f"unknown collection(s) in store data: {', '.join(unknown)}. "
                f"Known collections: {', '.join(sorted(COLLECTIONS.values()))}"
            )

        objects: dict[str, tuple[dict[str, Any], ...]] = {}
        index: dict[tuple[str, str], dict[str, Any]] = {}

        for object_type, key in COLLECTIONS.items():
            id_field = ID_FIELDS[object_type]
            items = raw.get(key) or []
            if not isinstance(items, list):
                raise StoreIntegrityError(f"{key} must be a list, got {type(items).__name__}")

            for position, item in enumerate(items):
                if not isinstance(item, dict):
                    raise StoreIntegrityError(f"{key}[{position}] is not an object")
                if validate:
                    errors = structural_errors(item, object_type)
                    if errors:
                        raise StoreIntegrityError(
                            f"{key}[{position}] is not a valid {object_type}: "
                            + "; ".join(errors)
                        )
                object_id = item.get(id_field)
                if not isinstance(object_id, str) or not object_id:
                    raise StoreIntegrityError(f"{key}[{position}] has no {id_field}")
                if (object_type, object_id) in index:
                    raise StoreIntegrityError(f"duplicate {object_type} {object_id!r}")
                index[(object_type, object_id)] = item

            # Sorted by id at load time so every downstream iteration is stable
            # without each call site having to remember to sort.
            objects[object_type] = tuple(sorted(items, key=lambda o: o[id_field]))

        fingerprint = hashlib.sha256(
            _canonical({k: list(v) for k, v in sorted(objects.items())}).encode("utf-8")
        ).hexdigest()

        return cls(_objects=objects, _index=index, _fingerprint=fingerprint)

    @classmethod
    def from_json(cls, path: str | Path, *, validate: bool = True) -> InMemoryBrainStore:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(payload, validate=validate)

    @classmethod
    def empty(cls) -> InMemoryBrainStore:
        return cls.from_mapping({})

    # -- BrainStore ---------------------------------------------------------

    def all_of(self, object_type: str) -> tuple[dict[str, Any], ...]:
        if object_type not in V1_OBJECTS:
            raise KeyError(f"not a V1 object type: {object_type!r}")
        return self._objects.get(object_type, ())

    def by_id(self, object_type: str, object_id: str) -> dict[str, Any] | None:
        return self._index.get((object_type, object_id))

    def fingerprint(self) -> str:
        return self._fingerprint
