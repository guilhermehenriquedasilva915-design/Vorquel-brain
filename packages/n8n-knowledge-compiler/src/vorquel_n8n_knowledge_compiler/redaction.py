from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s\"']+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{8,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{8,})\b"),
]

_SENSITIVE_PATH = re.compile(
    r"(?i)(credential|authorization|api[_ -]?key|token|password|passwd|secret)"
)


def path_is_sensitive(path: str) -> bool:
    return bool(_SENSITIVE_PATH.search(path))


def redact_text(text: str, *, limit: int = 400) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}<redacted>", redacted)
        else:
            redacted = pattern.sub("<redacted>", redacted)
    redacted = redacted.replace("\r", " ").strip()
    if len(redacted) > limit:
        redacted = redacted[: limit - 1] + "…"
    return redacted
