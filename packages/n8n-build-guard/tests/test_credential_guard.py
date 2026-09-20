from __future__ import annotations

import pytest

from vorquel_n8n_build_guard.credential_guard import (
    ACTION_PROCEED,
    ACTION_STOP_AND_REVERT,
    ANOMALY,
    CLEAN,
    AllowedCredential,
    CredentialBinding,
    CredentialValueLeak,
    guard_credentials,
    parse_bindings,
)


def test_no_bindings_is_clean_on_the_empty_dev_instance():
    result = guard_credentials(None)
    assert result.verdict == CLEAN
    assert result.required_action == ACTION_PROCEED
    assert result.bindings == []


def test_empty_list_is_also_clean():
    assert guard_credentials([]).verdict == CLEAN


def test_any_binding_is_an_anomaly_when_the_allowlist_is_empty():
    result = guard_credentials([{"node": "Slack", "id": "cred-1", "type": "slackApi"}])
    assert result.verdict == ANOMALY
    assert result.required_action == ACTION_STOP_AND_REVERT
    assert [binding.node_name for binding in result.violations] == ["Slack"]


def test_the_empty_allowlist_is_reported_as_a_deliberate_strict_state():
    result = guard_credentials(None)
    assert any("allowlist is empty" in note for note in result.notes)


def test_a_binding_on_the_allowlist_passes():
    result = guard_credentials(
        [{"node": "Slack", "id": "cred-1", "type": "slackApi"}],
        allowlist=[AllowedCredential(credential_id="cred-1", credential_type="slackApi")],
    )
    assert result.verdict == CLEAN
    assert result.violations == []


def test_a_binding_matching_only_some_fields_is_still_an_anomaly():
    # Same id, different type: the allowlist entry constrains both, so this is
    # not the credential that was approved.
    result = guard_credentials(
        [{"node": "Slack", "id": "cred-1", "type": "somethingElse"}],
        allowlist=[AllowedCredential(credential_id="cred-1", credential_type="slackApi")],
    )
    assert result.verdict == ANOMALY


def test_an_unconstrained_allowlist_entry_is_not_a_wildcard():
    result = guard_credentials(
        [{"node": "Slack", "id": "cred-1", "type": "slackApi"}],
        allowlist=[AllowedCredential()],
    )
    assert result.verdict == ANOMALY


def test_one_bad_binding_among_good_ones_still_stops_the_run():
    result = guard_credentials(
        [
            {"node": "Slack", "id": "cred-1", "type": "slackApi"},
            {"node": "Sheets", "id": "cred-rogue", "type": "googleApi"},
        ],
        allowlist=[AllowedCredential(credential_id="cred-1", credential_type="slackApi")],
    )
    assert result.verdict == ANOMALY
    assert [binding.node_name for binding in result.violations] == ["Sheets"]


def test_mapping_shape_is_accepted_and_keyed_by_node_name():
    bindings = parse_bindings({"Slack": {"id": "cred-1", "type": "slackApi"}})
    assert bindings == [
        CredentialBinding(
            node_name="Slack",
            credential_id="cred-1",
            credential_alias=None,
            credential_type="slackApi",
        )
    ]


def test_an_unexpected_shape_is_refused_rather_than_guessed():
    with pytest.raises(TypeError):
        parse_bindings("cred-1")
    with pytest.raises(TypeError):
        parse_bindings(["cred-1"])


@pytest.mark.parametrize(
    "payload",
    [
        [{"node": "Slack", "id": "cred-1", "password": "hunter2"}],
        [{"node": "Slack", "id": "cred-1", "data": {"apiKey": "sk-live"}}],
        {"Slack": {"id": "cred-1", "accessToken": "abc"}},
        [{"node": "Slack", "nested": {"deeper": {"client_secret": "s"}}}],
    ],
)
def test_a_read_back_carrying_a_value_is_itself_the_incident(payload):
    with pytest.raises(CredentialValueLeak):
        guard_credentials(payload)


def test_the_leak_error_names_the_field_but_never_the_value():
    with pytest.raises(CredentialValueLeak) as excinfo:
        guard_credentials([{"node": "Slack", "password": "hunter2"}])
    message = str(excinfo.value)
    assert "password" in message
    assert "hunter2" not in message


def test_describe_reports_identifiers_only():
    binding = CredentialBinding("Slack", "cred-1", "prod slack", "slackApi")
    described = binding.describe()
    assert "cred-1" in described
    assert "slackApi" in described


def test_result_serializes_for_the_report():
    payload = guard_credentials([{"node": "Slack", "id": "cred-1"}]).to_dict()
    assert payload["verdict"] == ANOMALY
    assert payload["required_action"] == ACTION_STOP_AND_REVERT
    assert payload["violations"][0]["credential_id"] == "cred-1"
