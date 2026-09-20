from __future__ import annotations

import pytest

from vorquel_n8n_build_guard.node_risk import classify_workflow
from vorquel_n8n_build_guard.safe_test_gate import (
    PRECONDITIONS,
    PROCEED,
    REFUSE,
    SafeTestEvidence,
    evaluate,
)


def node(name: str, node_type: str) -> dict:
    return {"name": name, "type": node_type}


CLEAN_WORKFLOW = {
    "nodes": [
        node("Trigger", "n8n-nodes-base.scheduleTrigger"),
        node("Shape", "n8n-nodes-base.set"),
    ]
}


def clean_evidence(**overrides) -> SafeTestEvidence:
    """Evidence with all seven preconditions satisfied, before any override."""
    risks = classify_workflow(CLEAN_WORKFLOW)
    evidence = SafeTestEvidence(
        deterministic_validation_passed=True,
        validate_workflow_passed=True,
        analyzer_risk_decision="SAFE_FOR_LEARNING",
        node_risks=risks,
        pin_data_prepared=True,
        pinned_node_names={"Trigger"},
        declared_node_count=len(CLEAN_WORKFLOW["nodes"]),
    )
    for key, value in overrides.items():
        setattr(evidence, key, value)
    return evidence


def test_the_happy_path_proceeds_and_records_all_seven():
    decision = evaluate(clean_evidence())
    assert decision.decision == PROCEED
    assert decision.may_execute is True
    assert decision.satisfied == list(PRECONDITIONS)


def test_empty_evidence_refuses():
    # The central property: a caller who recorded nothing gets a refusal.
    decision = evaluate(SafeTestEvidence())
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "deterministic_validation"
    assert decision.may_execute is False


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"deterministic_validation_passed": False}, "deterministic_validation"),
        ({"validate_workflow_passed": False}, "validate_workflow"),
        ({"analyzer_risk_decision": None}, "static_analyzer"),
        ({"analyzer_risk_decision": "REVIEW_REQUIRED"}, "static_analyzer"),
        ({"analyzer_risk_decision": "BLOCKED"}, "static_analyzer"),
        ({"node_risks": []}, "side_effect_classification"),
        ({"pin_data_prepared": False}, "prepare_workflow_pin_data"),
        ({"pinned_node_names": None}, "pin_data_inspected"),
    ],
)
def test_each_missing_precondition_refuses_and_names_itself(override, expected):
    decision = evaluate(clean_evidence(**override))
    assert decision.decision == REFUSE
    assert decision.failed_precondition == expected


def test_preconditions_are_reported_in_order():
    # Failing step 2 must still report step 1 as satisfied, so the caller can
    # see how far the pipeline got.
    decision = evaluate(clean_evidence(validate_workflow_passed=False))
    assert decision.satisfied == ["deterministic_validation"]


def test_a_blocked_node_never_reaches_an_execution():
    workflow = {
        "nodes": [
            node("Trigger", "n8n-nodes-base.scheduleTrigger"),
            node("Shell", "n8n-nodes-base.executeCommand"),
        ]
    }
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow(workflow),
            declared_node_count=2,
            # Even claiming it was pinned must not rescue it.
            pinned_node_names={"Trigger", "Shell"},
        )
    )
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "side_effect_classification"


def test_an_incomplete_classification_is_not_a_clean_one():
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow({"nodes": [node("Shape", "n8n-nodes-base.set")]}),
            declared_node_count=5,
        )
    )
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "side_effect_classification"


NETWORK_WORKFLOW = {
    "nodes": [
        node("Trigger", "n8n-nodes-base.scheduleTrigger"),
        node("Call API", "n8n-nodes-base.httpRequest"),
    ]
}


def test_an_unpinned_outward_reaching_node_is_refused_by_precondition_seven():
    # An HTTP Request node is harmless to the host, so it clears step 4. It is
    # only safe because pin data covers it — and here pin data did not.
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow(NETWORK_WORKFLOW),
            declared_node_count=2,
            pinned_node_names={"Trigger"},
        )
    )
    assert decision.decision == REFUSE
    assert decision.failed_precondition == "privileged_nodes_pinned"
    assert decision.unpinned_privileged_nodes == ["Call API"]
    assert decision.satisfied == list(PRECONDITIONS[:6])


def test_the_same_node_proceeds_once_pin_data_really_covered_it():
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow(NETWORK_WORKFLOW),
            declared_node_count=2,
            pinned_node_names={"Trigger", "Call API"},
        )
    )
    assert decision.decision == PROCEED


def test_a_credentialed_node_must_also_be_proven_pinned():
    workflow = {
        "nodes": [
            node("Trigger", "n8n-nodes-base.scheduleTrigger"),
            {
                "name": "Sheets",
                "type": "n8n-nodes-base.googleSheets",
                "credentials": {"googleApi": {"id": "cred-1", "name": "dev"}},
            },
        ]
    }
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow(workflow),
            declared_node_count=2,
            pinned_node_names={"Trigger"},
        )
    )
    assert decision.failed_precondition == "privileged_nodes_pinned"
    assert decision.unpinned_privileged_nodes == ["Sheets"]


def test_a_code_node_is_stopped_at_step_four_not_step_seven():
    # Documents the ordering: a Code node is a host-level concern, so the
    # classifier refuses it before the pin check is ever consulted — and
    # claiming it was pinned does not change that.
    workflow = {
        "nodes": [
            node("Trigger", "n8n-nodes-base.scheduleTrigger"),
            node("Transform", "n8n-nodes-base.code"),
        ]
    }
    decision = evaluate(
        clean_evidence(
            node_risks=classify_workflow(workflow),
            declared_node_count=2,
            pinned_node_names={"Trigger", "Transform"},
        )
    )
    assert decision.failed_precondition == "side_effect_classification"


def test_decision_serializes_for_the_report():
    payload = evaluate(SafeTestEvidence()).to_dict()
    assert payload["decision"] == REFUSE
    assert payload["may_execute"] is False
    assert payload["failed_precondition"] == "deterministic_validation"
