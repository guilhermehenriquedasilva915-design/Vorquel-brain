from __future__ import annotations

from vorquel_n8n_build_guard.node_risk import (
    ALLOWED,
    BLOCKED,
    REVIEW_REQUIRED,
    classify_node,
    classify_workflow,
    nodes_requiring_pinning,
    worst_verdict,
)


def node(name: str, node_type: str) -> dict:
    return {"name": name, "type": node_type}


# --- the host-danger axis: NodeRisk.verdict ---------------------------------


def test_execute_command_is_blocked():
    assert classify_node(node("shell", "n8n-nodes-base.executeCommand")).verdict == BLOCKED


def test_ssh_is_blocked():
    assert classify_node(node("remote", "n8n-nodes-base.ssh")).verdict == BLOCKED


def test_every_filesystem_node_is_blocked():
    for node_type in (
        "n8n-nodes-base.readWriteFile",
        "n8n-nodes-base.readBinaryFile",
        "n8n-nodes-base.writeBinaryFile",
        "n8n-nodes-base.localFileTrigger",
    ):
        assert classify_node(node("f", node_type)).verdict == BLOCKED, node_type


def test_code_nodes_need_review_rather_than_being_blocked():
    for node_type in (
        "n8n-nodes-base.code",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
    ):
        assert classify_node(node("c", node_type)).verdict == REVIEW_REQUIRED, node_type


def test_community_node_needs_review_because_it_was_never_classified():
    risk = classify_node(node("custom", "n8n-nodes-acme.doThing"))
    assert risk.verdict == REVIEW_REQUIRED
    assert "community" in risk.reason


def test_first_party_langchain_nodes_are_not_treated_as_community():
    assert classify_node(node("agent", "@n8n/n8n-nodes-langchain.agent")).verdict == ALLOWED


def test_ordinary_nodes_are_allowed():
    assert classify_node(node("set", "n8n-nodes-base.set")).verdict == ALLOWED


def test_untyped_node_is_treated_as_unclassified_rather_than_allowed():
    # A node with no type must not fall through to ALLOWED just because it
    # matches none of the dangerous sets.
    assert classify_node({"name": "mystery"}).verdict == REVIEW_REQUIRED


# --- the reaches-outside axis: NodeRisk.requires_pinning --------------------


def test_http_request_is_host_safe_but_must_be_pinned():
    # The axes are independent, and this node is why: allowed, yet it would call
    # a third party for real if pin data missed it.
    risk = classify_node(node("api", "n8n-nodes-base.httpRequest"))
    assert risk.verdict == ALLOWED
    assert risk.requires_pinning is True
    assert "network" in risk.pinning_reason


def test_a_credentialed_node_must_be_pinned():
    risk = classify_node(
        {
            "name": "Sheets",
            "type": "n8n-nodes-base.googleSheets",
            "credentials": {"googleApi": {"id": "cred-1"}},
        }
    )
    assert risk.verdict == ALLOWED
    assert risk.requires_pinning is True
    assert "credential" in risk.pinning_reason


def test_an_empty_credentials_object_does_not_make_a_node_credentialed():
    risk = classify_node(
        {"name": "Sheets", "type": "n8n-nodes-base.googleSheets", "credentials": {}}
    )
    assert risk.requires_pinning is False


def test_a_trigger_must_be_pinned():
    risk = classify_node(node("cron", "n8n-nodes-base.scheduleTrigger"))
    assert risk.requires_pinning is True
    assert "trigger" in risk.pinning_reason


def test_a_plain_data_node_needs_no_pinning():
    risk = classify_node(node("set", "n8n-nodes-base.set"))
    assert risk.requires_pinning is False
    assert risk.pinning_reason is None


def test_the_two_axes_are_independent():
    # A blocked node that also reaches outside carries both facts, rather than
    # one overwriting the other.
    risk = classify_node(node("trigger-file", "n8n-nodes-base.localFileTrigger"))
    assert risk.verdict == BLOCKED
    assert risk.requires_pinning is True


# --- folding over a workflow -----------------------------------------------


def test_worst_verdict_folds_to_the_most_dangerous_node():
    risks = classify_workflow(
        {
            "nodes": [
                node("set", "n8n-nodes-base.set"),
                node("code", "n8n-nodes-base.code"),
                node("shell", "n8n-nodes-base.executeCommand"),
            ]
        }
    )
    assert worst_verdict(risks) == BLOCKED


def test_worst_verdict_of_an_empty_classification_is_allowed():
    # The gate rejects an empty classification itself; this function must not be
    # the place that decides it, so it folds to the neutral value.
    assert worst_verdict([]) == ALLOWED


def test_nodes_requiring_pinning_lists_only_what_reaches_outside():
    risks = classify_workflow(
        {
            "nodes": [
                node("set", "n8n-nodes-base.set"),
                node("code", "n8n-nodes-base.code"),
                node("api", "n8n-nodes-base.httpRequest"),
                node("cron", "n8n-nodes-base.scheduleTrigger"),
            ]
        }
    )
    assert [risk.node_name for risk in nodes_requiring_pinning(risks)] == ["api", "cron"]


def test_classify_workflow_ignores_malformed_node_lists():
    assert classify_workflow({"nodes": "not-a-list"}) == []
    assert classify_workflow({}) == []
    assert classify_workflow({"nodes": ["not-a-dict"]}) == []


def test_risk_serializes_for_the_report():
    payload = classify_node(node("shell", "n8n-nodes-base.executeCommand")).to_dict()
    assert payload["verdict"] == BLOCKED
    assert payload["node_type"] == "n8n-nodes-base.executeCommand"
