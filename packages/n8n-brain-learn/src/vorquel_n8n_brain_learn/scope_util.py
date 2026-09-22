"""Scope resolution for LEARN.

The rules live in the retrieval package and are imported rather than restated.
A second definition of "which scope may see what" is a second chance to get it
wrong, and the two would drift.
"""

from __future__ import annotations

from vorquel_n8n_brain_retrieval.scope import Scope, ScopeError

__all__ = ["Scope", "ScopeError", "resolve_scope"]


def resolve_scope(raw: str | Scope) -> Scope:
    if isinstance(raw, Scope):
        return raw
    return Scope.parse(raw)
