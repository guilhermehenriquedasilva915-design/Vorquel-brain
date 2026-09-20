"""A secret must never become knowledge; PII must be minimised before it does."""

from __future__ import annotations

import pytest

from vorquel_n8n_brain_learn.adapters import learn_message
from vorquel_n8n_brain_learn.policy import SecretDetected, minimise, scan_for_secrets

# Structurally valid but entirely synthetic. None of these is a live credential.
SECRET_SAMPLES = {
    "private_key_block": "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n",
    "aws_access_key_id": "use AKIAIOSFODNN7EXAMPLE for the bucket",
    "github_token": "token ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "slack_token": "xoxb-1234567890-abcdefghijkl",
    "openai_key": "sk-" + "a" * 40,
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    "dsn_with_password": "postgresql://admin:hunter2@db.internal:5432/app",
    "authorization_header": "Authorization: Bearer abc123def456",
    "set_cookie": "Set-Cookie: session=abc123def456; HttpOnly",
    "assigned_credential": 'api_key = "9f8e7d6c5b4a3210"',
}


@pytest.mark.parametrize(("rule", "sample"), sorted(SECRET_SAMPLES.items()))
def test_every_secret_shape_is_refused(rule: str, sample: str) -> None:
    assert scan_for_secrets(sample) is not None

    with pytest.raises(SecretDetected) as caught:
        minimise(sample)

    # The message names the rule that fired and never echoes the value, so a
    # secret cannot leak through a log line or a traceback.
    assert caught.value.rule in SECRET_SAMPLES
    assert sample.split()[-1] not in str(caught.value)


def test_naming_a_credential_is_not_leaking_one() -> None:
    # Advice about credentials is exactly the kind of thing worth remembering.
    result = minimise("Rotacione o api_key do cliente a cada 30 dias e nunca o comite.")
    assert "api_key" in result.text
    assert result.redactions == ()


def test_pii_is_minimised_and_widens_the_classification() -> None:
    result = minimise(
        "Fale com joao.silva@acme.com.br ou no (11) 98765-4321. CPF 123.456.789-09.",
        "INTERNAL",
    )

    assert "joao.silva@acme.com.br" not in result.text
    assert "98765-4321" not in result.text
    assert "123.456.789-09" not in result.text
    assert "[EMAIL_REDIGIDO]" in result.text
    # The knowledge survives the minimisation.
    assert "Fale com" in result.text
    assert set(result.redactions) >= {"email", "cpf", "phone_br"}
    assert result.data_classification == "PII"


def test_classification_is_never_narrowed() -> None:
    result = minimise("contato: alguem@exemplo.com", "CLIENT_CONFIDENTIAL")
    # PII outranks CLIENT_CONFIDENTIAL in this ordering, so it widens.
    assert result.data_classification == "PII"

    clean = minimise("um workflow com tres nos", "CLIENT_CONFIDENTIAL")
    assert clean.data_classification == "CLIENT_CONFIDENTIAL"


def test_a_long_number_that_is_not_a_card_survives() -> None:
    # A version string or an id must not be mistaken for a card number.
    result = minimise("execution id 1234567890123456789 falhou no no HTTP Request")
    assert "1234567890123456789" in result.text


def test_a_secret_bearing_unit_is_refused_but_the_batch_reports_it() -> None:
    batch = learn_message(
        "O webhook do cliente exige assinatura HMAC no header X-Signature sempre.\n\n"
        'Credenciais de teste: api_key = "9f8e7d6c5b4a32100000"\n\n'
        "O retry do HTTP Request precisa de maxTries limitado para nao girar sem teto.",
        "CLIENT:acme",
        "CLIENT_CONFIDENTIAL",
    )

    stored = " ".join(candidate.summary for candidate in batch.candidates)
    assert "9f8e7d6c5b4a32100000" not in stored
    assert len(batch.candidates) == 2

    # Refused, not silently dropped -- and the refusal carries no value.
    assert len(batch.refused) == 1
    assert batch.refused[0].rule == "assigned_credential"
    assert "9f8e7d6c5b4a32100000" not in batch.refused[0].reason
    assert any("recusados por politica" in line for line in batch.summary_lines())
