"""Guards that stand between a drafted n8n workflow and a real execution.

Two things in the BUILD pipeline can cause an effect outside the draft, and each
has a guard here:

- binding a credential, which ``create_workflow_from_code`` and
  ``update_workflow`` can do by argument — :mod:`.credential_guard`;
- executing nodes, which ``test_workflow`` does for anything pin data missed —
  :mod:`.safe_test_gate`, built on the classification in :mod:`.node_risk`.
"""

from __future__ import annotations

from .credential_guard import (
    ACTION_PROCEED,
    ACTION_STOP_AND_REVERT,
    ANOMALY,
    CLEAN,
    AllowedCredential,
    CredentialBinding,
    CredentialGuardResult,
    CredentialValueLeak,
    guard_credentials,
    parse_bindings,
    scan_for_credential_values,
)
from .node_risk import (
    ALLOWED,
    BLOCKED,
    REVIEW_REQUIRED,
    UNPINNABLE_TRIGGER_TYPES,
    NodeRisk,
    classify_node,
    classify_workflow,
    nodes_requiring_pinning,
    worst_verdict,
)
from .safe_test_gate import (
    PRECONDITIONS,
    PROCEED,
    REFUSE,
    SafeTestDecision,
    SafeTestEvidence,
    evaluate,
)

__all__ = [
    "ACTION_PROCEED",
    "ACTION_STOP_AND_REVERT",
    "ALLOWED",
    "ANOMALY",
    "BLOCKED",
    "CLEAN",
    "PRECONDITIONS",
    "PROCEED",
    "REFUSE",
    "REVIEW_REQUIRED",
    "UNPINNABLE_TRIGGER_TYPES",
    "AllowedCredential",
    "CredentialBinding",
    "CredentialGuardResult",
    "CredentialValueLeak",
    "NodeRisk",
    "SafeTestDecision",
    "SafeTestEvidence",
    "classify_node",
    "classify_workflow",
    "evaluate",
    "guard_credentials",
    "parse_bindings",
    "nodes_requiring_pinning",
    "scan_for_credential_values",
    "worst_verdict",
]
