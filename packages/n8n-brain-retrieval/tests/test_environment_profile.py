"""The profile must stay boring: sanitized, secret-free, and honest about age.

These tests exist because the doctor's n8n verdict is now derived from this
file. If a profile could carry a secret, or could claim a tool surface nobody
observed, the verdict would be decoration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from vorquel_n8n_brain_retrieval.environment_profile import (
    REQUIRED_ASK_TOOLS,
    REQUIRED_DENY_TOOLS,
    ProfileError,
    audit_tool_policy,
    build_profile,
    dead_deny_rules,
    load_profile,
    observed_tools,
    profile_age_days,
    sanitize_base_url,
    sanitize_instance_id,
    scan_for_secrets,
    write_profile,
)

REAL_TOOLS = sorted(
    REQUIRED_DENY_TOOLS
    | REQUIRED_ASK_TOOLS
    | {"search_workflows", "validate_workflow", "list_credentials"}
)


def _permissions(allow=(), ask=(), deny=()) -> dict[str, list[str]]:
    pre = "mcp__n8n__"
    return {
        "allow": [pre + t for t in allow],
        "ask": [pre + t for t in ask],
        "deny": [pre + t for t in deny],
    }


def _sound_policy() -> dict[str, list[str]]:
    return _permissions(
        allow=["search_workflows", "validate_workflow", "list_credentials"],
        ask=sorted(REQUIRED_ASK_TOOLS),
        deny=sorted(REQUIRED_DENY_TOOLS),
    )


# --------------------------------------------------------------------------
# Sanitizing
# --------------------------------------------------------------------------


def test_base_url_drops_embedded_credentials():
    assert sanitize_base_url("http://user:pw@127.0.0.1:5678/rest") == "http://127.0.0.1:5678"


def test_base_url_keeps_scheme_host_and_port():
    assert sanitize_base_url("https://n8n.example.com:8443/") == "https://n8n.example.com:8443"


def test_base_url_without_scheme_is_refused():
    with pytest.raises(ValueError, match="esquema"):
        sanitize_base_url("127.0.0.1:5678")


def test_instance_id_is_truncated_but_still_correlatable():
    full = "a" * 64
    assert sanitize_instance_id(full) == "a" * 12 + "..."
    assert sanitize_instance_id("short") == "short"


# --------------------------------------------------------------------------
# Secret refusal
# --------------------------------------------------------------------------


def test_scan_flags_a_forbidden_key_at_any_depth():
    assert scan_for_secrets({"mcp": {"oauth": {"access_token": "x"}}})


def test_scan_flags_a_dsn_hiding_under_an_innocent_key():
    assert scan_for_secrets({"note": "postgresql://u:p@host:5432/db"})


def test_scan_passes_a_clean_profile():
    profile = build_profile(
        instance_id="abc123",
        base_url="http://127.0.0.1:5678",
        n8n_version="2.39.8",
        environment="DEV",
        mcp_server_url="http://127.0.0.1:5678/mcp-server/http",
        mcp_tools=REAL_TOOLS,
        mcp_scopes=["workflow:read"],
    )
    assert scan_for_secrets(profile) == []


def test_build_profile_refuses_to_emit_a_credential():
    with pytest.raises(ProfileError, match="recusado"):
        build_profile(
            instance_id="abc123",
            base_url="http://127.0.0.1:5678",
            n8n_version="2.39.8",
            environment="DEV",
            mcp_server_url=None,
            mcp_tools=[],
            mcp_scopes=[],
            credential_aliases=[{"alias": "slack", "api_key": "sk-abcdefghijklmnopqrst"}],
        )


def test_load_refuses_a_profile_that_gained_a_secret_on_disk(tmp_path):
    target = tmp_path / "profile.json"
    target.write_text(json.dumps({"environment": "DEV", "password": "hunter2"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="suspeitos"):
        load_profile(target)


def test_load_returns_none_when_there_is_no_profile(tmp_path):
    assert load_profile(tmp_path / "absent.json") is None


def test_round_trip_through_disk(tmp_path):
    profile = build_profile(
        instance_id="abc123",
        base_url="http://127.0.0.1:5678",
        n8n_version="2.39.8",
        environment="DEV",
        mcp_server_url="http://127.0.0.1:5678/mcp-server/http",
        mcp_tools=REAL_TOOLS,
        mcp_scopes=["workflow:read"],
    )
    target = write_profile(profile, tmp_path / "nested" / "profile.json")
    assert load_profile(target) == profile
    assert observed_tools(load_profile(target)) == REAL_TOOLS


# --------------------------------------------------------------------------
# Age
# --------------------------------------------------------------------------


def test_age_is_measured_from_checked_at():
    moment = datetime.now(UTC) - timedelta(days=3)
    profile = build_profile(
        instance_id="abc",
        base_url="http://127.0.0.1:5678",
        n8n_version="2.39.8",
        environment="DEV",
        mcp_server_url=None,
        mcp_tools=[],
        mcp_scopes=[],
        checked_at=moment,
    )
    assert profile_age_days(profile) == pytest.approx(3.0, abs=0.01)


def test_age_is_unknown_when_checked_at_is_garbage():
    assert profile_age_days({"checked_at": "not-a-date"}) is None


# --------------------------------------------------------------------------
# Policy audit — the part that replaces the old placeholder verdict
# --------------------------------------------------------------------------


def test_a_sound_policy_produces_no_findings():
    assert audit_tool_policy(REAL_TOOLS, _sound_policy()) == []


def test_a_tool_with_no_rule_at_all_is_a_finding():
    policy = _sound_policy()
    policy["allow"].remove("mcp__n8n__search_workflows")
    findings = audit_tool_policy(REAL_TOOLS, policy)
    assert [f.tool for f in findings] == ["search_workflows"]
    assert "sem regra" in findings[0].problem


def test_a_tool_in_two_buckets_is_a_finding():
    policy = _sound_policy()
    policy["deny"].append("mcp__n8n__search_workflows")
    findings = audit_tool_policy(REAL_TOOLS, policy)
    assert any("mais de um bucket" in f.problem for f in findings)


@pytest.mark.parametrize("tool", sorted(REQUIRED_DENY_TOOLS))
def test_every_dangerous_tool_must_be_denied(tool):
    policy = _sound_policy()
    policy["deny"].remove(f"mcp__n8n__{tool}")
    policy["allow"].append(f"mcp__n8n__{tool}")
    findings = audit_tool_policy(REAL_TOOLS, policy)
    assert any(f.tool == tool and "deny" in f.problem for f in findings)


@pytest.mark.parametrize("tool", sorted(REQUIRED_ASK_TOOLS))
def test_a_mutating_tool_may_not_sit_in_allow(tool):
    policy = _sound_policy()
    policy["ask"].remove(f"mcp__n8n__{tool}")
    policy["allow"].append(f"mcp__n8n__{tool}")
    findings = audit_tool_policy(REAL_TOOLS, policy)
    assert any(f.tool == tool and "allow" in f.problem for f in findings)


def test_a_policy_is_graded_only_against_tools_that_exist():
    # A denylist full of names the server never exposed protects nothing, but
    # it is not itself a divergence.
    policy = _permissions(deny=["publish_workflow", "execute_workflow"])
    assert audit_tool_policy([], policy) == []
    assert dead_deny_rules([], policy) == ["execute_workflow", "publish_workflow"]


def test_dead_rules_are_distinguished_from_live_ones():
    dead = dead_deny_rules(REAL_TOOLS, _sound_policy())
    assert dead == []
