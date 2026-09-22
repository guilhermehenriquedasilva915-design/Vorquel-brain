"""LEARN: turn an external source into reviewable, scoped, cited candidates.

One rule holds across every adapter in this package: a source is material, not
authority. Nothing it says becomes knowledge until a human approves it, and
nothing it says is ever followed as an instruction.
"""

from .extract import RawUnit, to_batch
from .model import Candidate, LearnBatch, LearnError, Refusal, SourceRef
from .policy import Sanitised, SecretDetected, minimise, scan_for_secrets
from .untrusted import UntrustedText, as_untrusted, detect_instruction_attempts
from .writer import PersistResult, WriterUnavailable, persist_batch

__all__ = [
    "Candidate",
    "LearnBatch",
    "LearnError",
    "PersistResult",
    "RawUnit",
    "Refusal",
    "Sanitised",
    "SecretDetected",
    "SourceRef",
    "UntrustedText",
    "WriterUnavailable",
    "as_untrusted",
    "detect_instruction_attempts",
    "minimise",
    "persist_batch",
    "scan_for_secrets",
    "to_batch",
]
