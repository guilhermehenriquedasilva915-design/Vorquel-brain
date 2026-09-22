"""Loading and structural validation of the published schema files.

The JSON Schema files are the contract's durable artifact — they outlive this
Python package and can be consumed by anything. This module is the thin layer
that finds them, resolves the ``$ref``s between them, and checks an object's
*shape*.

Shape is all it checks. Everything that needs to compare two objects, or reason
about what a status entitles a payload to, lives in :mod:`.validators`, because
JSON Schema cannot express it and pretending otherwise would put half the
contract somewhere it cannot be enforced.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_ROOT = Path(__file__).parent / "schemas"
SHARED_DIR = SCHEMA_ROOT / "shared"
V1_DIR = SCHEMA_ROOT / "v1"

BASE_URI = "https://schemas.vorquel/brain"

#: Object type -> schema file stem. The twelve objects the V1 contract defines.
V1_OBJECTS: dict[str, str] = {
    "Entity": "entity",
    "Source": "source",
    "SourceFragment": "source_fragment",
    "Claim": "claim",
    "Evidence": "evidence",
    "Hypothesis": "hypothesis",
    "Unknown": "unknown",
    "Decision": "decision",
    "Candidate": "candidate",
    "Event": "event",
    "StateProjection": "state_projection",
    "ContextPack": "context_pack",
}


@lru_cache(maxsize=1)
def load_all_schemas() -> dict[str, dict[str, Any]]:
    """Every schema in the contract, keyed by its ``$id``."""
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(SHARED_DIR.glob("*.json")) + sorted(V1_DIR.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        schemas[body["$id"]] = body
    return schemas


def schema_for(object_type: str) -> dict[str, Any]:
    """The V1 schema for one object type."""
    if object_type not in V1_OBJECTS:
        raise KeyError(f"no V1 schema for object_type {object_type!r}")
    return load_all_schemas()[f"{BASE_URI}/v1/{V1_OBJECTS[object_type]}.schema.json"]


def _registry():
    """A ``referencing`` registry holding every schema, so ``$ref`` resolves offline.

    Built lazily: ``jsonschema`` is a test-time dependency, and importing this
    module must not require it.
    """
    from referencing import Registry, Resource

    resources = [
        (uri, Resource.from_contents(body)) for uri, body in load_all_schemas().items()
    ]
    return Registry().with_resources(resources)


def structural_errors(instance: dict[str, Any], object_type: str | None = None) -> list[str]:
    """Schema-validate one object and return the messages, empty when it conforms.

    *object_type* defaults to the instance's own ``object_type``, so a payload
    that lies about what it is fails against the schema it claims.
    """
    from jsonschema import Draft202012Validator

    declared = object_type or instance.get("object_type")
    if declared not in V1_OBJECTS:
        return [f"unknown or missing object_type: {declared!r}"]

    validator = Draft202012Validator(schema_for(declared), registry=_registry())
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    ]


def is_structurally_valid(instance: dict[str, Any], object_type: str | None = None) -> bool:
    return not structural_errors(instance, object_type)
