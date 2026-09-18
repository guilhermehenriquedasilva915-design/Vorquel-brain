from __future__ import annotations

import copy
import hashlib

import pytest


@pytest.fixture
def knowledge_item():
    text = "Reference note"
    command = "echo should-not-be-persisted"
    return {
        "schema_version": "0.1",
        "kind": "N8N_KNOWLEDGE_ITEM",
        "source_content_trust": "UNTRUSTED_SOURCE_DATA",
        "provenance": {
            "source_repo": "JustInCache/n8n-workflows",
            "source_commit": "5a7864987c22930521382b597873b713cc830dac",
            "source_path": "workflows/Test/0001.json",
            "sha256": "a" * 64,
        },
        "workflow": {
            "name_untrusted": "Fixture",
            "node_count": 2,
            "node_types": {
                "n8n-nodes-base.executeCommand": 1,
                "n8n-nodes-base.webhook": 1,
            },
            "trigger_types": [],
            "integrations": [
                "n8n-nodes-base.executeCommand",
                "n8n-nodes-base.webhook",
            ],
            "nodes": [
                {
                    "name_untrusted": "Command",
                    "type": "n8n-nodes-base.executeCommand",
                    "type_version": 1,
                    "resource": None,
                    "operation": None,
                    "credential_types": [],
                },
                {
                    "name_untrusted": "Input",
                    "type": "n8n-nodes-base.webhook",
                    "type_version": 2,
                    "resource": None,
                    "operation": None,
                    "credential_types": [],
                },
            ],
            "edges": [
                {
                    "source_name_untrusted": "Input",
                    "target_name_untrusted": "Command",
                    "channel": "main",
                    "source_output_index": 0,
                    "target_input_index": 0,
                }
            ],
        },
        "admission": {
            "source_stage": "RAW_UNTRUSTED",
            "analysis_stage": "STATIC_ANALYZED",
            "risk_decision": "REVIEW_REQUIRED",
            "max_severity": "HIGH",
            "knowledge_role": "QUARANTINED_REFERENCE",
            "learning_scope": "review_only",
            "structure_reference_allowed": False,
            "implementation_reference_allowed": False,
            "vorquel_validated": False,
        },
        "security_findings": [
            {
                "rule_id": "EXECUTE_COMMAND",
                "severity": "HIGH",
                "node_name": "Command",
                "node_type": "n8n-nodes-base.executeCommand",
                "json_path": "nodes[0]",
            }
        ],
        "untrusted_text": [
            {
                "kind": "UNTRUSTED_TEXT",
                "node_name": "Input",
                "node_type": "n8n-nodes-base.webhook",
                "json_path": "parameters.description",
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_count": len(text),
                "preview": text,
            }
        ],
        "executable_snippets_untrusted": [
            {
                "kind": "EXECUTABLE_SNIPPET_UNTRUSTED",
                "node_name": "Command",
                "node_type": "n8n-nodes-base.executeCommand",
                "json_path": "parameters.command",
                "reason": "privileged_command",
                "language": "shell_or_remote_command",
                "sha256": hashlib.sha256(command.encode()).hexdigest(),
                "char_count": len(command),
                "content_persisted": False,
            }
        ],
    }


@pytest.fixture
def clone_item(knowledge_item):
    return lambda: copy.deepcopy(knowledge_item)
