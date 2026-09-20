"""The shape of a LEARN run: one source, its units, and what was refused.

Identity is derived from content, never from the clock or a counter, so the
same material learned twice produces the same ids and the database can treat
the second run as a no-op. `logical_key` is the one exception: it names the
*thing* rather than the bytes, which is what lets a re-exported PDF or a later
commit become version 2 instead of an unrelated source.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from vorquel_n8n_brain_retrieval.scope import Scope

SOURCE_KINDS = (
    "MESSAGE",
    "TEXT",
    "MARKDOWN",
    "JSON",
    "PDF",
    "DOCX",
    "GIT_REPO",
    "N8N_WORKFLOW",
    "YOUTUBE",
)

KNOWLEDGE_TYPES = (
    "CONCEPT",
    "PROCEDURE",
    "PATTERN",
    "ANTI_PATTERN",
    "ERROR",
    "FIX",
    "EXAMPLE",
    "CLAIM",
    "TOOL_USAGE",
    "CHECKLIST",
    "WARNING",
)

EPISTEMIC_STATUSES = (
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

# Mirrors the constraint in Watch migration 0021. A locator is an address.
LOCATOR_KINDS = (
    "MEDIA_TIME",
    "PDF_PAGE",
    "DOC_SECTION",
    "REPO_FILE",
    "GIT_COMMIT",
    "WORKFLOW_NODE",
    "N8N_EXECUTION",
    "MESSAGE",
    "GENERIC",
)

_FORBIDDEN_LOCATOR_KEYS = frozenset(
    {
        "secret",
        "token",
        "password",
        "api_key",
        "apiKey",
        "authorization",
        "credential",
        "credentials",
        "command",
        "shell",
        "sql",
        "query",
        "payload",
        "body",
    }
)

MAX_SUMMARY_CHARS = 12000
MAX_TITLE_CHARS = 300


class LearnError(ValueError):
    """A LEARN run refused to proceed. Always fails closed."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    # NFC first so the same characters typed two ways hash the same, which is
    # what makes "the same document" idempotent across editors.
    return sha256_bytes(unicodedata.normalize("NFC", text).encode("utf-8"))


def source_id_for(content_sha256: str) -> str:
    return f"src_{content_sha256[:32]}"


def candidate_id_for(content_hash: str) -> str:
    return f"knd_{content_hash[:32]}"


