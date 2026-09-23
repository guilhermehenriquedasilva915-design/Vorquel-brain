"""Vorquel Brain V1 retrieval: the read path and the deterministic ContextPack.

This package implements the six reads of the Brain V1 contract and the pack
generator on top of them. It consumes ``vorquel-brain-contract`` and defines no
vocabulary of its own; anything closed comes from there, and
``tests/test_enum_parity.py`` fails CI if the two ever disagree.

What Brain-V1-B deliberately is **not**:

* an MCP server — no tool is exposed here, only Python functions;
* a writer — the storage port has no write method and canonical mutation,
  ``record_candidate`` and ``record_event`` belong to Brain-V1-C;
* a store — the twelve V1 objects still have no table of their own, and
  inventing one was explicitly out of bounds. See :mod:`.store`.

Nothing in this package takes SQL, a shell command, a filesystem path, a secret
or a connection string. ``FORBIDDEN_FIELD_NAMES`` in the contract is what a
payload is checked against, and the port above is why there is nothing here to
hand one to.
"""

from __future__ import annotations

from .budget import (
    DROP_ORDER,
    NON_DROPPABLE,
    TOKENS_PER_CHAR,
    TrimLog,
    estimate_tokens,
    minimum_tokens,
)
from .contextpack import (
    CONTEXT_PACK_VERSION,
    MODE_PROFILES,
    ContextPackResult,
    get_context_pack,
)
from .doctor import DoctorReport, Finding, run_doctor
from .errors import (
    NO_EVIDENCE_FOUND,
    Absence,
    AmbiguousEntityError,
    BrainRetrievalError,
    BudgetTooSmallError,
    StoreIntegrityError,
)
from .evidence import EvidenceHit, EvidenceSearchResult, search_evidence
from .parity import ParityError, assert_parity, check_parity, parity_report
from .pipeline import (
    PIPELINE_STAGES,
    RetrievalResult,
    RetrievalTrace,
    expand_relations,
    retrieve,
)
from .policy import (
    DEFAULT_STALENESS_HORIZON,
    carries_pii,
    data_classes_of,
    freshness_for,
    is_secret,
    sensitivity_of,
)
from .promotion import PromotionFinding, detect_promotion, detect_promotions, violations_only
from .reads import Delta, EntityRelation, EntityView, get_delta, get_entity, get_state
from .resolve import EntityMatch, EntityResolution, normalize, resolve_entity
from .scope import GLOBAL_SCOPE_ID, Scope, ScopeError, ScopeGuard
from .store import COLLECTIONS, BrainStore, InMemoryBrainStore

__version__ = "0.1.0"

#: The reads this package implements, from the eight-tool contract (DIV-1). The
#: two controlled writes are absent on purpose and their absence is asserted in
#: CI, the same way Brain-V1-A asserted that it implemented none of the eight.
IMPLEMENTED_READS: tuple[str, ...] = (
    "resolve_entity",
    "get_entity",
    "get_state",
    "get_delta",
    "get_context_pack",
    "search_evidence",
)

__all__ = [
    "CONTEXT_PACK_VERSION",
    "COLLECTIONS",
    "DEFAULT_STALENESS_HORIZON",
    "DROP_ORDER",
    "GLOBAL_SCOPE_ID",
    "IMPLEMENTED_READS",
    "MODE_PROFILES",
    "NON_DROPPABLE",
    "NO_EVIDENCE_FOUND",
    "PIPELINE_STAGES",
    "TOKENS_PER_CHAR",
    "Absence",
    "AmbiguousEntityError",
    "BrainRetrievalError",
    "BrainStore",
    "BudgetTooSmallError",
    "ContextPackResult",
    "Delta",
    "DoctorReport",
    "EntityMatch",
    "EntityRelation",
    "EntityResolution",
    "EntityView",
    "EvidenceHit",
    "EvidenceSearchResult",
    "Finding",
    "InMemoryBrainStore",
    "ParityError",
    "PromotionFinding",
    "RetrievalResult",
    "RetrievalTrace",
    "Scope",
    "ScopeError",
    "ScopeGuard",
    "StoreIntegrityError",
    "TrimLog",
    "assert_parity",
    "carries_pii",
    "check_parity",
    "data_classes_of",
    "detect_promotion",
    "detect_promotions",
    "estimate_tokens",
    "expand_relations",
    "freshness_for",
    "get_context_pack",
    "get_delta",
    "get_entity",
    "get_state",
    "is_secret",
    "minimum_tokens",
    "normalize",
    "parity_report",
    "resolve_entity",
    "retrieve",
    "run_doctor",
    "search_evidence",
    "sensitivity_of",
    "violations_only",
]
