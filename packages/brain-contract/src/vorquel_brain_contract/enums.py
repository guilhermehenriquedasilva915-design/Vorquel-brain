"""The closed vocabularies of the Brain V1 contract.

Every value here is the **machine-readable** form: what goes into storage, into
an API payload and into a schema ``enum``. Where a human-facing spelling differs
it lives in a display map and never leaks back into the data.

The four reconciliation decisions recorded in
``docs/BRAIN_CONTRACT_V1_RECONCILIATION.md`` are encoded here rather than
described, so that a test can assert them instead of a reader having to trust a
paragraph.
"""

from __future__ import annotations

from typing import Final

CONTRACT_VERSION: Final = "1.0.0"

# --------------------------------------------------------------------------
# DIV-1 — the interface is eight tools, six reads and two controlled writes.
# This package does not implement them. It exists so that the contract is
# representable and countable before anything is built against it.
# --------------------------------------------------------------------------

BRAIN_V1_READS: Final[tuple[str, ...]] = (
    "resolve_entity",
    "get_entity",
    "get_state",
    "get_delta",
    "get_context_pack",
    "search_evidence",
)

BRAIN_V1_CONTROLLED_WRITES: Final[tuple[str, ...]] = (
    "record_candidate",
    "record_event",
)

BRAIN_V1_TOOLS: Final[tuple[str, ...]] = BRAIN_V1_READS + BRAIN_V1_CONTROLLED_WRITES

# --------------------------------------------------------------------------
# DIV-2 — confidentiality tier and data category are two axes, not one.
# --------------------------------------------------------------------------

#: How restricted an object is. Exactly one applies.
SENSITIVITY_LEVELS: Final[tuple[str, ...]] = (
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
    "CLIENT_CONFIDENTIAL",
    "SECRET",
)

#: What kind of data an object carries, independent of how restricted it is.
#: A set, empty by default, so later categories are additive rather than
#: breaking. V1 must support at least ``PII``.
DATA_CLASSES: Final[tuple[str, ...]] = ("PII",)

#: The one tier that may never reach a ContextPack, at any budget, in any mode.
SENSITIVITY_FORBIDDEN_IN_CONTEXT_PACK: Final[str] = "SECRET"

# --------------------------------------------------------------------------
# DIV-3 — six scopes. A company is an ENTITY with entity_type=COMPANY, never a
# scope of its own.
# --------------------------------------------------------------------------

SCOPE_TYPES: Final[tuple[str, ...]] = (
    "GLOBAL_VORQUEL",
    "VERTICAL",
    "ENTITY",
    "CLIENT",
    "PROJECT",
    "PRIVATE_TEST",
)

#: What the *live* database actually accepts today, as constrained in
#: ``supabase/migrations/20260920_004_n8n_brain_experience_and_runs_v01.sql``.
#: Brain-V1-A performs no migration, so the contract is deliberately ahead of
#: storage by ``VERTICAL`` and ``ENTITY`` until Brain-V1-B closes the gap.
#: Nothing may assume storage accepts a scope outside this tuple.
LEGACY_STORAGE_SCOPE_TYPES: Final[tuple[str, ...]] = (
    "GLOBAL_VORQUEL",
    "CLIENT",
    "PROJECT",
    "PRIVATE_TEST",
)

SCOPES_AWAITING_STORAGE_MIGRATION: Final[tuple[str, ...]] = tuple(
    scope for scope in SCOPE_TYPES if scope not in LEGACY_STORAGE_SCOPE_TYPES
)

# --------------------------------------------------------------------------
# DIV-4 — storage spelling is ASCII. The accent is display only.
# --------------------------------------------------------------------------

EPISTEMIC_STATUSES: Final[tuple[str, ...]] = (
    "OBSERVADO",
    "DECLARADO",
    "MEDIDO",
    "INFERIDO",
    "HIPOTESE",
    "ESTIMADO",
    "DESCONHECIDO",
    "CONFLITANTE",
    "INVALIDADO",
)

