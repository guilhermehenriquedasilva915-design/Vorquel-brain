from __future__ import annotations

import copy

import pytest

from vorquel_n8n_knowledge_writer.validation import (
    KnowledgeItemValidationError,
    prepare_records,
)


def test_valid_item_maps_only_safe_records(knowledge_item):
    records = prepare_records(knowledge_item, analyzer_version="0.1")

    assert records.source["trust_level"] == "RAW_UNTRUSTED"
    assert records.analysis["risk_decision"] == "REVIEW_REQUIRED"
    assert records.knowledge["knowledge_role"] == "QUARANTINED_REFERENCE"
    assert records.knowledge["implementation_reference_allowed"] is False
    assert records.knowledge["vorquel_validated"] is False

    serialized = str(records.knowledge)
    assert "echo should-not-be-persisted" not in serialized


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("kind",), "RAW_WORKFLOW"),
        (("source_content_trust",), "TRUSTED"),
        (("admission", "implementation_reference_allowed"), True),
        (("admission", "vorquel_validated"), True),
    ],
)
def test_rejects_forbidden_promotions(knowledge_item, path, value):
    item = copy.deepcopy(knowledge_item)
    target = item
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


def test_rejects_raw_evidence_field(knowledge_item):
    item = copy.deepcopy(knowledge_item)
    item["security_findings"][0]["evidence"] = "raw secret"

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


@pytest.mark.parametrize("forbidden_key", ["content", "code", "command"])
def test_rejects_raw_executable_fields(knowledge_item, forbidden_key):
    item = copy.deepcopy(knowledge_item)
    item["executable_snippets_untrusted"][0][forbidden_key] = "do something"

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


def test_rejects_node_count_mismatch(knowledge_item):
    item = copy.deepcopy(knowledge_item)
    item["workflow"]["node_count"] = 999

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


def test_rejects_role_scope_drift(knowledge_item):
    item = copy.deepcopy(knowledge_item)
    item["admission"]["knowledge_role"] = "REFERENCE_PATTERN"

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


def test_rejects_unknown_top_level_field(knowledge_item):
    item = copy.deepcopy(knowledge_item)
    item["raw_workflow"] = {"nodes": []}

    with pytest.raises(KnowledgeItemValidationError):
        prepare_records(item, analyzer_version="0.1")


def test_error_does_not_echo_untrusted_value(knowledge_item):
    item = copy.deepcopy(knowledge_item)
    secret = "super-secret-value-that-should-not-be-echoed"
    item["admission"]["risk_decision"] = secret

    with pytest.raises(KnowledgeItemValidationError) as caught:
        prepare_records(item, analyzer_version="0.1")

    assert secret not in str(caught.value)
