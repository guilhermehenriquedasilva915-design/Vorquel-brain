"""The SAFE TEST gate: the seven preconditions in front of ``test_workflow``.

``test_workflow`` executes unpinned nodes for real, so it is a gate with
preconditions rather than a playground. The tool matrix lists seven:

1. deterministic validation
2. ``validate_workflow``
3. Static Analyzer
4. side-effect classification
5. ``prepare_workflow_pin_data``
6. inspect which nodes were skipped
7. refuse privileged nodes

This module encodes them as an ordered, evidence-carrying gate with one design
rule running through it: **absence of evidence is failure, not success.** Every
precondition has to be positively satisfied by something the caller recorded. A
field left at its default reads as "never ran", so a caller who forgets a step
gets a refusal, not a pass. That is why :class:`SafeTestEvidence` has no
permissive defaults and why :func:`evaluate` returns ``REFUSE`` on an empty
evidence record.

Preconditions 4 and 7 check different things, and the distinction is the whole
point of the gate. Precondition 4 asks whether any node could harm the *host* —
``Execute Command``, SSH, file I/O, unclassified code — and pin data is
irrelevant to it, because pin data does not cover those nodes at all.
Precondition 7 asks whether every node that would reach *outside* the execution
was really pinned: a trigger, a credentialed node, an HTTP Request. Those are
harmless to the host and so clear precondition 4, which is exactly why they need
a check of their own.

For precondition 7 the gate does not trust the category. Pin data is *supposed*
to cover those three kinds of node, so the gate takes the node names
``prepare_workflow_pin_data`` actually reported and requires each such node to
appear among them. A node that should have been pinned and was not would call a
third party for real, and the gate refuses.

"Privileged", in the precondition name below, means precisely
:attr:`NodeRisk.requires_pinning` — reaches outside the execution — not
"dangerous to the host", which is :attr:`NodeRisk.verdict`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .node_risk import ALLOWED, BLOCKED, NodeRisk, nodes_requiring_pinning, worst_verdict

PROCEED = "PROCEED"
REFUSE = "REFUSE"

#: The preconditions, in the order the matrix states them. The gate reports the
#: first one that fails, so the order is part of the contract.
PRECONDITIONS = (
    "deterministic_validation",
    "validate_workflow",
    "static_analyzer",
    "side_effect_classification",
    "prepare_workflow_pin_data",
    "pin_data_inspected",
    "privileged_nodes_pinned",
)


@dataclass
class SafeTestEvidence:
    """What the pipeline actually did, as recorded by the steps that did it.

    Every field defaults to the "did not happen" value. There is no way to
    satisfy a precondition by omission.
    """

    #: Step 1 — the deterministic, offline validation of the draft passed.
    deterministic_validation_passed: bool = False

    #: Step 2 — ``validate_workflow`` was called and reported no errors.
    validate_workflow_passed: bool = False

    #: Step 3 — the Static Analyzer's ``risk_decision`` for the draft. Only
    #: ``SAFE_FOR_LEARNING`` clears this precondition; ``REVIEW_REQUIRED`` and
    #: ``BLOCKED`` both stop the run.
    analyzer_risk_decision: str | None = None

    #: Step 4 — the per-node side-effect classification. Empty means step 4 did
    #: not run, which is distinct from "ran and found nothing".
    node_risks: list[NodeRisk] = field(default_factory=list)

    #: Step 5 — ``prepare_workflow_pin_data`` was called.
    pin_data_prepared: bool = False

    #: Step 6 — the names of the nodes the server reported as pinned. ``None``
    #: means the result was never inspected; an empty set means it was inspected
    #: and nothing was pinned.
    pinned_node_names: set[str] | None = None

    #: How many nodes the draft has, as counted independently of *node_risks*,
    #: so a truncated classification cannot pass for a complete one.
    declared_node_count: int | None = None


@dataclass
class SafeTestDecision:
    """The gate's answer, with the reasoning kept attached."""

    decision: str
    satisfied: list[str] = field(default_factory=list)
    failed_precondition: str | None = None
    reasons: list[str] = field(default_factory=list)
    unpinned_privileged_nodes: list[str] = field(default_factory=list)

    @property
    def may_execute(self) -> bool:
        return self.decision == PROCEED

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["may_execute"] = self.may_execute
        return payload


