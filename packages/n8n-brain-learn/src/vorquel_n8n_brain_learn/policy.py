"""Data policy: what may never be stored, and what must be minimised first.

This module runs before anything reaches a candidate. It has two jobs and they
are deliberately asymmetric:

  * a **secret** is not minimised, it is refused. There is no classification
    that makes an API key storable, so the unit carrying it is dropped and the
    operator is told which rule fired -- never the value.
  * **PII** is minimised in place. The knowledge ("the client sends a signed
    webhook to an address we hold") survives; the personal datum does not.

The database enforces the same boundary again (0021 has no SECRET
classification, 0023 refuses it explicitly). This layer exists so the value
never travels that far in the first place.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# A classification the caller asked for may only ever be widened by what we
# find, never narrowed.
CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CLIENT_CONFIDENTIAL", "PII")
_SEVERITY = {name: index for index, name in enumerate(CLASSIFICATIONS)}


class SecretDetected(ValueError):
    """A credential was found. The unit is refused, not sanitised."""

    def __init__(self, rule: str) -> None:
        # The message names the rule and never echoes the match, so a secret
        # cannot leak through a log line or a stack trace.
        super().__init__(f"secret material detected by rule {rule!r}; unit refused")
        self.rule = rule


# Ordered most-specific first so the reported rule is the informative one.
_SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "dsn_with_password",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s/@]+@[^\s/]+", re.IGNORECASE),
    ),
    (
        "authorization_header",
        re.compile(r"\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic)\s+\S+", re.IGNORECASE),
    ),
    ("set_cookie", re.compile(r"\bset-cookie\s*:\s*\S+", re.IGNORECASE)),
    # A named credential field with an actual value attached. The name alone is
    # not a secret: "rotate the api_key monthly" is knowledge worth keeping.
    (
        "assigned_credential",
        re.compile(
            r"\b(?:password|passwd|secret|api[_-]?key|apikey|access[_-]?token|"
            r"refresh[_-]?token|client[_-]?secret|private[_-]?key|credential)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_.=-]{8,}",
            re.IGNORECASE,
        ),
    ),
)

# Each PII rule replaces the datum with a stable, non-reversible placeholder.
_PII_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b"), "[EMAIL_REDIGIDO]"),
    ("cpf", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[CPF_REDIGIDO]"),
    ("cnpj", re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"), "[CNPJ_REDIGIDO]"),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "[CARTAO_REDIGIDO]",
    ),
    (
        "phone_br",
        # The trailing guard rejects a decimal or a longer run of digits, but
        # must still allow a number that ends a sentence.
        re.compile(r"(?<![\w.])(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)(?!\.\d)"),
        "[TELEFONE_REDIGIDO]",
    ),
)


@dataclass(frozen=True)
class Sanitised:
    """Text that is safe to persist, plus what had to be done to get there."""

    text: str
    data_classification: str
    redactions: tuple[str, ...] = field(default=())

    @property
    def was_minimised(self) -> bool:
        return bool(self.redactions)


def _luhn_ok(digits: str) -> bool:
    """Reject the long-number false positives: a version string is not a card."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _card_replacer(placeholder: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 13 or not _luhn_ok(digits):
            return match.group(0)
        return placeholder

    return replace


def scan_for_secrets(text: str) -> str | None:
    """Return the name of the first secret rule that matches, or None."""
    for rule, pattern in _SECRET_RULES:
        if pattern.search(text):
            return rule
    return None


def minimise(text: str, declared_classification: str = "INTERNAL") -> Sanitised:
    """Refuse secrets, minimise PII, and report the resulting classification.

    Raises SecretDetected rather than returning a partly-cleaned string: a unit
    that contained a credential is not trustworthy material to learn from, and
    silently storing the rest would hide that the operator pasted a secret.
    """
    if declared_classification not in CLASSIFICATIONS:
        raise ValueError(f"unknown data_classification: {declared_classification!r}")

    rule = scan_for_secrets(text)
    if rule is not None:
        raise SecretDetected(rule)

    cleaned = text
    found: list[str] = []
    for name, pattern, placeholder in _PII_RULES:
        if name == "credit_card":
            # A long run of digits is only a card if it passes Luhn; a version
            # string or an execution id must survive untouched.
            replaced = pattern.sub(_card_replacer(placeholder), cleaned)
            # sub() reports no count, and a non-Luhn match is returned intact,
            # so a real change is the only reliable signal that anything went.
            if replaced != cleaned:
                found.append(name)
            cleaned = replaced
            continue

        replaced, count = pattern.subn(placeholder, cleaned)
        if count:
            found.append(name)
        cleaned = replaced

    classification = declared_classification
    if found:
        # Finding PII widens the classification; it never narrows it. A PII
        # datum that was minimised still tells you the source handled people.
        classification = max(classification, "PII", key=lambda name: _SEVERITY[name])

    return Sanitised(text=cleaned, data_classification=classification, redactions=tuple(found))
