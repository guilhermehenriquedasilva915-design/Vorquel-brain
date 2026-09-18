from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SEVERITY_ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    node_name: str | None = None
    node_type: str | None = None
    json_path: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowReport:
    source_path: str
    sha256: str
    workflow_name: str | None
    stage: str = "STATIC_ANALYZED"
    risk_decision: str = "SAFE_FOR_LEARNING"
    max_severity: str = "INFO"
    node_count: int = 0
    node_types: dict[str, int] = field(default_factory=dict)
    trigger_types: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    parse_error: str | None = None

    def finalize(self) -> "WorkflowReport":
        if self.parse_error:
            self.max_severity = "CRITICAL"
            self.risk_decision = "BLOCKED"
            return self

        if self.findings:
            self.max_severity = max(
                (finding.severity for finding in self.findings),
                key=lambda severity: SEVERITY_ORDER[severity],
            )

        if self.max_severity == "CRITICAL":
            self.risk_decision = "BLOCKED"
        elif self.max_severity == "HIGH":
            self.risk_decision = "REVIEW_REQUIRED"
        else:
            self.risk_decision = "SAFE_FOR_LEARNING"
        return self

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["findings"] = [finding.to_dict() for finding in self.findings]
        return payload