def _refuse(
    precondition: str,
    reason: str,
    satisfied: list[str],
    unpinned: list[str] | None = None,
) -> SafeTestDecision:
    return SafeTestDecision(
        decision=REFUSE,
        satisfied=satisfied,
        failed_precondition=precondition,
        reasons=[reason],
        unpinned_privileged_nodes=list(unpinned or []),
    )


def evaluate(evidence: SafeTestEvidence) -> SafeTestDecision:
    """Decide whether ``test_workflow`` may be called.

    Returns on the first failed precondition, naming it, so the caller learns
    which step to fix rather than receiving a bare refusal.
    """
    satisfied: list[str] = []

    # 1 — deterministic validation.
    if not evidence.deterministic_validation_passed:
        return _refuse(
            "deterministic_validation",
            "deterministic validation did not pass, or was never run",
            satisfied,
        )
    satisfied.append("deterministic_validation")

    # 2 — validate_workflow.
    if not evidence.validate_workflow_passed:
        return _refuse(
            "validate_workflow",
            "validate_workflow did not pass, or was never called",
            satisfied,
        )
    satisfied.append("validate_workflow")

    # 3 — Static Analyzer. Anything other than SAFE_FOR_LEARNING stops the run,
    # including None, which means the Analyzer never reported.
    if evidence.analyzer_risk_decision != "SAFE_FOR_LEARNING":
        return _refuse(
            "static_analyzer",
            "Static Analyzer risk decision is "
            f"{evidence.analyzer_risk_decision!r}; only 'SAFE_FOR_LEARNING' clears this gate",
            satisfied,
        )
    satisfied.append("static_analyzer")

    # 4 — side-effect classification. It has to have run, to have covered every
    # node, and to have found nothing blocked.
    if not evidence.node_risks:
        return _refuse(
            "side_effect_classification",
            "no node was classified — side-effect classification did not run",
            satisfied,
        )
    if (
        evidence.declared_node_count is not None
        and len(evidence.node_risks) != evidence.declared_node_count
    ):
        return _refuse(
            "side_effect_classification",
            f"classified {len(evidence.node_risks)} node(s) but the draft declares "
            f"{evidence.declared_node_count}; an incomplete classification is not a clean one",
            satisfied,
        )
    verdict = worst_verdict(evidence.node_risks)
    if verdict != ALLOWED:
        offenders = [risk.node_name for risk in evidence.node_risks if risk.verdict == verdict]
        detail = (
            "a blocked node never reaches an execution"
            if verdict == BLOCKED
            else "unreviewed side effects are not safe"
        )
        return _refuse(
            "side_effect_classification",
            f"side-effect classification returned {verdict} for {offenders!r}; {detail}",
            satisfied,
        )
    satisfied.append("side_effect_classification")

    # 5 — prepare_workflow_pin_data.
    if not evidence.pin_data_prepared:
        return _refuse(
            "prepare_workflow_pin_data",
            "prepare_workflow_pin_data was never called, so nothing is pinned",
            satisfied,
        )
    satisfied.append("prepare_workflow_pin_data")

    # 6 — the pin-data result was actually looked at.
    if evidence.pinned_node_names is None:
        return _refuse(
            "pin_data_inspected",
            "the pin-data result was never inspected, so which nodes are pinned is unknown",
            satisfied,
        )
    satisfied.append("pin_data_inspected")

    # 7 — every node that reaches outside the execution must be proven pinned.
    # Reachable precisely because such nodes are harmless to the host and so
    # cleared step 4: an HTTP Request node pin data failed to cover is the case
    # this catches.
    unpinned = [
        risk.node_name
        for risk in nodes_requiring_pinning(evidence.node_risks)
        if risk.node_name not in evidence.pinned_node_names
    ]
    if unpinned:
        return _refuse(
            "privileged_nodes_pinned",
            f"privileged node(s) {unpinned!r} are not in the pinned set and would execute for real",
            satisfied,
            unpinned,
        )
    satisfied.append("privileged_nodes_pinned")

    return SafeTestDecision(
        decision=PROCEED, satisfied=satisfied, reasons=["all seven preconditions satisfied"]
    )
