"""The credential auto-assignment guard.

``create_workflow_from_code`` and ``update_workflow`` can bind a credential to a
node, and ``update_workflow``'s ``operations[].type`` enum includes
``setNodeCredential``. The danger is therefore *argument-level*: permission to
call ``update_workflow`` by name says nothing about whether a given call binds a
credential. Name-level permission is not sufficient, so every create or update
is followed by a read-back that this module judges.

Three rules shape the implementation:

1. **Compare ids, aliases and types only.** Never a value. The guard refuses a
   read-back that even carries a value-shaped field, because a payload holding a
   secret is itself the incident — see :func:`scan_for_credential_values`.
2. **The DEV allowlist starts empty.** The instance was provisioned with
   ``No credentials found with specified filters``, so on this instance *any*
   binding is an anomaly. An empty allowlist is the strict case, not the
   unconfigured case, and the guard never silently widens it.
3. **An anomaly stops the run.** The verdict carries the required action:
   do not test, and revert to the snapshot.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

CLEAN = "CLEAN"
ANOMALY = "ANOMALY"

#: What to do next. The pipeline must not invent a softer response.
ACTION_PROCEED = "PROCEED"
ACTION_STOP_AND_REVERT = "STOP_AND_REVERT"

#: The only fields we are allowed to look at on a binding.
COMPARABLE_FIELDS = ("id", "alias", "type")

#: Field names on a read-back that would carry a secret rather than an
#: identifier. Their mere presence is a violation.
VALUE_FIELD_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|apikey|authorization|cookie"
    r"|private[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token"
    r"|credential_data|credential_payload|^data$|^value$)",
    re.IGNORECASE,
)


class CredentialValueLeak(Exception):
    """Raised when a read-back carries a credential value rather than an id.

    This is not a validation nicety. If the guard ever receives a payload
    containing a secret, the safe response is to fail loudly before that payload
    can be logged, diffed or written into a report.
    """


@dataclass(frozen=True)
class CredentialBinding:
    """One credential bound to one node, reduced to identifiers."""

    node_name: str
    credential_id: str | None
    credential_alias: str | None
    credential_type: str | None

    def identity(self) -> tuple[str | None, str | None, str | None]:
        return (self.credential_id, self.credential_alias, self.credential_type)

    def describe(self) -> str:
        parts = [
            f"{label}={value!r}"
            for label, value in zip(COMPARABLE_FIELDS, self.identity(), strict=True)
            if value is not None
        ]
        return f"node {self.node_name!r}: " + (", ".join(parts) or "no identifiers reported")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AllowedCredential:
    """One entry in the DEV allowlist, matched on identifiers only."""

    credential_id: str | None = None
    credential_alias: str | None = None
    credential_type: str | None = None

    def matches(self, binding: CredentialBinding) -> bool:
        """True when every field this entry constrains equals the binding's.

        An entry that constrains nothing matches nothing: an empty allowlist
        entry must not become a wildcard.
        """
        constraints = [
            (self.credential_id, binding.credential_id),
            (self.credential_alias, binding.credential_alias),
            (self.credential_type, binding.credential_type),
        ]
        active = [(expected, actual) for expected, actual in constraints if expected is not None]
        if not active:
            return False
        return all(expected == actual for expected, actual in active)


@dataclass
class CredentialGuardResult:
    """The verdict on one create-or-update read-back."""

    verdict: str
    required_action: str
    bindings: list[CredentialBinding] = field(default_factory=list)
    violations: list[CredentialBinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.verdict == CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "required_action": self.required_action,
            "bindings": [binding.to_dict() for binding in self.bindings],
            "violations": [binding.to_dict() for binding in self.violations],
            "notes": list(self.notes),
        }


def scan_for_credential_values(payload: Any, path: str = "autoAssignedCredentials") -> None:
    """Raise :class:`CredentialValueLeak` if *payload* carries a credential value.

    Walks the whole structure: a secret nested three levels down is still a
    secret. Only key names are reported in the error, never the value, so that
    raising this does not itself leak what it found.
    """
    if isinstance(payload, dict):
        for key, child in payload.items():
            if VALUE_FIELD_PATTERN.search(str(key)):
                raise CredentialValueLeak(
                    f"credential read-back carries a value-shaped field at {path}.{key} — "
                    "the guard compares ids, aliases and types only"
                )
            scan_for_credential_values(child, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, child in enumerate(payload):
            scan_for_credential_values(child, f"{path}[{index}]")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_bindings(payload: Any) -> list[CredentialBinding]:
    """Reduce an ``autoAssignedCredentials`` read-back to identifier-only bindings.

    Accepts the two shapes the server uses — a list of binding records, and a
    mapping of node name to binding — and refuses anything else rather than
    guessing. ``None`` and an empty container both mean "nothing was bound",
    which is the expected result on this instance.
    """
    if payload is None:
        return []

    scan_for_credential_values(payload)

    records: list[tuple[str | None, Any]] = []
    if isinstance(payload, list):
        records = [(None, item) for item in payload]
    elif isinstance(payload, dict):
        records = list(payload.items())
    else:
        raise TypeError(
            f"unsupported autoAssignedCredentials shape: {type(payload).__name__}; "
            "expected a list of bindings or a mapping of node name to binding"
        )

    bindings: list[CredentialBinding] = []
    for key, record in records:
        if not isinstance(record, dict):
            raise TypeError(
                "each autoAssignedCredentials entry must be an object describing one binding; "
                f"got {type(record).__name__}"
            )
        node_name = (
            _optional_str(record.get("node") or record.get("nodeName") or key) or "<unknown node>"
        )
        bindings.append(
            CredentialBinding(
                node_name=node_name,
                credential_id=_optional_str(record.get("id") or record.get("credentialId")),
                credential_alias=_optional_str(
                    record.get("alias") or record.get("name") or record.get("credentialName")
                ),
                credential_type=_optional_str(record.get("type") or record.get("credentialType")),
            )
        )
    return bindings


def guard_credentials(
    payload: Any,
    allowlist: list[AllowedCredential] | None = None,
) -> CredentialGuardResult:
    """Judge an ``autoAssignedCredentials`` read-back against the DEV allowlist.

    *allowlist* defaults to empty, which is this instance's real state: the DEV
    instance was provisioned with no credentials, so any binding at all is an
    anomaly and the run stops.
    """
    entries = list(allowlist or [])
    bindings = parse_bindings(payload)
    notes: list[str] = []

    if not entries:
        notes.append(
            "DEV allowlist is empty — the instance was provisioned with no credentials, "
            "so any binding is an anomaly"
        )

    violations = [
        binding for binding in bindings if not any(entry.matches(binding) for entry in entries)
    ]

    if violations:
        notes.extend(
            f"binding outside the DEV allowlist — {binding.describe()}" for binding in violations
        )
        return CredentialGuardResult(
            verdict=ANOMALY,
            required_action=ACTION_STOP_AND_REVERT,
            bindings=bindings,
            violations=violations,
            notes=notes,
        )

    if not bindings:
        notes.append("no credential was bound by the create or update")

    return CredentialGuardResult(
        verdict=CLEAN,
        required_action=ACTION_PROCEED,
        bindings=bindings,
        violations=[],
        notes=notes,
    )
