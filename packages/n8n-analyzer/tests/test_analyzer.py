from __future__ import annotations

from vorquel_n8n_analyzer.analyzer import analyze_file, analyze_workflow


def report_for(nodes):
    return analyze_workflow({"name": "test", "nodes": nodes, "connections": {}})


def rules(report):
    return {finding.rule_id for finding in report.findings}


def test_benign_set_workflow_is_safe_for_learning():
    report = report_for(
        [
            {
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "parameters": {},
            },
            {"name": "Set", "type": "n8n-nodes-base.set", "parameters": {}},
        ]
    )
    assert report.risk_decision == "SAFE_FOR_LEARNING"
    assert report.max_severity == "INFO"


def test_execute_command_is_high_risk():
    report = report_for(
        [
            {
                "name": "Run",
                "type": "n8n-nodes-base.executeCommand",
                "parameters": {"command": "echo hello"},
            }
        ]
    )
    assert "EXECUTE_COMMAND" in rules(report)
    assert report.risk_decision == "REVIEW_REQUIRED"


def test_decrypted_credential_export_is_blocked():
    report = report_for(
        [
            {
                "name": "Export Credentials",
                "type": "n8n-nodes-base.executeCommand",
                "parameters": {
                    "command": (
                        "n8n export:credentials --all --pretty "
                        "--decrypted --output=/tmp/cred"
                    )
                },
            }
        ]
    )
    assert "DECRYPTED_CREDENTIAL_EXPORT" in rules(report)
    assert report.risk_decision == "BLOCKED"


def test_ai_plus_ssh_is_prompt_injection_sensitive():
    report = report_for(
        [
            {"name": "AI Agent", "type": "@n8n/n8n-nodes-langchain.agent", "parameters": {}},
            {
                "name": "SSH",
                "type": "n8n-nodes-base.ssh",
                "parameters": {"command": "={{ $json.query }}"},
            },
        ]
    )
    assert "AI_WITH_PRIVILEGED_EXECUTION" in rules(report)
    assert report.risk_decision == "BLOCKED"


def test_eval_in_code_is_high_risk():
    report = report_for(
        [
            {
                "name": "Code",
                "type": "n8n-nodes-base.code",
                "parameters": {"jsCode": "const x = eval(input); return x;"},
            }
        ]
    )
    assert "CODE_EVAL" in rules(report)
    assert report.risk_decision == "REVIEW_REQUIRED"


def test_private_network_http_target_is_high_risk():
    report = report_for(
        [
            {
                "name": "HTTP",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {"url": "http://127.0.0.1:5678/rest/workflows"},
            }
        ]
    )
    assert "PRIVATE_NETWORK_URL" in rules(report)
    assert report.risk_decision == "REVIEW_REQUIRED"


def test_env_placeholder_is_not_flagged_as_hardcoded_secret():
    report = report_for(
        [
            {
                "name": "HTTP",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {"apiKey": "{{ $env.API_KEY }}", "url": "https://example.com"},
            }
        ]
    )
    assert "POSSIBLE_HARDCODED_SECRET" not in rules(report)


def test_hardcoded_secret_is_redacted_in_evidence():
    report = report_for(
        [
            {
                "name": "HTTP",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "apiKey": "super-secret-value-123456",
                    "url": "https://example.com",
                },
            }
        ]
    )
    finding = next(
        item for item in report.findings if item.rule_id == "POSSIBLE_HARDCODED_SECRET"
    )
    assert finding.evidence != "super-secret-value-123456"
    assert "super-secret-value-123456" not in (finding.evidence or "")


def test_noop_named_ai_agent_does_not_escalate_to_critical():
    report = report_for(
        [
            {
                "name": "AI Agent",
                "type": "n8n-nodes-base.noOp",
                "parameters": {},
            },
            {
                "name": "Execute Command",
                "type": "n8n-nodes-base.executeCommand",
                "parameters": {},
            },
        ]
    )
    assert "AI_WITH_PRIVILEGED_EXECUTION" not in rules(report)
    assert report.risk_decision == "REVIEW_REQUIRED"


def test_symlink_input_is_blocked(tmp_path):
    target = tmp_path / "target.json"
    target.write_text('{"name":"x","nodes":[]}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    report = analyze_file(link)
    assert report.risk_decision == "BLOCKED"
    assert "Symlink input is not allowed" in (report.parse_error or "")


def test_size_limit_is_checked_before_json_parse(tmp_path):
    workflow = tmp_path / "large.json"
    workflow.write_bytes(b"x" * 64)

    report = analyze_file(workflow, max_file_bytes=16)
    assert report.risk_decision == "BLOCKED"
    assert "exceeds configured size limit" in (report.parse_error or "")
