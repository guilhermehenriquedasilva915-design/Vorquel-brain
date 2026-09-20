"""The doctor's n8n verdict must follow evidence, not a constant.

Before this, `n8n.mcp` was hardcoded to BLOCKED and `n8n.deny_rules` announced
itself as placeholders, so the doctor could not tell a working instance from a
missing one. These tests pin the three states apart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from vorquel_n8n_brain_retrieval import doctor as doctor_mod
from vorquel_n8n_brain_retrieval.doctor import (
    DoctorReport,
    Status,
    _check_n8n_deny_rules,
    _check_n8n_mcp,
    _check_n8n_profile,
)
from vorquel_n8n_brain_retrieval.environment_profile import (
    REQUIRED_ASK_TOOLS,
    REQUIRED_DENY_TOOLS,
    build_profile,
)

REAL_TOOLS = sorted(REQUIRED_DENY_TOOLS | REQUIRED_ASK_TOOLS | {"search_workflows"})


def _status(report: DoctorReport, name: str) -> Status:
    return next(c.status for c in report.checks if c.name == name)


def _detail(report: DoctorReport, name: str) -> str:
    return next(c.detail for c in report.checks if c.name == name)


def _sound_policy() -> dict[str, list[str]]:
    pre = "mcp__n8n__"
    return {
        "allow": [pre + "search_workflows"],
        "ask": [pre + t for t in sorted(REQUIRED_ASK_TOOLS)],
        "deny": [pre + t for t in sorted(REQUIRED_DENY_TOOLS)],
    }


def _profile(**overrides):
    base = {
        "instance_id": "abc123def456789",
        "base_url": "http://127.0.0.1:5678",
        "n8n_version": "2.39.8",
        "environment": "DEV",
        "mcp_server_url": "http://127.0.0.1:5678/mcp-server/http",
        "mcp_tools": REAL_TOOLS,
        "mcp_scopes": ["workflow:read"],
    }
    base.update(overrides)
    return build_profile(**base)


# --------------------------------------------------------------------------
# n8n.mcp
# --------------------------------------------------------------------------


def test_mcp_is_ready_once_a_real_surface_was_enumerated():
    report = DoctorReport()
    _check_n8n_mcp(report, REAL_TOOLS, configured=True)
    assert _status(report, "n8n.mcp") is Status.READY
    assert str(len(REAL_TOOLS)) in _detail(report, "n8n.mcp")


def test_mcp_configured_but_never_enumerated_is_only_limited():
    report = DoctorReport()
    _check_n8n_mcp(report, [], configured=True)
    assert _status(report, "n8n.mcp") is Status.READY_WITH_LIMITS


def test_mcp_absent_is_blocked():
    report = DoctorReport()
    _check_n8n_mcp(report, [], configured=False)
    assert _status(report, "n8n.mcp") is Status.BLOCKED


def test_configured_detection_reads_the_client_config(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_mod.Path, "home", staticmethod(lambda: tmp_path))
    assert doctor_mod._mcp_server_configured() is False

    (tmp_path / ".claude.json").write_text(
        '{"projects": {"/repo": {"mcpServers": {"n8n": {"type": "http"}}}}}',
        encoding="utf-8",
    )
    assert doctor_mod._mcp_server_configured() is True


def test_malformed_client_config_is_not_mistaken_for_a_server(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_mod.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".claude.json").write_text("{not json", encoding="utf-8")
    assert doctor_mod._mcp_server_configured() is False


# --------------------------------------------------------------------------
# n8n.deny_rules
# --------------------------------------------------------------------------


def test_deny_rules_ready_when_policy_matches_the_real_surface():
    report = DoctorReport()
    _check_n8n_deny_rules(report, REAL_TOOLS, _sound_policy())
    assert _status(report, "n8n.deny_rules") is Status.READY


def test_deny_rules_blocked_when_a_dangerous_tool_is_allowed():
    policy = _sound_policy()
    policy["deny"].remove("mcp__n8n__archive_workflow")
    policy["allow"].append("mcp__n8n__archive_workflow")
    report = DoctorReport()
    _check_n8n_deny_rules(report, REAL_TOOLS, policy)
    assert _status(report, "n8n.deny_rules") is Status.BLOCKED
    assert "archive_workflow" in _detail(report, "n8n.deny_rules")


def test_deny_rules_not_verifiable_without_an_observed_surface():
    report = DoctorReport()
    _check_n8n_deny_rules(report, [], _sound_policy())
    assert _status(report, "n8n.deny_rules") is Status.READY_WITH_LIMITS
    assert "nao verificavel" in _detail(report, "n8n.deny_rules")


def test_deny_rules_blocked_without_any_permissions():
    report = DoctorReport()
    _check_n8n_deny_rules(report, REAL_TOOLS, {})
    assert _status(report, "n8n.deny_rules") is Status.BLOCKED


def test_forward_looking_rules_are_reported_as_such():
    policy = _sound_policy()
    policy["deny"].append("mcp__n8n__publish_workflow")
    report = DoctorReport()
    _check_n8n_deny_rules(report, REAL_TOOLS, policy)
    assert _status(report, "n8n.deny_rules") is Status.READY
    assert "guarda futura" in _detail(report, "n8n.deny_rules")


# --------------------------------------------------------------------------
# n8n.environment_profile
# --------------------------------------------------------------------------


def test_profile_ready_when_fresh_and_dev():
    report = DoctorReport()
    _check_n8n_profile(report, _profile(), None)
    assert _status(report, "n8n.environment_profile") is Status.READY
    assert "2.39.8" in _detail(report, "n8n.environment_profile")


def test_profile_missing_is_blocked():
    report = DoctorReport()
    _check_n8n_profile(report, None, None)
    assert _status(report, "n8n.environment_profile") is Status.BLOCKED


def test_unsafe_profile_is_blocked_with_its_reason():
    report = DoctorReport()
    _check_n8n_profile(report, None, "perfil contem campos suspeitos: password")
    assert _status(report, "n8n.environment_profile") is Status.BLOCKED
    assert "suspeitos" in _detail(report, "n8n.environment_profile")


@pytest.mark.parametrize("env", ["PROD", "STAGING", ""])
def test_a_non_dev_profile_blocks_mutation(env):
    profile = _profile()
    profile["environment"] = env
    report = DoctorReport()
    _check_n8n_profile(report, profile, None)
    assert _status(report, "n8n.environment_profile") is Status.BLOCKED
    assert "DEV" in _detail(report, "n8n.environment_profile")


def test_a_stale_profile_is_limited_not_ready():
    profile = _profile(checked_at=datetime.now(UTC) - timedelta(days=90))
    report = DoctorReport()
    _check_n8n_profile(report, profile, None)
    assert _status(report, "n8n.environment_profile") is Status.READY_WITH_LIMITS


def test_overall_is_blocked_if_any_check_is():
    report = DoctorReport()
    report.add("a", Status.READY, "")
    report.add("b", Status.READY_WITH_LIMITS, "")
    assert report.overall is Status.READY_WITH_LIMITS
    report.add("c", Status.BLOCKED, "")
    assert report.overall is Status.BLOCKED