#: Human-facing spellings. Only entries that actually differ appear here, so
#: the map cannot silently become a second source of truth for the vocabulary.
EPISTEMIC_STATUS_DISPLAY: Final[dict[str, str]] = {"HIPOTESE": "HIPÓTESE"}

#: A separate axis. Whether a human has reviewed something says nothing about
#: how it was known, and merging the two loses both.
VERIFICATION_STATES: Final[tuple[str, ...]] = (
    "UNREVIEWED",
    "REVIEWED",
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
)

#: Statuses that assert a fact about the world and therefore owe provenance.
#: Everything else may stand on reasoning alone, and says so by its status.
EPISTEMIC_STATUSES_REQUIRING_PROVENANCE: Final[tuple[str, ...]] = ("OBSERVADO", "MEDIDO")

#: Promotions that must never happen automatically. Key is the current status,
#: value is what it may not silently become.
FORBIDDEN_EPISTEMIC_PROMOTIONS: Final[dict[str, tuple[str, ...]]] = {
    "INFERIDO": ("MEDIDO", "OBSERVADO"),
    "DECLARADO": ("OBSERVADO", "MEDIDO"),
    "HIPOTESE": ("OBSERVADO", "MEDIDO", "DECLARADO"),
    "ESTIMADO": ("MEDIDO", "OBSERVADO"),
    "DESCONHECIDO": ("OBSERVADO", "MEDIDO", "DECLARADO", "INFERIDO", "ESTIMADO"),
}


def display_epistemic_status(status: str) -> str:
    """The human spelling of a stored status. Unknown values are returned as-is."""
    return EPISTEMIC_STATUS_DISPLAY.get(status, status)


# --------------------------------------------------------------------------
# Object vocabularies
# --------------------------------------------------------------------------

ENTITY_TYPES: Final[tuple[str, ...]] = (
    "COMPANY",
    "PERSON",
    "PROJECT",
    "VERTICAL",
    "PRODUCT",
    "PROCESS",
    "SYSTEM",
    "OFFER",
    "CLIENT",
    "PROSPECT",
    "INTERNAL_UNIT",
)

ENTITY_STATUSES: Final[tuple[str, ...]] = ("ACTIVE", "INACTIVE", "MERGED", "ARCHIVED")

SOURCE_TYPES: Final[tuple[str, ...]] = (
    "DOCUMENT",
    "MESSAGE",
    "TRANSCRIPT",
    "WEB_PAGE",
    "REPOSITORY",
    "WORKFLOW",
    "DATASET",
    "MEDIA",
    "HUMAN_STATEMENT",
    "SYSTEM_RECORD",
)

SOURCE_STATUSES: Final[tuple[str, ...]] = ("ACTIVE", "SUPERSEDED", "WITHDRAWN", "QUARANTINED")

#: How much the *origin* is trusted. Orthogonal to how a claim was known.
TRUST_CLASSES: Final[tuple[str, ...]] = (
    "FIRST_PARTY",
    "CLIENT_PROVIDED",
    "THIRD_PARTY",
    "PUBLIC",
    "UNTRUSTED",
)

#: Whether text from a source may steer behaviour. External content is data,
#: never instruction, so ``NONE`` must always be representable and is the
#: default everywhere.
INSTRUCTION_AUTHORITIES: Final[tuple[str, ...]] = ("NONE", "REFERENCE", "POLICY")

FRAGMENT_TYPES: Final[tuple[str, ...]] = (
    "TEXT",
    "MESSAGE",
    "TRANSCRIPT_INTERVAL",
    "PAGE",
    "FRAME",
    "OCR_BLOCK",
    "TABLE",
    "CODE",
)

#: A locator addresses a fragment inside its source. Media cannot be addressed
#: by character offsets, so the contract carries one locator kind per medium
#: instead of forcing text ranges onto everything.
LOCATOR_KINDS: Final[tuple[str, ...]] = (
    "CHAR_RANGE",
    "LINE_RANGE",
    "PAGE_NUMBER",
    "TIME_INTERVAL",
    "FRAME_INDEX",
    "BBOX",
    "MESSAGE_ID",
    "JSON_POINTER",
)

