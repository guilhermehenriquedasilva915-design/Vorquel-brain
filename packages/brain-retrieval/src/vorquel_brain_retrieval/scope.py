"""Scope identity and the guard every read passes through.

A scope answers "whose knowledge is this?". Brain-V1-B resolves a request to
exactly one requested scope plus ``GLOBAL_VORQUEL``, and there is no code path
that widens it. In particular there is **no implicit inheritance**: a CLIENT does
not see its VERTICAL, and a VERTICAL does not see the clients under it.

That is a deliberate, costly choice. Inheritance is the feature that would make
the clinic pack quietly pull real-estate material, so it is not offered by
default and cannot be switched on by a caller passing a flag. Widening the
visible set is a contract decision, not a parameter.

The six values here are the contract's, and since 20260922_006 they are also
storage's. ``tests/test_enum_parity.py`` fails CI if the two drift apart again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vorquel_brain_contract import SCOPE_TYPES

GLOBAL_SCOPE_ID = "GLOBAL"

#: Same shape storage enforces, so a scope that is representable here is
#: insertable there and a malformed one fails in both places.
_SCOPE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ScopeError(ValueError):
    """Raised when a scope is malformed. Always fails closed."""


@dataclass(frozen=True, order=True)
class Scope:
    scope_type: str
    scope_id: str = GLOBAL_SCOPE_ID

    def __post_init__(self) -> None:
        if self.scope_type not in SCOPE_TYPES:
            raise ScopeError(f"unknown scope_type: {self.scope_type!r}")
        if not _SCOPE_ID_RE.match(self.scope_id):
            raise ScopeError(f"malformed scope_id: {self.scope_id!r}")
        # GLOBAL_VORQUEL is addressed by the reserved id only. Allowing any other
        # pairing would make "global" a second name for a private scope.
        if (self.scope_type == "GLOBAL_VORQUEL") != (self.scope_id == GLOBAL_SCOPE_ID):
            raise ScopeError(
                "GLOBAL_VORQUEL must use scope_id 'GLOBAL', and 'GLOBAL' is reserved for it"
            )

    @classmethod
    def global_vorquel(cls) -> Scope:
        return cls("GLOBAL_VORQUEL", GLOBAL_SCOPE_ID)

    @classmethod
    def parse(cls, raw: str) -> Scope:
        """Parse ``"CLIENT:acme"`` or ``"GLOBAL_VORQUEL"``."""
        scope_type, _, scope_id = raw.partition(":")
        return cls(scope_type.strip(), scope_id.strip() or GLOBAL_SCOPE_ID)

    @classmethod
    def from_mapping(cls, raw: object) -> Scope:
        """Build from a contract ``scope`` / ``entity_scope`` object."""
        if not isinstance(raw, dict):
            raise ScopeError(f"scope is not an object: {raw!r}")
        try:
            return cls(raw["scope_type"], raw["scope_id"])
        except KeyError as exc:  # pragma: no cover - defensive
            raise ScopeError(f"scope is missing {exc.args[0]!r}") from exc

    def is_global(self) -> bool:
        return self.scope_type == "GLOBAL_VORQUEL"

    def as_mapping(self) -> dict[str, str]:
        return {"scope_type": self.scope_type, "scope_id": self.scope_id}

    def __str__(self) -> str:
        return self.scope_type if self.is_global() else f"{self.scope_type}:{self.scope_id}"


@dataclass(frozen=True)
class ScopeGuard:
    """The single place that decides whether a stored object may be shown.

    Applied to every object after it comes back from the store and again before
    it enters a ContextPack, so a retrieval bug or a future unscoped query still
    cannot put one client's knowledge into another's answer.
    """

    requested: Scope
    include_global: bool = True

    def visible_scopes(self) -> tuple[Scope, ...]:
        """Exactly what this request can see, in a stable order."""
        if self.requested.is_global() or not self.include_global:
            return (self.requested,)
        return (Scope.global_vorquel(), self.requested)

    def admits_scope(self, scope: Scope) -> bool:
        return scope in self.visible_scopes()

    def admits(self, obj: dict) -> bool:
        """Whether one contract object is in scope for this request.

        An object with no readable scope is **not** admitted. Absence of a scope
        is not permission: an object that cannot say where it belongs is exactly
        the one that must not be handed to a caller.
        """
        raw = obj.get("scope") or obj.get("entity_scope")
        try:
            scope = Scope.from_mapping(raw)
        except ScopeError:
            return False
        return self.admits_scope(scope)

    def __str__(self) -> str:
        return " + ".join(str(s) for s in self.visible_scopes())
