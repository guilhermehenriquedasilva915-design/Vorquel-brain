"""TXT, Markdown, JSON, PDF and DOCX: real files, real extraction, real locators."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from vorquel_n8n_brain_learn.adapters import (
    learn_document,
    learn_json,
    learn_message,
    learn_text_file,
)
from vorquel_n8n_brain_learn.adapters.documents import learn_docx, learn_pdf
from vorquel_n8n_brain_learn.model import LearnError

LONG = "Este paragrafo tem conteudo suficiente para virar um candidato citavel."


def test_markdown_is_addressed_by_heading(tmp_path: Path) -> None:
    path = tmp_path / "guia.md"
    path.write_text(
        f"# Retry\n\n{LONG} O retry precisa de maxTries.\n\n"
        f"# Webhook\n\n{LONG} O webhook precisa de assinatura.\n",
        encoding="utf-8",
    )

    batch = learn_text_file(path, "GLOBAL_VORQUEL")

    assert batch.source.source_kind == "MARKDOWN"
    assert batch.source.logical_key == "guia.md"
    assert [candidate.locator["section"] for candidate in batch.candidates] == [
        "Retry",
        "Webhook",
    ]
    assert all(candidate.locator_kind == "DOC_SECTION" for candidate in batch.candidates)


def test_plain_text_falls_back_to_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / "notas.txt"
    path.write_text(f"{LONG} Primeiro.\n\n{LONG} Segundo.\n", encoding="utf-8")

    batch = learn_text_file(path, "GLOBAL_VORQUEL")

    assert batch.source.source_kind == "TEXT"
    assert [candidate.locator["paragraph"] for candidate in batch.candidates] == [1, 2]


def test_pdf_is_addressed_by_page(pdf_file) -> None:
    path = pdf_file(
        [
            "O no HTTP Request do n8n precisa de retryOnFail com maxTries limitado.",
            "O webhook do cliente exige assinatura HMAC no header X-Signature.",
        ]
    )

    batch = learn_pdf(path, "CLIENT:acme", "CLIENT_CONFIDENTIAL")

    assert batch.source.source_kind == "PDF"
    assert str(batch.source.scope) == "CLIENT:acme"
    assert [candidate.locator for candidate in batch.candidates] == [
        {"page": 1},
        {"page": 2},
    ]
    assert all(candidate.locator_kind == "PDF_PAGE" for candidate in batch.candidates)


def test_a_pdf_with_no_text_layer_says_so_instead_of_returning_nothing(pdf_file) -> None:
    # An empty extraction that looks successful is the worst outcome for a
    # memory: it records that the source was learned and holds nothing.
    path = pdf_file([""])

    with pytest.raises(LearnError, match="camada de texto"):
        learn_pdf(path, "GLOBAL_VORQUEL")


def test_docx_is_addressed_by_section(docx_file) -> None:
    path = docx_file(
        [
            ("Retry", f"{LONG} Use maxTries limitado no HTTP Request."),
            ("Webhook", f"{LONG} Valide a assinatura antes de processar."),
        ]
    )

    batch = learn_docx(path, "GLOBAL_VORQUEL")

    assert batch.source.source_kind == "DOCX"
    sections = [candidate.locator["section"] for candidate in batch.candidates]
    assert sections == ["Retry", "Webhook"]
    assert all(candidate.locator_kind == "DOC_SECTION" for candidate in batch.candidates)


def test_a_macro_bearing_document_is_refused(docx_file, tmp_path: Path) -> None:
    path = docx_file([("Titulo", LONG)])
    # Smuggle a VBA project into an otherwise ordinary .docx.
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("word/vbaProject.bin", b"\x00fake")

    with pytest.raises(LearnError, match="VBA"):
        learn_docx(path, "GLOBAL_VORQUEL")


def test_a_macro_extension_is_refused_without_being_opened(tmp_path: Path) -> None:
    path = tmp_path / "planilha.docm"
    path.write_bytes(b"not even a real document")

    with pytest.raises(LearnError, match="macros"):
        learn_document(str(path), "GLOBAL_VORQUEL")


def test_json_is_addressed_by_path(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"retry": {"maxTries": 3, "note": LONG}, "timeoutMs": 30000}),
        encoding="utf-8",
    )

    batch = learn_json(path, "GLOBAL_VORQUEL")

    paths = {candidate.locator["path"] for candidate in batch.candidates}
    assert "retry.note" in paths
    assert all(candidate.locator_kind == "GENERIC" for candidate in batch.candidates)


def test_an_n8n_workflow_cannot_enter_through_the_generic_json_path(tmp_path: Path) -> None:
    # Reading it here would skip the Analyzer and the Compiler, which are what
    # classify embedded code and decide the admission role.
    path = tmp_path / "workflow.json"
    path.write_text(
        json.dumps(
            {
                "name": "fluxo",
                "nodes": [{"type": "n8n-nodes-base.code", "parameters": {"jsCode": "x"}}],
                "connections": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LearnError, match="Analyzer"):
        learn_json(path, "GLOBAL_VORQUEL")


def test_unsupported_extensions_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "planilha.xlsx"
    path.write_bytes(b"x")

    with pytest.raises(LearnError, match="nao suportada"):
        learn_document(str(path), "GLOBAL_VORQUEL")


def test_learning_the_same_material_twice_is_identical(tmp_path: Path) -> None:
    text = f"{LONG} O retry precisa de maxTries limitado."

    first = learn_message(text, "GLOBAL_VORQUEL")
    second = learn_message(text, "GLOBAL_VORQUEL")

    # Identity is derived from content, so a replay produces the same ids and
    # the database can treat the second run as a no-op.
    assert first.source.source_id == second.source.source_id
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]


def test_changed_bytes_are_a_different_source_under_the_same_logical_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runbook.md"
    path.write_text(f"# Um\n\n{LONG} Versao um.\n", encoding="utf-8")
    first = learn_text_file(path, "GLOBAL_VORQUEL")

    path.write_text(f"# Um\n\n{LONG} Versao dois, revisada.\n", encoding="utf-8")
    second = learn_text_file(path, "GLOBAL_VORQUEL")

    assert first.source.logical_key == second.source.logical_key == "runbook.md"
    assert first.source.content_sha256 != second.source.content_sha256
    assert first.source.source_id != second.source.source_id