def knowledge_source_id_for(content_hash: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{content_hash}:{ordinal}".encode()).hexdigest()
    return f"ksr_{digest[:32]}"


def validate_locator(locator_kind: str, locator: dict[str, Any]) -> None:
    if locator_kind not in LOCATOR_KINDS:
        raise LearnError(f"unknown locator_kind: {locator_kind!r}")
    offending = sorted(set(locator) & _FORBIDDEN_LOCATOR_KEYS)
    if offending:
        # If the address needed one of these keys, the excerpt is wrong.
        raise LearnError(f"locator carries payload-shaped keys: {offending}")
    if len(str(locator)) > 2048:
        raise LearnError("locator is too large to be an address")


@dataclass(frozen=True)
class SourceRef:
    """A registered source: the root every citation resolves back to."""

    source_kind: str
    content_sha256: str
    byte_size: int
    detected_mime: str
    scope: Scope
    data_classification: str = "INTERNAL"
    logical_key: str | None = None
    external_metadata: dict[str, Any] = field(default_factory=dict)
    # Set only when the source was registered by another component -- today,
    # Vorquel Watch registering a media source through its own ingest path. The
    # Brain then cites that source instead of registering a second row for the
    # same material.
    existing_source_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise LearnError(f"unknown source_kind: {self.source_kind!r}")
        if len(self.content_sha256) != 64 or not all(
            char in "0123456789abcdef" for char in self.content_sha256
        ):
            raise LearnError("content_sha256 must be a lowercase hex digest")
        if self.byte_size < 0:
            raise LearnError("byte_size must not be negative")
        if self.data_classification == "SECRET":
            raise LearnError("SECRET must never become a source")
        if self.existing_source_id is not None and not self.existing_source_id.startswith("src_"):
            raise LearnError("existing_source_id must be a Watch source id")

    @property
    def source_id(self) -> str:
        return self.existing_source_id or source_id_for(self.content_sha256)

    @property
    def is_externally_registered(self) -> bool:
        return self.existing_source_id is not None


@dataclass(frozen=True)
class Candidate:
    """One reviewable claim, addressed back into its source."""

    title: str
    summary: str
    knowledge_type: str
    epistemic_status: str
    locator_kind: str
    locator: dict[str, Any]
    domain: str = "n8n"
    data_classification: str = "INTERNAL"
    instruction_attempts: tuple[str, ...] = ()
    redactions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.knowledge_type not in KNOWLEDGE_TYPES:
            raise LearnError(f"unknown knowledge_type: {self.knowledge_type!r}")
        if self.epistemic_status not in EPISTEMIC_STATUSES:
            raise LearnError(f"unknown epistemic_status: {self.epistemic_status!r}")
        if not self.title.strip() or len(self.title) > MAX_TITLE_CHARS:
            raise LearnError("title must be 1..300 characters")
        if not self.summary.strip() or len(self.summary) > MAX_SUMMARY_CHARS:
            raise LearnError(f"summary must be 1..{MAX_SUMMARY_CHARS} characters")
        validate_locator(self.locator_kind, self.locator)

    @property
    def content_hash(self) -> str:
        # The hash covers what a reviewer would read plus where it came from, so
        # the same excerpt cited from a different page is a different candidate.
        return sha256_text(
            "\u0000".join(
                [
                    self.knowledge_type,
                    self.domain,
                    self.title.strip(),
                    self.summary.strip(),
                    self.locator_kind,
                    repr(sorted(self.locator.items())),
                ]
            )
        )

    @property
    def candidate_id(self) -> str:
        return candidate_id_for(self.content_hash)

    def provenance(self) -> list[dict[str, Any]]:
        return [
            {
                "knowledge_source_id": knowledge_source_id_for(self.content_hash, 0),
                "locator_kind": self.locator_kind,
                "locator": self.locator,
            }
        ]


@dataclass(frozen=True)
class Refusal:
    """Something the source offered that policy would not store."""

    reason: str
    rule: str
    locator_kind: str
    locator: dict[str, Any]


@dataclass(frozen=True)
class LearnBatch:
    """The reviewable result of reading one source.

    Nothing here is knowledge yet. Every candidate is PENDING until a human
    approves it, and `refused` is reported to the operator rather than hidden:
    a LEARN run that silently dropped half a document is worse than one that
    says what it would not keep.
    """

    source: SourceRef
    candidates: tuple[Candidate, ...]
    refused: tuple[Refusal, ...] = ()

    @property
    def instruction_attempts(self) -> tuple[Candidate, ...]:
        return tuple(item for item in self.candidates if item.instruction_attempts)

    def summary_lines(self) -> list[str]:
        by_type: dict[str, int] = {}
        for candidate in self.candidates:
            by_type[candidate.knowledge_type] = by_type.get(candidate.knowledge_type, 0) + 1

        lines = [
            f"fonte: {self.source.source_kind} {self.source.source_id}",
            f"escopo: {self.source.scope} ({self.source.data_classification})",
            f"candidatos: {len(self.candidates)}",
        ]
        lines += [f"  {count} {name}" for name, count in sorted(by_type.items())]
        if self.instruction_attempts:
            lines.append(
                f"  {len(self.instruction_attempts)} trecho(s) tentaram instruir o sistema"
            )
        if self.refused:
            lines.append(f"recusados por politica: {len(self.refused)}")
            for refusal in self.refused:
                lines.append(f"  {refusal.rule}: {refusal.reason}")
        return lines
