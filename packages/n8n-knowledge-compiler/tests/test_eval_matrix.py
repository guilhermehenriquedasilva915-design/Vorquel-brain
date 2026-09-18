from __future__ import annotations

import json

import pytest
from vorquel_n8n_knowledge_compiler.compiler import compile_knowledge_item


CASES = [
    ("INFO", "SAFE_FOR_LEARNING", "REFERENCE_PATTERN"),
    ("LOW", "SAFE_FOR_LEARNING", "REFERENCE_PATTERN"),
    ("MEDIUM", "SAFE_FOR_LEARNING", "STRUCTURE_REFERENCE_RESTRICTED"),
    ("HIGH", "REVIEW_REQUIRED", "QUARANTINED_REFERENCE"),
    ("CRITICAL", "BLOCKED", "SECURITY_EXAMPLE"),
] * 5


@pytest.mark.parametrize(("severity", "decision", "expected_role"), CASES)
def test_admission_eval_pack_has_no_credential_or_executable_leak(
    severity, decision, expected_role
):
    command = "n8n export:credentials --all --decrypted"
    workflow = {
        "name": f"Eval {severity}",
        "nodes": [
            {
                "name": "Input",
                "type": "n8n-nodes-base.webhook",
                "parameters": {
                    "path": "demo",
                    "description": "Reference text",
                },
            },
            {
                "name": "Potentially Executable",
                "type": "n8n-nodes-base.executeCommand",
                "parameters": {"command": command},
                "credentials": {
                    "sshPassword": {
                        "id": "credential-id-must-not-leak",
                        "name": "Credential Name Must Not Leak",
                    }
                },
            },
        ],
        "connections": {
            "Input": {
                "main": [[{"node": "Potentially Executable", "type": "main", "index": 0}]]
            }
        },
    }
    report = {
        "risk_decision": decision,
        "max_severity": severity,
        "findings": [],
    }

    item = compile_knowledge_item(
        workflow,
        report,
        source_repo="eval/repo",
        source_commit="eval-sha",
        source_path=f"workflows/{severity}.json",
        source_sha256="fixture-sha",
    )
    serialized = json.dumps(item)

    assert item["admission"]["knowledge_role"] == expected_role
    assert item["admission"]["implementation_reference_allowed"] is False
    assert item["admission"]["vorquel_validated"] is False
    assert command not in serialized
    assert "credential-id-must-not-leak" not in serialized
    assert "Credential Name Must Not Leak" not in serialized
