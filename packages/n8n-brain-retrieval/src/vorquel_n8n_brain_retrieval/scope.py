"""Scope identity and isolation rules.

A scope answers "whose knowledge is this?". Retrieval always resolves to exactly
one requested scope plus GLOBAL_VORQUEL; there is no code path that widens it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCOPE_TYPES = ("GLOBAL_VORQUEL", "CLIENT", "PROJECT", "PRIVATE_TEST")
GLOBAL_SCOPE_ID = "GLOBAL"

_SCOPE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ScopeError(ValueError):
    """Raised when a scope is malformed. Always fails closed."""


@dataclass(frozen=True)
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
        is_global_type = self.scope_type == "GLOBAL_VORQUEL"
        is_global_id = self.scope_id == GLOBAL_SCOPE_ID
        if is_global_type != is_global_id:
            raise ScopeError(
                "GLOBAL_VORQUEL must use scope_id 'GLOBAL', and 'GLOBAL' is reserved for it"
            )

    @classmethod
    def global_vorquel(cls) -> Scope:
        return cls("GLOBAL_VORQUEL", GLOBAL_SCOPE_ID)

    @classmethod
    def parse(cls, raw: str) -> Scope:
        """Parse "CLIENT:acme" or "GLOBAL_VORQUEL"."""
        if ":" in raw:
            scope_type, scope_id = raw.split(":", 1)
        else:
            scope_type, scope_id = raw, GLOBAL_SCOPE_ID
        return cls(scope_type.strip(), scope_id.strip())

    def is_global(self) -> bool:
        return self.scope_type == "GLOBAL_VORQUEL"

    def admits(self, row_scope_type: str, row_scope_id: str) -> bool:
        """Whether a stored row may be shown to this scope.

        This is the last line of defence, applied to every row after it comes
        back from the database, so a retrieval bug or a future unscoped query
        still cannot leak one client's knowledge into another's answer.
        """
        if row_scope_type == "GLOBAL_VORQUEL" and row_scope_id == GLOBAL_SCOPE_ID:
            return True
        return row_scope_type == self.scope_type and row_scope_id == self.scope_id

    def __str__(self) -> str:
        return self.scope_type if self.is_global() else f"{self.scope_type}:{self.scope_id}"