CLAIM_STATUSES: Final[tuple[str, ...]] = ("ACTIVE", "SUPERSEDED", "RETRACTED", "DISPUTED")

EVIDENCE_TYPES: Final[tuple[str, ...]] = (
    "DIRECT_STATEMENT",
    "MEASUREMENT",
    "ARTIFACT",
    "OBSERVATION",
    "PUBLIC_RESEARCH",
    "DERIVED_ANALYSIS",
)

#: What an evidence item does to a claim. NEUTRAL is a real answer: it records
#: that something was looked at and settled nothing.
EVIDENCE_DIRECTIONS: Final[tuple[str, ...]] = ("SUPPORTS", "CONTRADICTS", "NEUTRAL")

EVIDENCE_STRENGTHS: Final[tuple[str, ...]] = ("WEAK", "MODERATE", "STRONG")

HYPOTHESIS_STATUSES: Final[tuple[str, ...]] = (
    "OPEN",
    "PARTIALLY_SUPPORTED",
    "CONFLICTING",
    "INVALIDATED",
    "SUPPORTED",
    "ARCHIVED",
)

#: A hypothesis that is open or in conflict is a live question, so it owes the
#: next thing that would move it. These statuses require ``next_best_learning``.
HYPOTHESIS_STATUSES_REQUIRING_NEXT_LEARNING: Final[tuple[str, ...]] = ("OPEN", "CONFLICTING")

UNKNOWN_STATUSES: Final[tuple[str, ...]] = (
    "OPEN",
    "PARTIALLY_RESOLVED",
    "RESOLVED",
    "NO_LONGER_RELEVANT",
)

UNKNOWN_PRIORITIES: Final[tuple[str, ...]] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

DECISION_STATUSES: Final[tuple[str, ...]] = ("DRAFT", "ACTIVE", "SUPERSEDED", "REVOKED")

CANDIDATE_TYPES: Final[tuple[str, ...]] = (
    "CLAIM",
    "ENTITY",
    "EVIDENCE",
    "HYPOTHESIS",
    "UNKNOWN",
    "RELATION",
)

CANDIDATE_STATUSES: Final[tuple[str, ...]] = (
    "PENDING",
    "APPROVED",
    "REJECTED",
    "MERGED",
    "CONFLICTING",
)

EVENT_TYPES: Final[tuple[str, ...]] = (
    "INGESTION",
    "REVIEW",
    "DECISION_MADE",
    "AGENT_RUN",
    "BUILD",
    "OUTCOME_OBSERVED",
    "CORRECTION",
)

#: Freshness, exactly as the canonical BRAIN CONTRACT V1 defines it. An earlier
#: draft of this package invented AGING and shortened UNKNOWN_FRESHNESS to
#: UNKNOWN; neither was an approved contract change, and both are gone. A
#: machine-readable alias is not offered on purpose — an alias is how a
#: vocabulary quietly acquires a second spelling.
FRESHNESS_STATUSES: Final[tuple[str, ...]] = ("FRESH", "STALE", "UNKNOWN_FRESHNESS")

CONTEXT_PACK_MODES: Final[tuple[str, ...]] = (
    "OPERATIONAL",
    "RESEARCH",
    "BUILD",
    "AUDIT",
    "STRATEGY",
)

# --------------------------------------------------------------------------
# Absence
# --------------------------------------------------------------------------

#: The explicit marker for "we looked and found nothing". It exists because the
#: alternative — writing ``false`` — turns a gap in the record into a negative
#: fact about the world, which is the single most damaging thing this contract
#: is built to prevent. ``NO_EVIDENCE_FOUND != FALSE``.
NO_EVIDENCE_FOUND: Final[str] = "NO_EVIDENCE_FOUND"

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------

#: Field names no schema in this contract may define, and no payload may carry.
#: A Brain object points at a source; it never carries the means to act.
FORBIDDEN_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "sql",
        "raw_sql",
        "query_sql",
        "shell",
        "command",
        "cmd",
        "exec",
        "script",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "password",
        "passwd",
        "dsn",
        "database_url",
        "connection_string",
        "cookie",
        "authorization",
        "credential",
        "credentials",
        "private_key",
    }
)
