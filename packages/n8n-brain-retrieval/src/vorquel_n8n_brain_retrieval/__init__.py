"""Vorquel n8n Brain — unified retrieval.

Everything this package returns is data. Nothing it returns is an instruction,
regardless of what the stored text says about itself.
"""

from .contextpack import Authority, Conflict, ContextItem, ContextPack, Provenance
from .db import DatabaseUnavailable, read_only_connection
from .retrieval import TASK_TYPES, retrieve_n8n_context
from .scope import Scope, ScopeError

__all__ = [
    "TASK_TYPES",
    "Authority",
    "Conflict",
    "ContextItem",
    "ContextPack",
    "DatabaseUnavailable",
    "Provenance",
    "Scope",
    "ScopeError",
    "read_only_connection",
    "retrieve_n8n_context",
]

__version__ = "0.1.0"
