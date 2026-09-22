"""The BUILD fixture must stay SAFE_TEST eligible.

`fixtures/safe_test_minimal.json` is the workflow PR2 builds on the DEV
instance. Its whole value is that it is boring: no credential, no network, no
filesystem, no shell, no community node. These tests fail if an edit ever makes
it interesting, because the SAFE TEST gate would then be proving something else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vorquel_n8n_build_guard import (
    ALLOWED,
    CLEAN,
    PROCEED,
    REFUSE,
    SafeTestEvidence,
    classify_workflow,
    evaluate,
    guard_credentials,
    nodes_requiring_pinning,
    worst_verdict,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "safe_test_minimal.json"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def risks(workflow: dict):
    return classify_workflow(workflow)


def test_no_node_endangers_the_host(risks) -> None:
    """Precondition 4: nothing in the fixture may be worse than ALLOWED."""
    assert worst_verdict(risks) == ALLOWED
    assert [r.verdict for r in risks] == [ALLOWED] * len(risks)


def test_only_the_trigger_reaches_outside(risks) -> None:
    """Precondition 7 has exactly one node to prove, and it is the trigger."""
    assert [r.node_name for r in nodes_requiring_pinning(risks)] == ["Manual Trigger"]


def test_fixture_declares_no_credentials(workflow: dict) -> None:
    assert all(not node.get("credentials") for node in workflow["nodes"])
    result = guard_credentials(None)
    assert result.verdict == CLEAN
    assert result.bindings == []


def test_fixture_uses_only_deterministic_first_party_nodes(workflow: dict) -> None:
    allowed_types = {"n8n-nodes-base.manualTrigger", "n8n-nodes-base.set"}
    assert {node["type"] for node in workflow["nodes"]} <= allowed_types


def test_gate_refuses_until_the_server_has_spoken(risks, workflow: dict) -> None:
    """Offline evidence alone is not enough, and the gate says which step is missing.

    This is the state PR2 is actually in while the MCP tool surface is absent:
    everything provable offline is proven, and the gate still refuses at the
    first precondition that needs the server.
    """
    decision = evaluate(
        SafeTestEvidence(
            deterministic_validation_passed=True,
            analyzer_risk_decision="SAFE_FOR_LEARNING",
            node_risks=risks,
            declared_node_count=len(workflow["nodes"]),
        )
    )
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "validate_workflow"
    assert not decision.may_execute


def test_gate_proceeds_once_the_server_evidence_exists(risks, workflow: dict) -> None:
    """With every precondition recorded, this fixture is the case that passes."""
    decision = evaluate(
        SafeTestEvidence(
            deterministic_validation_passed=True,
            validate_workflow_passed=True,
            analyzer_risk_decision="SAFE_FOR_LEARNING",
            node_risks=risks,
            pin_data_prepared=True,
            pinned_node_names={"Manual Trigger"},
            declared_node_count=len(workflow["nodes"]),
        )
    )
    assert decision.decision == PROCEED
    assert decision.may_execute
    assert not decision.unpinned_privileged_nodes


def test_unpinned_trigger_is_refused(risks, workflow: dict) -> None:
    """If pin data missed the trigger, precondition 7 must catch it."""
    decision = evaluate(
        SafeTestEvidence(
            deterministic_validation_passed=True,
            validate_workflow_passed=True,
            analyzer_risk_decision="SAFE_FOR_LEARNING",
            node_risks=risks,
            pin_data_prepared=True,
            pinned_node_names=set(),
            declared_node_count=len(workflow["nodes"]),
        )
    )
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "privileged_nodes_pinned"
    assert decision.unpinned_privileged_nodes == ["Manual Trigger"]
